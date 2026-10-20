#!/usr/bin/env python3
"""POPULAR_FETCH.py - '국내 인기종목' 원자료 수집 (GitHub Actions)
후보(방산/반도체/전선) 종목별: 거래대금(5일/20일 평균), 등락, 네이버 인기검색 순위, 뉴스 건수(7일/30일, 구글뉴스 RSS), 종토방 글 속도
결과: popular_raw.json -> 'popular-data' 브랜치
"""
import json, re, time, datetime as dt, html, urllib.parse
from concurrent.futures import ThreadPoolExecutor
import requests

UA = {"User-Agent": "Mozilla/5.0"}
KST = dt.timezone(dt.timedelta(hours=9))
CAND = {
 "방산": {"012450":"한화에어로스페이스","079550":"LIG디펜스앤에어로스페이스","047810":"한국항공우주","064350":"현대로템","272210":"한화시스템","103140":"풍산","010820":"퍼스텍","274090":"켄코아에어로스페이스","099320":"쎄트렉아이"},
 "반도체": {"005930":"삼성전자","000660":"SK하이닉스","042700":"한미반도체","007660":"이수페타시스","036930":"주성엔지니어링","039030":"이오테크닉스","058470":"리노공업","240810":"원익IPS","403870":"HPSP","095340":"ISC","067310":"하나마이크론","357780":"솔브레인","095610":"테스","131970":"두산테스나","222800":"심텍","005290":"동진쎄미켐"},
 "전선": {"001440":"대한전선","000500":"가온전선","006340":"대원전선","010120":"LS ELECTRIC","006260":"LS","103590":"일진전기","033100":"제룡전기","062040":"산일전기","229640":"LS에코에너지","298040":"효성중공업","267260":"HD현대일렉트릭"},
}

def get(url, tries=3, timeout=25, enc=None):
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, headers=UA, timeout=timeout)
            if r.status_code == 200 and r.content:
                if enc: r.encoding = enc
                return r
            last = RuntimeError(f"HTTP {r.status_code}")
        except Exception as e:
            last = e
        time.sleep(0.8 * (i + 1))
    raise last

def daily(code, n=45):
    xml = get(f"https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count={n}&requestType=0").text
    out = []
    for m in re.finditer(r'data="(\d{8})\|([\d.]+)\|([\d.]+)\|([\d.]+)\|([\d.]+)\|(\d+)"', xml):
        d, o, h, l, c, v = m.groups()
        out.append((d, float(c), int(v)))
    return out

def news_count(name, days):
    q = urllib.parse.quote(f'"{name}" when:{days}d')
    try:
        x = get(f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko").text
        return x.count("<item>")
    except Exception as e:
        return None

def hot_search():
    """네이버 증권 인기검색종목 상위"""
    out = {}
    try:
        t = get("https://finance.naver.com/sise/lastsearch2.naver", enc="euc-kr").text
        for i, m in enumerate(re.finditer(r'code=(\d{6})"[^>]*>([^<]+)</a>', t), 1):
            out.setdefault(m.group(1), i)
    except Exception as e:
        print("::warning::인기검색 실패", e)
    return out

def board_speed(code):
    """종토방 첫 페이지 글 시각 -> 시간당 글 수(대략)"""
    try:
        t = get(f"https://finance.naver.com/item/board.naver?code={code}", enc="euc-kr").text
        ds = re.findall(r'(\d{4}\.\d{2}\.\d{2} \d{2}:\d{2})', t)
        ts = sorted(dt.datetime.strptime(x, "%Y.%m.%d %H:%M") for x in ds)
        if len(ts) < 5: return None
        hrs = max((ts[-1] - ts[0]).total_seconds() / 3600, 0.05)
        return round(len(ts) / hrs, 1)
    except Exception:
        return None

def one(item):
    grp, code, name = item
    r = {"grp": grp, "code": code, "name": name}
    try:
        s = daily(code)
        val = [c * v / 1e8 for _, c, v in s]  # 억원
        r["last"] = s[-1][1]; r["last_d"] = s[-1][0]
        r["v5"] = round(sum(val[-5:]) / 5); r["v20"] = round(sum(val[-20:]) / 20)
        r["v1"] = round(val[-1])
        r["ret5"] = round((s[-1][1] / s[-6][1] - 1) * 100, 1); r["ret20"] = round((s[-1][1] / s[-21][1] - 1) * 100, 1)
        r["hi_gap"] = round((s[-1][1] / max(c for _, c, _ in s) - 1) * 100, 1)
    except Exception as e:
        r["err"] = str(e)
    r["news7"] = news_count(name, 7); r["news30"] = news_count(name, 30)
    r["board_per_h"] = board_speed(code)
    return r

def main():
    hs = hot_search()
    items = [(g, c, n) for g, d in CAND.items() for c, n in d.items()]
    with ThreadPoolExecutor(5) as ex:
        res = list(ex.map(one, items))
    for r in res:
        r["hot_rank"] = hs.get(r["code"])
    json.dump({"generated": dt.datetime.now(KST).isoformat(timespec="seconds"), "hot_top": len(hs), "items": res},
              open("popular_raw.json", "w"), ensure_ascii=False, indent=1)
    print(len(res), "ok", sum(1 for r in res if "err" in r), "err")

if __name__ == "__main__":
    main()
