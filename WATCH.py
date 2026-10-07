#!/usr/bin/env python3
"""WATCH.py - 국내 급등 종목 주간 모니터링 (GitHub Actions에서 실행, API 키 불필요)

기준
  - 주간 = 달력상 월~금. 휴장일이 있으면 그 주의 마지막 거래일 종가를 사용.
  - 주간 변동률 = (그 주 마지막 거래일 종가 / 직전 주 마지막 거래일 종가 - 1) * 100
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
SMALL_CAP_EOK = 1000     # '소형주' 표시 기준(시가총액, 억원)
VOL_SPIKE     = 3.0      # '거래량 급증' 표시 기준(최근 4주 평균 대비 배수)
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
    """candles: [(date, close, volume)] 오름차순. 반환: dict 또는 None"""
    inweek = [c for c in candles if mon <= c[0] <= fri and c[1]]
    before = [c for c in candles if c[0] < mon and c[1]]
    if not inweek or not before: return None
    last, base = inweek[-1], before[-1]
    if base[1] <= 0: return None
    vol_week = sum(c[2] for c in inweek)
    prev4 = before[-20:]                              # 직전 약 4주(거래일 20개)
    avg_daily = (sum(c[2] for c in prev4) / len(prev4)) if prev4 else 0
    vol_ratio = (vol_week / len(inweek)) / avg_daily if avg_daily > 0 else None
    return {"close": last[1], "prev_close": base[1], "chg": round((last[1] / base[1] - 1) * 100, 2),
            "last_day": last[0].isoformat(), "days": len(inweek),
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

def candles_naver(code):
    xml = http("https://fchart.stock.naver.com/sise.nhn?symbol=%s&timeframe=day&count=45&requestType=0" % code)
    res = []
    for d in re.findall(r'<item data="([^"]+)"', xml):
        p = d.split("|")
        if len(p) >= 6 and p[4] not in ("", "0"):
            res.append((dt.datetime.strptime(p[0], "%Y%m%d").date(), float(p[4]), float(p[5] or 0)))
    return sorted(res)

def candles_yahoo(code, market):
    sfx = ".KS" if market == "KOSPI" else ".KQ"
    j = json.loads(http("https://query1.finance.yahoo.com/v8/finance/chart/%s%s?range=3mo&interval=1d" % (code, sfx)))
    r = j["chart"]["result"][0]; q = r["indicators"]["quote"][0]; res = []
    for t, c, v in zip(r["timestamp"], q["close"], q["volume"]):
        if c: res.append((dt.datetime.fromtimestamp(t, KST).date(), float(c), float(v or 0)))
    return sorted(res)

def fetch_candles(s):
    try:
        c = candles_naver(s["code"])
        if c: return c
    except Exception: pass
    try: return candles_yahoo(s["code"], s["market"])
    except Exception: return None

# --------------------------- 실행 ---------------------------
def run(stocks, fetch, mon, fri):
    ok = fail = 0; rows = []
    def work(s):
        c = fetch(s)
        return s, c
    with ThreadPoolExecutor(WORKERS) as ex:
        for s, c in ex.map(work, stocks.values()):
            if c is None: fail += 1; continue
            w = weekly_change(c, mon, fri)
            if w is None: fail += 1; continue
            ok += 1
            th = THRESH_KOSPI if s["market"] == "KOSPI" else THRESH_KOSDAQ
            if w["chg"] >= th:
                flags = []
                if s["cap"] is not None and s["cap"] < SMALL_CAP_EOK: flags.append("소형주")
                if w["vol_ratio"] and w["vol_ratio"] >= VOL_SPIKE: flags.append("거래량 급증")
                if "스팩" in s["name"]: flags.append("스팩")
                rows.append({"code": s["code"], "name": s["name"], "market": s["market"], "price": int(w["close"]),
                             "prev_price": int(w["prev_close"]), "chg": w["chg"], "cap_eok": s["cap"],
                             "vol_ratio": w["vol_ratio"], "flags": flags, "last_day": w["last_day"]})
    rows.sort(key=lambda r: -r["chg"])
    return rows, ok, fail

def build(rows, ok, fail, mon, fri, now):
    return {"version": 1, "week_start": mon.isoformat(), "week_end": fri.isoformat(),
            "label": "%s ~ %s" % (mon.strftime("%Y.%m.%d"), fri.strftime("%m.%d")),
            "generated_at": now.isoformat(timespec="seconds"),
            "thresholds": {"KOSPI": THRESH_KOSPI, "KOSDAQ": THRESH_KOSDAQ},
            "scanned": ok, "failed": fail,
            "kospi": [r for r in rows if r["market"] == "KOSPI"],
            "kosdaq": [r for r in rows if r["market"] == "KOSDAQ"]}

def save(d):
    os.makedirs(OUT_DIR, exist_ok=True)
    for p in (os.path.join(ROOT, "watch.json"), os.path.join(OUT_DIR, d["week_end"] + ".json")):
        json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    ip = os.path.join(OUT_DIR, "index.json")
    try: idx = json.load(open(ip, encoding="utf-8"))
    except Exception: idx = []
    idx = [x for x in idx if x.get("week_end") != d["week_end"]]
    idx.append({"week_end": d["week_end"], "label": d["label"], "kospi": len(d["kospi"]), "kosdaq": len(d["kosdaq"]),
                "top": [r["name"] for r in sorted(d["kospi"] + d["kosdaq"], key=lambda r: -r["chg"])[:3]]})
    idx.sort(key=lambda x: x["week_end"])
    json.dump(idx, open(ip, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def probe():
    urls = [
     "https://m.stock.naver.com/api/stocks/marketValue/KOSPI?page=1&pageSize=3",
     "https://m.stock.naver.com/api/stocks/marketValue/KOSDAQ?page=1&pageSize=3",
     "https://m.stock.naver.com/api/stock/005930/price?pageSize=3&page=1",
     "https://api.stock.naver.com/chart/domestic/item/005930/day?startDateTime=20260925&endDateTime=20261005",
     "https://fchart.stock.naver.com/sise.nhn?symbol=005930&timeframe=day&count=3&requestType=0",
     "https://query1.finance.yahoo.com/v8/finance/chart/005930.KS?range=5d&interval=1d",
    ]
    for u in urls:
        try:
            t = http(u, tries=1)
            log("::warning title=probe OK::%s len=%d %r" % (u[:80], len(t), t[:260].replace("\n", " ")))
        except Exception as e:
            log("::warning title=probe FAIL::%s %r" % (u[:80], e))

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
    rows, ok, fail = run(stocks, fetch_candles, mon, fri)
    log("[info] 수집 성공 %d / 실패 %d" % (ok, fail))
    if ok / max(1, ok + fail) < MIN_OK_RATIO: raise RuntimeError("수집 성공률 부족 (%d/%d)" % (ok, ok + fail))
    d = build(rows, ok, fail, mon, fri, now); save(d)
    log("[ok] %s  코스피 %d개 / 코스닥 %d개" % (d["label"], len(d["kospi"]), len(d["kosdaq"])))

if __name__ == "__main__":
    try: main()
    except Exception as e:
        log("[error] %s" % e)
        log("::error title=WATCH.py::%s" % str(e).replace("\n", " ")[:900])   # Actions 화면/API 주석으로 노출
        sys.exit(1)
