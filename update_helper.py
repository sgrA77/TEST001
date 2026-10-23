#!/usr/bin/env python3
"""update_helper.py - 예약작업(Claude)이 만든 Market Outlook 초안을 검증/저장하는 보조 스크립트. API 호출 없음.

구조(v2): outlook.json(오늘) / voices.json(주요 인물 발언) / outlook/index.json(날짜별 흐름 기록)
사용법
  python update_helper.py prev                 # 직전 outlook.json 요약 + 최근 흐름 기록 출력 (신규/지속 판단용)
  python update_helper.py save daily.json      # 오늘 초안 검증 후 outlook.json, outlook/index.json 갱신
  python update_helper.py save-voices v.json   # 발언 모음 검증 후 voices.json 갱신
실패하면 [error]를 출력하고 종료코드 1 (기존 파일은 건드리지 않음).
"""
import os, re, json, sys, datetime as dt

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_LATEST = os.path.join(ROOT, "outlook.json")
OUT_VOICES = os.path.join(ROOT, "voices.json")
OUT_DIR = os.path.join(ROOT, "outlook")
KEEP_FLOW = 60          # 흐름 기록 보관 일수(그 이전 항목은 삭제)
KST = dt.timezone(dt.timedelta(hours=9))
IMP = ("HIGH", "MEDIUM", "LOW")

def log(*a): print(*a, flush=True)
def jload(p, default=None):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return default
def jsave(p, o): json.dump(o, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def clean_daily(d, now):
    d["version"] = 2
    d["date"] = now.strftime("%Y-%m-%d"); d["generated_at"] = now.isoformat(timespec="seconds")
    seen, srcs = set(), []
    for s in d.get("sources", []) or []:
        if isinstance(s, dict) and str(s.get("url", "")).startswith("http") and s.get("id") and s["id"] not in seen:
            seen.add(s["id"]); srcs.append(s)
    d["sources"] = srcs
    ids = {s["id"] for s in srcs}
    mv = d.setdefault("market_view", {})
    if mv.get("label") not in ("Bullish", "Neutral", "Bearish"): mv["label"] = "Neutral"
    if not mv.get("summary"): raise ValueError("market_view.summary 가 비어 있습니다")
    for k in ("key_changes", "issues", "risks"):
        if not isinstance(d.get(k), list): d[k] = []
        for x in d[k]:
            if x.get("importance") not in IMP: x["importance"] = "MEDIUM"
    d["key_changes"] = d["key_changes"][:5]; d["issues"] = d["issues"][:5]; d["risks"] = d["risks"][:5]
    for x in d["issues"]:
        if x.get("tag") not in ("신규", "지속"): x["tag"] = "지속"
        if x.get("trend") not in ("up", "steady", "down"): x["trend"] = "steady"
    def fix(o):
        if isinstance(o, dict):
            if "src" in o: o["src"] = [x for x in (o.get("src") or []) if x in ids]
            for v in o.values(): fix(v)
        elif isinstance(o, list):
            for v in o: fix(v)
    fix(d)
    if not d["key_changes"]: raise ValueError("key_changes 가 비어 있습니다")
    d["flow"] = str(d.get("flow") or "")
    return d


def update_index(d):
    p = os.path.join(OUT_DIR, "index.json")
    idx = jload(p, [])
    idx = [x for x in idx if x.get("date") != d["date"]]
    idx.append({"date": d["date"], "label": d["market_view"]["label"],
                "headline": d["key_changes"][0]["title"], "flow": d.get("flow", "")})
    idx.sort(key=lambda x: x["date"])
    idx = idx[-KEEP_FLOW:]
    os.makedirs(OUT_DIR, exist_ok=True); jsave(p, idx)


def cmd_prev():
    d = jload(OUT_LATEST)
    if not d: print("없음(첫 회차)"); return
    out = {"date": d.get("date"), "view": d.get("market_view", {}).get("label"), "summary": d.get("market_view", {}).get("summary"),
           "key_changes": [k.get("title") for k in d.get("key_changes", [])],
           "issues": [(i.get("title"), i.get("importance"), i.get("trend")) for i in d.get("issues", [])],
           "risks": [(r.get("title"), r.get("importance")) for r in d.get("risks", [])]}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    print("--- 최근 흐름 기록 ---")
    print(json.dumps((jload(os.path.join(OUT_DIR, "index.json"), []))[-7:], ensure_ascii=False, indent=1))


def cmd_save(path):
    now = dt.datetime.now(KST)
    d = clean_daily(json.load(open(path, encoding="utf-8")), now)
    jsave(OUT_LATEST, d); update_index(d)
    log("[ok] %s View=%s key_changes=%d issues=%d risks=%d sources=%d" % (d["date"], d["market_view"]["label"], len(d["key_changes"]), len(d["issues"]), len(d["risks"]), len(d["sources"])))


def cmd_save_voices(path):
    v = json.load(open(path, encoding="utf-8"))
    groups = v.get("groups")
    if not isinstance(groups, list) or not groups: raise ValueError("groups 가 비어 있습니다")
    srcs = [s for s in (v.get("sources") or []) if isinstance(s, dict) and str(s.get("url", "")).startswith("http")]
    ns = {s.get("n") for s in srcs}
    for g in groups:
        if not g.get("name") or not isinstance(g.get("rows"), list): raise ValueError("그룹 형식 오류: %s" % g.get("name"))
        for r in g["rows"]:
            for k in ("who", "org", "stance", "quote", "date"):
                if not r.get(k): raise ValueError("%s: '%s' 가 비어 있습니다" % (r.get("who"), k))
            r.setdefault("detail", ""); r["outside"] = bool(r.get("outside"))
            r["src"] = [n for n in (r.get("src") or []) if n in ns]
    v["version"] = 1; v["sources"] = srcs
    v["updated"] = dt.datetime.now(KST).strftime("%Y-%m-%d")
    v.setdefault("window", "최근 3개월"); v.setdefault("summary", []); v.setdefault("missing", [])
    jsave(OUT_VOICES, v)
    log("[ok] voices rows=%d sources=%d" % (sum(len(g["rows"]) for g in groups), len(srcs)))


if __name__ == "__main__":
    a = sys.argv[1:]
    try:
        if a[:1] == ["prev"]: cmd_prev()
        elif a[:1] == ["save"]: cmd_save(a[1])
        elif a[:1] == ["save-voices"]: cmd_save_voices(a[1])
        else: print(__doc__); sys.exit(2)
    except Exception as e:
        log("[error] %s" % e); sys.exit(1)
