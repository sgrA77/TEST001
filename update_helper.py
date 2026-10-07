#!/usr/bin/env python3
"""update_helper.py - 예약작업(Claude)이 만든 Outlook 초안을 검증/저장하는 보조 스크립트. API 호출 없음.

사용법
  python update_helper.py prev                 # 이전 Daily 요약(최대 7개)을 출력 -> view_changed 작성용
  python update_helper.py save daily.json      # 초안 검증 후 outlook.json / outlook/날짜.json / index.json 갱신
  python update_helper.py weekly-input         # Weekly 작성용 Daily 요약 출력
  python update_helper.py save-weekly weekly.json
실패하면 [error]를 출력하고 종료코드 1 (기존 파일은 건드리지 않음).
"""
import os, re, json, sys, datetime as dt

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_LATEST = os.path.join(ROOT, "outlook.json")
OUT_DIR = os.path.join(ROOT, "outlook")
KEEP_PREV = 7
KST = dt.timezone(dt.timedelta(hours=9))

def log(*a): print(*a, flush=True)

def clean_daily(d, now):
    """모양이 어긋나도 페이지가 깨지지 않도록 최소한으로 정리."""
    d["version"] = 1; d["mode"] = "daily"
    d["date"] = now.strftime("%Y-%m-%d"); d["generated_at"] = now.isoformat(timespec="seconds")
    # 출처: http 로 시작하는 것만, id 중복 제거
    seen, srcs = set(), []
    for s in d.get("sources", []) or []:
        if isinstance(s, dict) and str(s.get("url", "")).startswith("http") and s.get("id") and s["id"] not in seen:
            seen.add(s["id"]); srcs.append(s)
    d["sources"] = srcs
    ids = {s["id"] for s in srcs}
    def fix(o):
        if isinstance(o, dict):
            if "src" in o: o["src"] = [x for x in (o.get("src") or []) if x in ids]
            for v in o.values(): fix(v)
        elif isinstance(o, list):
            for v in o: fix(v)
    fix(d)
    mv = d.setdefault("market_view", {})
    if mv.get("label") not in ("Bullish", "Neutral", "Bearish"): mv["label"] = "Neutral"
    for k in ("key_changes", "issues", "emerging", "risks", "macro", "institutions", "view_changed"):
        if not isinstance(d.get(k), list): d[k] = []
    d["key_changes"] = d["key_changes"][:5]; d["issues"] = d["issues"][:5]
    for k in ("key_changes", "issues", "emerging", "risks"):
        for x in d[k]:
            if x.get("importance") not in ("HIGH", "MEDIUM", "LOW"): x["importance"] = "MEDIUM"
    for k in ("core_stocks", "genai"):
        if not isinstance(d.get(k), list): d[k] = []
    if not isinstance(d.get("spacex"), dict): d["spacex"] = {}
    for c in d["core_stocks"]:
        if str(c.get("stance")) not in ("Bullish", "Neutral", "Bearish"): c["stance"] = None
    d.setdefault("ai_semi", {}).setdefault("chain", [])
    d.setdefault("scenarios", {})
    if not d["key_changes"] or not mv.get("summary"):
        raise ValueError("필수 항목(key_changes / market_view.summary)이 비어 있습니다")
    return d


def load_prev(today):
    """오늘 이전의 Daily 최대 KEEP_PREV개 (오래된 순)."""
    out = []
    if not os.path.isdir(OUT_DIR): return out
    files = sorted(f for f in os.listdir(OUT_DIR) if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.json", f) and f[:10] < today)
    for f in files[-KEEP_PREV:]:
        try: out.append(json.load(open(os.path.join(OUT_DIR, f), encoding="utf-8")))
        except Exception: pass
    return out


def compact(d):
    """이전 회차를 프롬프트에 넣기 위한 요약(토큰 절약)."""
    return {
        "date": d.get("date"),
        "market_view": d.get("market_view", {}).get("label"),
        "summary": d.get("market_view", {}).get("summary"),
        "key_changes": [k.get("title") for k in d.get("key_changes", [])],
        "issues": [(i.get("title"), i.get("importance")) for i in d.get("issues", [])],
        "ai_chain": {c.get("step"): c.get("status") for c in d.get("ai_semi", {}).get("chain", [])},
        "institutions": {i.get("name"): i.get("stance") for i in d.get("institutions", [])},
        "core_stocks": {c.get("ticker"): c.get("stance") for c in d.get("core_stocks", [])},
        "spacex": (d.get("spacex") or {}).get("summary"),
        "genai": [g.get("headline") for g in d.get("genai", [])],
        "scenario_lean": d.get("scenarios", {}).get("lean"),
    }


def update_index(d):
    idx_path = os.path.join(OUT_DIR, "index.json")
    try: idx = json.load(open(idx_path, encoding="utf-8"))
    except Exception: idx = []
    idx = [x for x in idx if x.get("date") != d["date"]]
    idx.append({"date": d["date"], "label": d["market_view"]["label"],
                "headline": (d["key_changes"][0]["title"] if d["key_changes"] else ""),
                "top": [k["title"] for k in d["key_changes"][:3]]})
    idx.sort(key=lambda x: x["date"])
    json.dump(idx, open(idx_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def attach_institution_changes(d, prev):
    """이전 회차의 같은 기관 View와 비교해 prev / change(↑→↓)를 코드로 계산."""
    if not prev: return
    order = {"Bearish": 0, "Neutral": 1, "Bullish": 2}
    last = {i.get("name"): (i.get("stance") or {}).get("market") for i in prev[-1].get("institutions", [])}
    for i in d["institutions"]:
        old = last.get(i.get("name")); new = (i.get("stance") or {}).get("market")
        i["prev"] = old
        o, n = order.get(str(old).rstrip("*")), order.get(str(new).rstrip("*"))
        if o is not None and n is not None:
            i["change"] = "↑" if n > o else "↓" if n < o else "→"



def cmd_prev():
    now = dt.datetime.now(KST)
    prev = load_prev(now.strftime("%Y-%m-%d"))
    print(json.dumps([compact(p) for p in prev], ensure_ascii=False, indent=1) if prev else "없음(첫 회차이거나 기록 없음)")

def cmd_save(path):
    now = dt.datetime.now(KST)
    d = clean_daily(json.load(open(path, encoding="utf-8")), now)
    prev = load_prev(d["date"])
    attach_institution_changes(d, prev)
    os.makedirs(OUT_DIR, exist_ok=True)
    for p in (OUT_LATEST, os.path.join(OUT_DIR, d["date"] + ".json")):
        json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    update_index(d)
    log("[ok] %s View=%s key_changes=%d sources=%d" % (d["date"], d["market_view"]["label"], len(d["key_changes"]), len(d["sources"])))

def cmd_weekly_input():
    now = dt.datetime.now(KST)
    days = load_prev((now + dt.timedelta(days=1)).strftime("%Y-%m-%d"))
    print(json.dumps([compact(p) for p in days], ensure_ascii=False, indent=1))

def cmd_save_weekly(path):
    now = dt.datetime.now(KST)
    days = load_prev((now + dt.timedelta(days=1)).strftime("%Y-%m-%d"))
    if len(days) < 2: raise ValueError("Weekly를 만들 Daily 기록이 2개 미만입니다")
    w = json.load(open(path, encoding="utf-8")); iso = now.isocalendar()
    w["version"] = 1; w["mode"] = "weekly"
    w["week"] = "%d-W%02d" % (iso[0], iso[1]); w["period"] = "%s ~ %s" % (days[0]["date"], days[-1]["date"])
    w["generated_at"] = now.isoformat(timespec="seconds")
    w["market_view_trend"] = [{"date": p["date"], "label": p["market_view"]["label"],
                               "headline": (p["key_changes"][0]["title"] if p.get("key_changes") else "")} for p in days]
    seen, srcs = set(), []
    for p in days:
        for s in p.get("sources", []):
            if s["url"] not in seen: seen.add(s["url"]); srcs.append(s)
    w["sources"] = srcs[:30]
    os.makedirs(os.path.join(OUT_DIR, "weekly"), exist_ok=True)
    for p in (os.path.join(OUT_DIR, "weekly.json"), os.path.join(OUT_DIR, "weekly", w["week"] + ".json")):
        json.dump(w, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    log("[ok] weekly %s" % w["week"])

if __name__ == "__main__":
    a = sys.argv[1:]
    try:
        if a[:1] == ["prev"]: cmd_prev()
        elif a[:1] == ["save"]: cmd_save(a[1])
        elif a[:1] == ["weekly-input"]: cmd_weekly_input()
        elif a[:1] == ["save-weekly"]: cmd_save_weekly(a[1])
        else: print(__doc__); sys.exit(2)
    except Exception as e:
        log("[error] %s" % e); sys.exit(1)
