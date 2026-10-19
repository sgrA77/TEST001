#!/usr/bin/env python3
"""MA.py - 주봉/월봉 60·120 이동평균선(MA) 추적 (GitHub Actions, API 키 불필요)

- 대상: ma_watch.json 의 items (종목 추가는 거기에 한 줄 추가)
- 야후 파이낸스 chart API: 주봉(1wk) 10년, 월봉(1mo) 25년 → 봉 종가로 MA60/MA120 계산
- 마지막 봉은 '진행 중인 봉'(이번 주/이번 달, 현재가 기준)이며 MA에도 포함 (HTS/차트 프로그램 기본과 동일)
- 결과: ma.json   (한 종목이라도 실패하면 이전 값 유지, 전부 실패하면 종료코드 1)
"""
import json, sys, time, datetime as dt, requests

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
PERIODS = {"week": ("1wk", "10y", "주봉"), "month": ("1mo", "25y", "월봉")}
WINDOWS = (60, 120)
KEEP = {"week": 200, "month": 160}   # 차트에 쓸 최근 봉 수


def fetch(sym, interval, rng):
    last = None
    for host in ("query1", "query2"):
        for _ in range(2):
            try:
                u = f"https://{host}.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval={interval}"
                r = requests.get(u, headers=UA, timeout=25)
                res = r.json()["chart"]["result"][0]
                ts = res["timestamp"]; q = res["indicators"]["quote"][0]
                bars = [(t, c) for t, c in zip(ts, q["close"]) if c is not None]
                meta = res["meta"]
                return bars, meta
            except Exception as e:
                last = e; time.sleep(2)
    raise RuntimeError(f"{sym} {interval}: {last}")


def sma(vals, n):
    out = []
    for i in range(len(vals)):
        out.append(round(sum(vals[i - n + 1:i + 1]) / n, 4) if i + 1 >= n else None)
    return out


def build(sym, tz_off):
    out = {}
    price = None
    for key, (iv, rng, label) in PERIODS.items():
        bars, meta = fetch(sym, iv, rng)
        closes = [c for _, c in bars]
        price = meta.get("regularMarketPrice", closes[-1])
        closes[-1] = price                       # 진행 중인 봉은 현재가로
        dates = [dt.datetime.utcfromtimestamp(t + tz_off).strftime("%Y-%m-%d") for t, _ in bars]
        m = {n: sma(closes, n) for n in WINDOWS}
        k = KEEP[key]
        d = {"label": label, "bars": len(closes), "last_date": dates[-1],
             "dates": dates[-k:], "close": [round(c, 4) for c in closes[-k:]]}
        for n in WINDOWS:
            cur = m[n][-1]
            d[f"ma{n}"] = m[n][-k:]
            d[f"ma{n}_now"] = cur
            d[f"gap{n}"] = round((price / cur - 1) * 100, 2) if cur else None   # 현재가가 MA 대비 몇 % 위(+)/아래(−)
        out[key] = d
    cur = meta
    return {"price": round(price, 4), "currency": cur.get("currency", ""),
            "exch_tz": cur.get("exchangeTimezoneName", ""), "periods": out}


def main():
    cfg = json.load(open("ma_watch.json", encoding="utf-8"))
    try:
        old = {x["symbol"]: x for x in json.load(open("ma.json", encoding="utf-8")).get("items", [])}
    except Exception:
        old = {}
    now = dt.datetime.utcnow() + dt.timedelta(hours=9)
    items, ok = [], 0
    for it in cfg["items"]:
        sym = it["symbol"]
        off = 9 * 3600 if (sym.endswith((".KS", ".KQ")) or sym in ("^KS11", "^KQ11")) else -5 * 3600
        try:
            r = build(sym, off); ok += 1
            r.update(symbol=sym, name=it.get("name", sym), group=it.get("group", ""))
            items.append(r); print("ok", sym, r["price"])
        except Exception as e:
            print("[warn]", sym, e); print(f"::error::{sym} {str(e)[:300]}")
            if sym in old:
                o = old[sym]; o["stale"] = True; items.append(o)
    if ok == 0:
        print("[error] 전부 실패 — ma.json 유지"); sys.exit(1)
    json.dump({"updated": now.strftime("%Y-%m-%d %H:%M"), "items": items},
              open("ma.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    main()
