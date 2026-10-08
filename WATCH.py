#!/usr/bin/env python3
"""WATCH.py - 국내 급등 종목 주간 모니터링 (GitHub Actions에서 실행, API 키 불필요)

기준
  - 주간 = 달력상 월~금. 휴장일이 있으면 그 주의 마지막 거래일 종가를 사용.
  - 주간 변동률 = (그 주 마지막 거래일 종가 / 직전 주 마지막 거래일 종가 - 1) * 100
  - 매집 의심 = (최근 ACCUM_LOOKBACK_WEEKS주 중 주간 +ACCUM_PAST_SURGE% 이상 마감한 주가 있는 종목) 중 그 주 종가가 주봉 시작가(첫 거래일 시가) 대비 ±ACCUM_BAND% 이내이고, 주중 최고가가 시작가 대비 +ACCUM_MAX_UP% 이하.
  - 정렬은 업종별로 묶고 업종 안에서 시가총액 큰 순. 업종은 네이버 증권 업종 분류.
  - 대상 주 = 가장 최근에 끝난 주. (월~금에 실행하면 '지난주', 토/일에 실행하면 '방금 끝난 주')
  - 코스피 THRESH_KOSPI% 이상, 코스닥 THRESH_KOSDAQ% 이상 상승 마감 종목만 수록.
사용:  python WATCH.py            (자동)   |   python WATCH.py --week 2026-10-02   (그 주 금요일 날짜 지정)
실패(수집률 낮음)하면 [error] 를 출력하고 종료코드 1 - 기존 watch.json 은 건드리지 않음.
"""
import os, re, sys, json, time, datetime as dt, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

# ===================== 설정 =====================
THRESH_KOSPI  = 20.0     # 코스피 주간 상승률 기준(%)
THRESH_KOSDAQ = 30.0     # 코스닥 주간 상승률 기준(%)
MIN_OK_RATIO  = 0.90     # 수집 성공률이 이보다 낮으면 실패 처리
WORKERS       = 12
ACCUM_BAND    = 3.0      # 매집 의심: 주봉 시작가(그 주 첫 거래일 시가) 대비 종가 변동이 ±이 값(%) 이내
ACCUM_MAX_UP  = 10.0     # 매집 의심: 주중 최고가가 주봉 시작가 대비 +이 값(%) 이하 (주봉 최대 상승률)
ACCUM_LOOKBACK_WEEKS = 26   # 매집 의심: 과거 확인 기간(주) ≈ 6개월
ACCUM_PAST_SURGE = 30.0     # 매집 의심: 과거 기간 중 주간 상승률(직전 주 종가 대비)이 이 값(%) 이상 마감한 주가 1번 이상 있어야 함
ACCUM_MIN_CAP = 1000     # 매집 의심: 시가총액(억원) 이 값 이하는 제외
SURGE_MIN_CAP = 2000     # 급등 목록: 시가총액(억원) 이 값 이하는 제외
ACCUM_VOL     = 0.0      # 매집 의심: 거래량 배수 조건 (0 이면 사용 안 함, 예: 3.0 이면 직전 4주 일평균의 3배 이상만)
SMALL_CAP_EOK = 1000     # '소형주' 표시 기준(시가총액, 억원)
# --- 테마(업종 묶음) 설정: 네이버 업종명 -> 보고 싶은 테마. 앞쪽일수록 화면 상단 ---
THEME_ORDER = ["반도체", "AI", "방산", "우주항공", "친환경에너지", "은행", "증권", "석유와가스"]
ACCUM_THEMES = THEME_ORDER + ["제약", "생명과학도구", "조선", "유류"]        # 매집 의심은 이 테마만 모니터링
THEME_MAP = {
    "반도체와반도체장비": "반도체",
    "소프트웨어": "AI", "IT서비스": "AI", "컴퓨터와주변기기": "AI",
    "우주항공과국방": "방산",
    "에너지장비및서비스": "친환경에너지", "전기장비": "친환경에너지", "전기유틸리티": "친환경에너지", "복합유틸리티": "친환경에너지",
    "은행": "은행", "증권": "증권", "석유와가스": "석유와가스",
    "가스유틸리티": "유류",
    "제약": "제약", "생명과학도구및서비스": "생명과학도구", "조선": "조선",
}
OIL_NAMES = ["석유", "정유", "유화", "오일", "에너비스", "원유"]   # 이름에 포함되면 '유류' 테마(종목이 있을 때만 표시됨)
SPACE_NAMES = ["켄코아", "이노스페이스", "쎄트렉", "AP위성", "컨텍", "인텔리안", "한화시스템", "한화에어로", "페리지", "나라스페이스", "제노코", "스페이스"]  # 이름에 포함되면 '우주항공'(SpaceX 관련 국내 후보)
# ================================================
ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "watch")
KST = dt.timezone(dt.timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}

def log(*a): print(*a, flush=True)

def http(url, enc="utf-8", tries=3, timeout=20):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode(enc, "replace")
        except Exception as e:
            last = e; time.sleep(0.6 * (i + 1))
    raise last

# --------------------------- 주(週) 계산 ---------------------------
def target_week(today, friday=None):
    """(월요일, 금요일) 날짜 반환."""
    if friday:
        fri = dt.date.fromisoformat(friday)
        return fri - dt.timedelta(days=4), fri
    monday = today - dt.timedelta(days=today.weekday())
    if today.weekday() >= 5: mon = monday          # 토/일 실행 -> 방금 끝난 주
    else: mon = monday - dt.timedelta(days=7)      # 월~금 실행 -> 지난주
    return mon, mon + dt.timedelta(days=4)

def weekly_change(candles, mon, fri):
    """candles: [(date, open, high, low, close, volume)] 오름차순. 반환: dict 또는 None"""
    inweek = [c for c in candles if mon <= c[0] <= fri and c[4]]
    before = [c for c in candles if c[0] < mon and c[4]]
    if not inweek or not before: return None
    first, last, base = inweek[0], inweek[-1], before[-1]
    if base[4] <= 0: return None
    wopen = first[1] or first[4]
    vol_week = sum(c[5] for c in inweek)
    prev4 = before[-20:]                              # 직전 약 4주(거래일 20개)
    avg_daily = (sum(c[5] for c in prev4) / len(prev4)) if prev4 else 0
    vol_ratio = (vol_week / len(inweek)) / avg_daily if avg_daily > 0 else None
    hi = max(c[2] or c[4] for c in inweek); lo = min(c[3] or c[4] for c in inweek)
    return {"close": last[4], "prev_close": base[4], "chg": round((last[4] / base[4] - 1) * 100, 2),
            "week_open": wopen, "open_chg": round((last[4] / wopen - 1) * 100, 2),
            "range": round((hi - lo) / wopen * 100, 1) if wopen else None,
            "max_up": round((hi / wopen - 1) * 100, 1) if wopen else None,
            "last_day": last[0].isoformat(), "days": len(inweek), "vol_week": vol_week,
            "vol_ratio": round(vol_ratio, 1) if vol_ratio else None}

# --------------------------- 데이터 수집 ---------------------------
def list_stocks():
    """네이버 증권 모바일 API(시가총액 순)에서 코스피/코스닥 보통주 목록(코드, 이름, 시총 억원)."""
    out = {}
    for market in ("KOSPI", "KOSDAQ"):
        page = 1
        while page <= 80:
            j = json.loads(http("https://m.stock.naver.com/api/stocks/marketValue/%s?page=%d&pageSize=100" % (market, page)))
            items = j.get("stocks") or []
            for it in items:
                if it.get("stockEndType", "stock") != "stock": continue      # ETF/ETN 등 제외
                code = str(it.get("itemCode", ""))
                if not re.fullmatch(r"\d{6}", code): continue
                try: cap = int(float(str(it.get("marketValue", "")).replace(",", "")))
                except ValueError: cap = None
                out[code] = {"code": code, "name": it.get("stockName", code), "market": market, "cap": cap}
            if len(items) < 100: break
            page += 1
            time.sleep(0.15)
    return out

def candles_naver(code, count=45):
    xml = http("https://fchart.stock.naver.com/sise.nhn?symbol=%s&timeframe=day&count=%d&requestType=0" % (code, count))
    res = []
    for d in re.findall(r'<item data="([^"]+)"', xml):
        p = d.split("|")
        if len(p) >= 6 and p[4] not in ("", "0"):
            res.append((dt.datetime.strptime(p[0], "%Y%m%d").date(), float(p[1] or 0), float(p[2] or 0), float(p[3] or 0), float(p[4]), float(p[5] or 0)))
    return sorted(res)

def candles_yahoo(code, market):
    sfx = ".KS" if market == "KOSPI" else ".KQ"
    j = json.loads(http("https://query1.finance.yahoo.com/v8/finance/chart/%s%s?range=3mo&interval=1d" % (code, sfx)))
    r = j["chart"]["result"][0]; q = r["indicators"]["quote"][0]; res = []
    for t, o, h, l, c, v in zip(r["timestamp"], q["open"], q["high"], q["low"], q["close"], q["volume"]):
        if c: res.append((dt.datetime.fromtimestamp(t, KST).date(), float(o or 0), float(h or 0), float(l or 0), float(c), float(v or 0)))
    return sorted(res)

def fetch_candles(s):
    try:
        c = candles_naver(s["code"])
        if c: return c
    except Exception: pass
    try: return candles_yahoo(s["code"], s["market"])
    except Exception: return None

# --------------------------- 6개월 이력 ---------------------------
def weekly_series(candles):
    """일봉 -> 주봉 [(월요일, 시가, 고가, 저가, 종가)] 오름차순"""
    wk = {}
    for d, o, h, l, c, v in candles:
        if not c: continue
        m = d - dt.timedelta(days=d.weekday())
        if m not in wk: wk[m] = [o or c, h or c, l or c, c]
        else:
            w = wk[m]; w[1] = max(w[1], h or c); w[2] = min(w[2], l or c) if l else w[2]; w[3] = c
    return [(m, w[0], w[1], w[2], w[3]) for m, w in sorted(wk.items())]

def history_stats(candles, mon):
    """대상 주(mon) 직전 ACCUM_LOOKBACK_WEEKS주: +30% 이상 마감 횟수, ±ACCUM_BAND% 이내 마감 횟수."""
    ser = weekly_series(candles)
    lo = mon - dt.timedelta(weeks=ACCUM_LOOKBACK_WEEKS)
    surge_n = flat_n = n = 0; last = None; best = None
    for i in range(1, len(ser)):
        m, o, h, l, c = ser[i]
        if m < lo or m >= mon: continue
        n += 1
        chg = (c / ser[i - 1][4] - 1) * 100 if ser[i - 1][4] else 0
        if chg >= ACCUM_PAST_SURGE:
            surge_n += 1; last = (m + dt.timedelta(days=4)).isoformat()
            best = chg if best is None else max(best, chg)
        if o and abs(c / o - 1) * 100 <= ACCUM_BAND: flat_n += 1
    return {"surge_n": surge_n, "surge_last": last, "surge_max": round(best, 1) if best is not None else None,
            "flat_n": flat_n, "hist_weeks": n}

def fetch_history(s):
    try:
        c = candles_naver(s["code"], 170)
        if c: return c
    except Exception: pass
    try: return candles_yahoo(s["code"], s["market"])
    except Exception: return None

# --------------------------- 업종 ---------------------------
def industry_names():
    names = {}
    for page in range(1, 6):
        j = json.loads(http("https://m.stock.naver.com/api/stocks/industry?page=%d&pageSize=100" % page))
        g = j.get("groups") or []
        for x in g: names[str(x["no"])] = x["name"]
        if len(g) < 100: break
    return names

def sector_of(code, names):
    try:
        j = json.loads(http("https://m.stock.naver.com/api/stock/%s/integration" % code, tries=2))
        return names.get(str(j.get("industryCode")), "") or "–"
    except Exception:
        return "–"

def theme_of(name, sector):
    if any(k in name for k in SPACE_NAMES): return "우주항공"
    if any(k in name for k in OIL_NAMES): return "유류"
    return THEME_MAP.get(sector, sector)

KEYS = ("상한가", "급등", "강세", "수주", "계약", "승인", "인수", "공급", "실적", "임상", "특허", "협력", "MOU", "투자")

def news_of(code, mon, fri):
    """그 주(월~다음날) 안에 나온 종목 뉴스 중 상승 원인으로 보이는 제목 1개."""
    try:
        j = json.loads(http("https://m.stock.naver.com/api/news/stock/%s?pageSize=20&page=1" % code, tries=2))
    except Exception:
        return []
    items = []
    for g in j if isinstance(j, list) else []:
        items += g.get("items") or []
    lo = mon.strftime("%Y%m%d") + "0000"; hi = (fri + dt.timedelta(days=2)).strftime("%Y%m%d") + "2359"
    inw = [x for x in items if lo <= str(x.get("datetime", "")) <= hi] or items[:5]
    inw.sort(key=lambda x: (-any(k in (x.get("title") or "") for k in KEYS), -int(x.get("datetime") or 0)))
    out = []
    for x in inw[:1]:
        t = re.sub(r"<[^>]+>", "", x.get("titleFull") or x.get("title") or "").strip()
        d = str(x.get("datetime", ""))
        out.append({"title": t, "url": x.get("mobileNewsUrl", ""), "office": x.get("officeName", ""),
                    "date": "%s-%s-%s" % (d[:4], d[4:6], d[6:8]) if len(d) >= 8 else ""})
    return out

def add_sectors(rows):
    if not rows: return
    try: names = industry_names()
    except Exception as e:
        log("[warn] 업종 목록 수집 실패: %r" % e); names = {}
    with ThreadPoolExecutor(8) as ex:
        for r, sec in zip(rows, ex.map(lambda r: sector_of(r["code"], names), rows)):
            r["sector"] = sec; r["theme"] = theme_of(r["name"], sec)

def add_news(rows, mon, fri):
    with ThreadPoolExecutor(8) as ex:
        for r, n in zip(rows, ex.map(lambda r: news_of(r["code"], mon, fri), rows)): r["news"] = n

# --------------------------- 실행 ---------------------------
def cap_key(r): return -(r["cap_eok"] if r["cap_eok"] is not None else -1)

def run(stocks, fetch, mon, fri):
    ok = fail = 0; surge = []; accum = []; accum_novol = 0
    def work(s): return s, fetch(s)
    with ThreadPoolExecutor(WORKERS) as ex:
        for s, c in ex.map(work, stocks.values()):
            if c is None: fail += 1; continue
            w = weekly_change(c, mon, fri)
            if w is None: fail += 1; continue
            ok += 1
            base = {"code": s["code"], "name": s["name"], "market": s["market"], "price": int(w["close"]),
                    "cap_eok": s["cap"], "vol_ratio": w["vol_ratio"], "last_day": w["last_day"]}
            flags = []
            if s["cap"] is not None and s["cap"] < SMALL_CAP_EOK: flags.append("소형주")
            if "스팩" in s["name"]: flags.append("스팩")
            th = THRESH_KOSPI if s["market"] == "KOSPI" else THRESH_KOSDAQ
            if w["chg"] >= th and (s["cap"] is None or s["cap"] > SURGE_MIN_CAP):
                surge.append(dict(base, prev_price=int(w["prev_close"]), chg=w["chg"], flags=flags))
            if w["chg"] < th and w["vol_week"] > 0 and abs(w["open_chg"]) <= ACCUM_BAND and w["max_up"] is not None and w["max_up"] <= ACCUM_MAX_UP:   # 급등 종목은 제외(중복 방지)
                accum_novol += 1
                if not ACCUM_VOL or (w["vol_ratio"] and w["vol_ratio"] >= ACCUM_VOL):
                    accum.append(dict(base, open_price=int(w["week_open"]), open_chg=w["open_chg"], max_up=w["max_up"], range=w["range"], flags=flags))
    add_sectors(surge + accum)
    accum = [r for r in accum if r["theme"] in ACCUM_THEMES and (r["cap_eok"] or 0) > ACCUM_MIN_CAP]
    kept = []
    def hwork(r): return r, fetch_history(stocks[r["code"]])
    with ThreadPoolExecutor(WORKERS) as ex:
        for r, c in ex.map(hwork, accum):
            if c is None: continue
            hs = history_stats(c, mon)
            if hs["surge_n"] >= 1: r.update(hs); kept.append(r)
    accum_before_hist = len(accum); accum = kept
    accum.sort(key=lambda r: (-r["surge_n"], cap_key(r)))   # +30% 마감 횟수 많은 순 (같으면 시총 큰 순)
    def tkey(r):
        t = r["theme"]; return (THEME_ORDER.index(t) if t in THEME_ORDER else 99, t, cap_key(r))
    surge.sort(key=tkey)
    add_news(surge, mon, fri)
    return surge, accum, accum_before_hist, ok, fail

def build(surge, accum, accum_novol, ok, fail, mon, fri, now):
    return {"version": 3, "week_start": mon.isoformat(), "week_end": fri.isoformat(),
            "label": "%s ~ %s" % (mon.strftime("%Y.%m.%d"), fri.strftime("%m.%d")),
            "generated_at": now.isoformat(timespec="seconds"),
            "thresholds": {"KOSPI": THRESH_KOSPI, "KOSDAQ": THRESH_KOSDAQ, "ACCUM_BAND": ACCUM_BAND, "ACCUM_MAX_UP": ACCUM_MAX_UP, "ACCUM_VOL": ACCUM_VOL, "ACCUM_MIN_CAP": ACCUM_MIN_CAP, "ACCUM_LOOKBACK_WEEKS": ACCUM_LOOKBACK_WEEKS, "ACCUM_PAST_SURGE": ACCUM_PAST_SURGE, "THEME_ORDER": THEME_ORDER, "ACCUM_THEMES": ACCUM_THEMES, "SURGE_MIN_CAP": SURGE_MIN_CAP},
            "scanned": ok, "failed": fail, "accum_before_history_filter": accum_novol,
            "kospi": [r for r in surge if r["market"] == "KOSPI"],
            "kosdaq": [r for r in surge if r["market"] == "KOSDAQ"],
            "accum": accum}

def save(d):
    os.makedirs(OUT_DIR, exist_ok=True)
    for p in (os.path.join(ROOT, "watch.json"), os.path.join(OUT_DIR, d["week_end"] + ".json")):
        json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    ip = os.path.join(OUT_DIR, "index.json")
    try: idx = json.load(open(ip, encoding="utf-8"))
    except Exception: idx = []
    idx = [x for x in idx if x.get("week_end") != d["week_end"]]
    idx.append({"week_end": d["week_end"], "label": d["label"], "kospi": len(d["kospi"]), "kosdaq": len(d["kosdaq"]), "accum": len(d.get("accum", [])),
                "top": [r["name"] for r in sorted(d["kospi"] + d["kosdaq"], key=lambda r: -r["chg"])[:3]]})
    idx.sort(key=lambda x: x["week_end"])
    json.dump(idx, open(ip, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def probe():
    try:
        names = industry_names()
        t = " | ".join("%s:%s" % (k, v) for k, v in sorted(names.items(), key=lambda x: int(x[0])))
        for i in range(0, len(t), 800): log("::warning title=industries %d::%s" % (i // 800, t[i:i + 800]))
    except Exception as e: log("::warning title=ind FAIL::%r" % e)
    for u in ["https://m.stock.naver.com/api/news/stock/196170?pageSize=3&page=1",
              "https://m.stock.naver.com/api/stock/196170/news?pageSize=3&page=1"]:
        try:
            t = http(u, tries=1)
            log("::warning title=news OK::%s len=%d %r" % (u[26:80], len(t), t[:600].replace("\n", " ")))
        except Exception as e: log("::warning title=news FAIL::%s %r" % (u[26:80], e))

def main():
    if "--probe" in sys.argv: return probe()
    now = dt.datetime.now(KST)
    friday = sys.argv[sys.argv.index("--week") + 1] if "--week" in sys.argv else None
    mon, fri = target_week(now.date(), friday)
    log("[info] 대상 주: %s ~ %s" % (mon, fri))
    try: stocks = list_stocks()
    except Exception as e: raise RuntimeError("종목 목록 요청 실패: %r" % e)
    log("[info] 종목 수: %d (코스피 %d / 코스닥 %d)" % (len(stocks), sum(1 for s in stocks.values() if s["market"] == "KOSPI"),
                                                  sum(1 for s in stocks.values() if s["market"] == "KOSDAQ")))
    if len(stocks) < 1500:
        h = http("https://m.stock.naver.com/api/stocks/marketValue/KOSPI?page=1&pageSize=3")
        i = h.find("code=")
        raise RuntimeError("종목 목록 수집 실패(%d개) len=%d title=%r pgRR=%s ctx=%r" % (len(stocks), len(h),
                           re.findall(r"<title>(.*?)</title>", h, re.S)[:1], "pgRR" in h, h[max(0, i - 120):i + 200] if i >= 0 else h[:300]))
    surge, accum, accum_novol, ok, fail = run(stocks, fetch_candles, mon, fri)
    log("[info] 수집 성공 %d / 실패 %d, 매집 후보(거래량 조건 제외) %d" % (ok, fail, accum_novol))
    if ok / max(1, ok + fail) < MIN_OK_RATIO: raise RuntimeError("수집 성공률 부족 (%d/%d)" % (ok, ok + fail))
    d = build(surge, accum, accum_novol, ok, fail, mon, fri, now); save(d)
    log("[ok] %s  코스피 %d / 코스닥 %d / 매집 의심 %d" % (d["label"], len(d["kospi"]), len(d["kosdaq"]), len(d["accum"])))

if __name__ == "__main__":
    try: main()
    except Exception as e:
        log("[error] %s" % e)
        log("::error title=WATCH.py::%s" % str(e).replace("\n", " ")[:900])   # Actions 화면/API 주석으로 노출
        sys.exit(1)
