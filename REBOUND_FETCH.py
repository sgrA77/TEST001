#!/usr/bin/env python3
"""REBOUND_FETCH.py - '하락 후 반등 분석'용 원시 일봉 종가 수집 (GitHub Actions 1회성/수동 실행)

미국: S&P500 + 나스닥100(위키백과) + 인기·모멘텀 종목 + 대시보드 MARKET 종목 + 기준 ETF/지수 (야후 chart, 1년)
국내: 코스피·코스닥 시총 CAP_MIN 이상 보통주 (네이버 증권 일봉) + 업종
결과: rebound_prices.json  → 'rebound-data' 브랜치(워크플로가 푸시)
"""
import io, json, re, sys, time, datetime as dt, urllib.request
from concurrent.futures import ThreadPoolExecutor
import requests

UA = {"User-Agent": "Mozilla/5.0"}
KST = dt.timezone(dt.timedelta(hours=9))
CAP_MIN = 1500        # 국내 시총(억원) 하한
KR_DAYS = 300         # 네이버 일봉 개수

REF_US = ["SPY", "QQQ", "QLD", "TQQQ", "SPXL", "SMH", "SOXX", "SOXL", "NVDL", "^SOX", "^NDX", "^GSPC", "^VIX", "IGV", "AIQ", "BOTZ"]
REF_KR = {"^KS11": "코스피", "^KQ11": "코스닥"}
EXTRA_US = """IONQ RGTI QBTS QUBT RKLB ASTS LUNR RDW OKLO SMR NNE HOOD SOFI AFRM APP TTD CVNA PLTR SOUN BBAI AAOI LITE COHR CRDO ALAB NBIS IREN CIFR MARA RIOT CLSK COIN MSTR UPST JOBY ACHR WOLF ENPH FSLR SEDG RIVN LCID SNDK CRWV MU WDC STX SMCI DELL VRT GEV CEG VST TSM ASML AMAT LRCX KLAC ARM MRVL ANET CIEN INTC AMD AVGO QCOM TXN ON MPWR NVTS POET NVMI ONTO ACLS CAMT AEHR ICHR FORM AMKR COHU PLAB UCTT PENG SKYT RMBS MTSI SITM LSCC SMTC SLAB CRUS SYNA DIOD AOSL ALGM WOLF GFS UMC ASX""".split()


def get(url, tries=3, timeout=25, **kw):
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, headers=UA, timeout=timeout, **kw)
            if r.status_code == 200 and r.text.strip():
                return r
            last = RuntimeError(f"HTTP {r.status_code}")
        except Exception as e:
            last = e
        time.sleep(0.8 * (i + 1))
    raise last


# ---------------- 미국 유니버스 ----------------
def wiki_table(url, key):
    import pandas as pd
    html = get(url).text
    for t in pd.read_html(io.StringIO(html)):
        cols = [str(c) for c in t.columns]
        if any(key in c for c in cols):
            return t
    return None


def us_universe():
    uni = {}
    try:
        t = wiki_table("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", "Symbol")
        for _, r in t.iterrows():
            uni[str(r["Symbol"]).replace(".", "-")] = {"name": str(r["Security"]), "sec": str(r.get("GICS Sector", "")), "sub": str(r.get("GICS Sub-Industry", "")), "grp": "S&P500"}
        print("S&P500", len(uni))
    except Exception as e:
        print("::warning::S&P500 목록 실패", e)
    try:
        t = wiki_table("https://en.wikipedia.org/wiki/Nasdaq-100", "Ticker")
        n = 0
        for _, r in t.iterrows():
            s = str(r["Ticker"]).replace(".", "-")
            if s not in uni:
                uni[s] = {"name": str(r.get("Company", s)), "sec": str(r.get("GICS Sector", "")), "sub": str(r.get("GICS Sub-Industry", "")), "grp": "나스닥100"}; n += 1
        print("NDX 추가", n)
    except Exception as e:
        print("::warning::나스닥100 목록 실패", e)
    for s in EXTRA_US:
        uni.setdefault(s, {"name": s, "sec": "", "sub": "", "grp": "인기·모멘텀"})
    try:
        d = json.load(open("data.json", encoding="utf-8"))
        for sector, items in (d.get("market") or {}).items():
            for name, m in items.items():
                tk = m.get("ticker") or name
                if re.fullmatch(r"[A-Z\-]{1,6}", tk):
                    uni.setdefault(tk, {"name": name, "sec": "", "sub": sector, "grp": "대시보드"})
    except Exception as e:
        print("::warning::data.json 읽기 실패", e)
    for s in REF_US:
        uni[s] = {"name": s, "sec": "", "sub": "", "grp": "기준"}
    return uni


def yahoo_daily(sym):
    for host in ("query1", "query2"):
        try:
            r = get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{sym}?range=1y&interval=1d", tries=2)
            res = r.json()["chart"]["result"][0]
            q = res["indicators"]["quote"][0]["close"]
            ts = res["timestamp"]
            return [(dt.datetime.fromtimestamp(t, dt.timezone(dt.timedelta(hours=-5))).strftime("%Y-%m-%d"), c) for t, c in zip(ts, q) if c is not None], res["meta"]
        except Exception as e:
            last = e
    raise last


# ---------------- 국내 ----------------
def kr_universe():
    out = {}
    for market in ("KOSPI", "KOSDAQ"):
        page = 1
        while page <= 40:
            j = get(f"https://m.stock.naver.com/api/stocks/marketValue/{market}?page={page}&pageSize=100").json()
            items = j.get("stocks") or []
            for it in items:
                if it.get("stockEndType", "stock") != "stock":
                    continue
                code = str(it.get("itemCode", ""))
                if not re.fullmatch(r"\d{6}", code):
                    continue
                try:
                    cap = int(float(str(it.get("marketValue", "")).replace(",", "")))
                except ValueError:
                    continue
                if cap >= CAP_MIN:
                    out[code] = {"name": it.get("stockName", code), "market": market, "cap": cap}
            if len(items) < 100:
                break
            page += 1
            time.sleep(0.15)
    return out


def naver_daily(code, count=KR_DAYS):
    xml = get(f"https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count={count}&requestType=0").text
    res = []
    for d in re.findall(r'<item data="([^"]+)"', xml):
        p = d.split("|")
        if len(p) >= 6 and p[4] not in ("", "0"):
            res.append((dt.datetime.strptime(p[0], "%Y%m%d").strftime("%Y-%m-%d"), float(p[4])))
    return sorted(res)


def kr_sector_names():
    names = {}
    for page in range(1, 6):
        j = get(f"https://m.stock.naver.com/api/stocks/industry?page={page}&pageSize=100").json()
        g = j.get("groups") or []
        for x in g:
            names[str(x["no"])] = x["name"]
        if len(g) < 100:
            break
    return names


def kr_sector(code, names):
    try:
        j = get(f"https://m.stock.naver.com/api/stock/{code}/integration", tries=2).json()
        return names.get(str(j.get("industryCode")), "")
    except Exception:
        return ""


def main():
    t0 = time.time()
    out = {"generated": dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"), "us": {}, "kr": {}}

    # ---- 미국
    uni = us_universe()
    print("US universe", len(uni))

    def wu(sym):
        try:
            rows, meta = yahoo_daily(sym)
            return sym, rows, meta.get("currency", "")
        except Exception as e:
            return sym, None, str(e)[:80]

    us_rows, fails = {}, []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for sym, rows, cur in ex.map(wu, list(uni)):
            if rows and len(rows) > 30:
                us_rows[sym] = rows
            else:
                fails.append(sym)
    cal = sorted({d for rows in us_rows.values() for d, _ in rows})
    idx = {d: i for i, d in enumerate(cal)}
    out["us_dates"] = cal
    for sym, rows in us_rows.items():
        arr = [None] * len(cal)
        for d, c in rows:
            arr[idx[d]] = round(c, 4)
        out["us"][sym] = {**uni[sym], "c": arr}
    print("US ok", len(us_rows), "fail", len(fails), fails[:30])

    # ---- 국내
    kuni = kr_universe()
    print("KR universe", len(kuni))
    names = kr_sector_names()

    def wk(code):
        try:
            return code, naver_daily(code), kr_sector(code, names)
        except Exception as e:
            return code, None, ""

    kr_rows, kfails = {}, []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for code, rows, sec in ex.map(wk, list(kuni)):
            if rows and len(rows) > 30:
                kr_rows[code] = (rows, sec)
            else:
                kfails.append(code)
    # 지수 (야후)
    for sym, nm in REF_KR.items():
        try:
            rows, _ = yahoo_daily(sym)
            kr_rows[sym] = (rows, "지수"); kuni[sym] = {"name": nm, "market": "INDEX", "cap": None}
        except Exception as e:
            print("::warning::", sym, e)
    kcal = sorted({d for rows, _ in kr_rows.values() for d, _ in rows})
    kidx = {d: i for i, d in enumerate(kcal)}
    out["kr_dates"] = kcal
    for code, (rows, sec) in kr_rows.items():
        arr = [None] * len(kcal)
        for d, c in rows:
            arr[kidx[d]] = round(c, 2)
        out["kr"][code] = {**kuni[code], "sec": sec, "c": arr}
    print("KR ok", len(kr_rows), "fail", len(kfails))
    json.dump(out, open("rebound_prices.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("done", round(time.time() - t0), "s")


if __name__ == "__main__":
    main()
