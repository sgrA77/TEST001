#!/usr/bin/env python3
"""MA.py - 주봉 이동평균선(MA60·MA120) 추적 (GitHub Actions, API 키 불필요)

- 대상: ma_watch.json 의 items(직접 관리: 차트 포함) + data.json 의 MARKET·성장률 카드 종목 전체(자동, 차트 없음) + pinned.json 종목
- 야후 파이낸스 chart API 주봉(1wk) 5년 → 주봉 종가로 MA60/MA120 계산
- 마지막 봉은 '이번 주 진행 중인 봉'(현재가 기준)이며 MA에도 포함 (HTS/차트 프로그램 기본과 동일)
- 결과: ma.json   (종목 하나가 실패하면 이전 값 유지, 전부 실패하면 종료코드 1)
"""
import json, os, sys, time, datetime as dt, requests
from concurrent.futures import ThreadPoolExecutor

UA = {"User-Agent": "Mozilla/5.0"}   # TEST001.py와 동일 (긴 UA는 야후가 빈 응답을 줌)
KEEP = 130   # 차트용 최근 주봉 수


def fetch(sym):
    last = None
    for host in ("query1", "query2"):
        for _ in range(2):
            try:
                r = requests.get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{sym}?range=5y&interval=1wk", headers=UA, timeout=25)
                if not r.text.strip():
                    raise RuntimeError(f"빈 응답 HTTP {r.status_code}")
                res = r.json()["chart"]["result"][0]
                q = res["indicators"]["quote"][0]
                bars = [(t, c) for t, c in zip(res["timestamp"], q["close"]) if c is not None]
                return bars, res["meta"]
            except Exception as e:
                last = e; time.sleep(2)
    raise RuntimeError(f"{sym}: {last}")


def sma(vals, n):
    return [round(sum(vals[i - n + 1:i + 1]) / n, 4) if i + 1 >= n else None for i in range(len(vals))]


def is_kr(sym):
    return sym.endswith((".KS", ".KQ")) or sym in ("^KS11", "^KQ11")


def build(sym, tz_off, full=True):
    bars, meta = fetch(sym)
    closes = [c for _, c in bars]
    price = meta.get("regularMarketPrice", closes[-1])
    closes[-1] = price                       # 진행 중인 주봉은 현재가로
    dates = [dt.datetime.utcfromtimestamp(t + tz_off).strftime("%Y-%m-%d") for t, _ in bars]
    m60, m120 = sma(closes, 60), sma(closes, 120)
    out = {"price": round(price, 4), "currency": meta.get("currency", ""),
           "ma60": m60[-1], "ma120": m120[-1], "weeks": len(closes)}
    if full:   # 차트용 시계열은 직접 관리 종목만 (파일 크기 절약)
        out.update(dates=dates[-KEEP:], close=[round(c, 4) for c in closes[-KEEP:]],
                   s60=m60[-KEEP:], s120=m120[-KEEP:])
    return out


def collect_targets():
    """[(symbol, name, group, mas, full)] — 직접 관리 → 핀 → 대시보드 카드 종목 순, 중복 제거"""
    cfg = json.load(open("ma_watch.json", encoding="utf-8"))
    targets, seen = [], set()
    for it in cfg["items"]:
        if it["symbol"] in seen:
            continue
        seen.add(it["symbol"])
        targets.append((it["symbol"], it.get("name", it["symbol"]), it.get("group", ""), it.get("mas", [60, 120]), True))
    try:
        pins = json.load(open("pinned.json", encoding="utf-8")).get("symbols", [])
    except Exception:
        pins = []
    try:
        data = json.load(open("data.json", encoding="utf-8"))
    except Exception:
        data = {}
    extra = []
    for name, g in (data.get("growth") or {}).items():
        if g.get("ticker"):
            extra.append((g["ticker"], name, "지수 성장률 카드"))
    for sector, items in (data.get("market") or {}).items():
        for name, m in items.items():
            extra.append((m.get("ticker") or name, name, sector))
    for sym in pins:
        extra.append((sym, sym, "핀"))
    for sym, name, group in extra:
        if sym in seen:
            continue
        seen.add(sym)
        targets.append((sym, name, group, [120] if is_kr(sym) else [60, 120], False))
    return targets


def main():
    try:
        old = {x["symbol"]: x for x in json.load(open("ma.json", encoding="utf-8")).get("items", [])}
    except Exception:
        old = {}
    now = dt.datetime.utcnow() + dt.timedelta(hours=9)
    targets = collect_targets()

    def work(t):
        sym, name, group, mas, full = t
        try:
            r = build(sym, 9 * 3600 if is_kr(sym) else -5 * 3600, full); r["stale"] = False
        except Exception as e:
            print("[warn]", sym, e)
            if sym not in old:
                return None
            r = old[sym]; r["stale"] = True
        r.update(symbol=sym, name=name, group=group, mas=mas, auto=not full)
        return r

    with ThreadPoolExecutor(max_workers=6) as ex:
        res = list(ex.map(work, targets))
    items = [r for r in res if r]
    ok = sum(1 for r in items if not r["stale"])
    fails = [t[0] for t, r in zip(targets, res) if r is None or r["stale"]]
    if fails:
        print(f"::warning::MA 수집 실패/지연 {len(fails)}건: {', '.join(fails)[:300]}")
    print(f"ok {ok}/{len(targets)}")
    if ok == 0:
        print("[error] 전부 실패 — ma.json 유지"); sys.exit(1)
    json.dump({"updated": now.strftime("%Y-%m-%d %H:%M"), "items": items},
              open("ma.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    main()
