"""
Market Dashboard 데이터 수집 (TEST001.py → data.json)

수정하는 곳은 아래 [설정] 구역뿐입니다.
  - MARKET  : 관심종목 (섹터 → 표시이름 → Yahoo 티커)
  - MACRO   : 거시 지표
  - EARNINGS: 실적 발표 추적 기업
  - MANUAL_EVENTS / MANUAL_MACRO : 자동 수집이 안 될 때 직접 넣는 값
"""

import json
import re
import requests
from datetime import datetime, timedelta, timezone, date
from urllib.parse import quote

KST = timezone(timedelta(hours=9))
NOW = datetime.now(KST)
TODAY = NOW.date()

UA = {"User-Agent": "Mozilla/5.0"}

# =========================================================
# [설정] MARKET : 섹터 -> {표시이름: Yahoo 티커}
# 같은 종목이 여러 섹터에 있어도 됨 (AMD). 요청은 한 번만 나감.
# =========================================================

MARKET = {
    "지수": {"SPY": "SPY", "QQQ": "QQQ"},
    "레버리지 지수": {"SPXL 3x": "SPXL", "QLD 2x": "QLD"},
    "MAG7": {
        "NVDA": "NVDA", "MSFT": "MSFT", "AAPL": "AAPL", "AMZN": "AMZN",
        "GOOGL": "GOOGL", "META": "META", "TSLA": "TSLA",
    },
    "Memory": {"MU": "MU", "SK Hynix": "000660.KS", "Samsung": "005930.KS"},
    "GPU / AI Chip": {"AMD": "AMD", "AVGO": "AVGO"},
    "CPU": {"AMD": "AMD", "INTC": "INTC"},
    "Storage": {"SNDK": "SNDK"},
    "FAB": {"TSM": "TSM"},
    "Semiconductor Equipment": {
        "ASML": "ASML", "AMAT": "AMAT", "LRCX": "LRCX", "KLAC": "KLAC",
    },
}

# =========================================================
# [설정] MACRO : 그룹 -> {지표명: 스펙}
#   src    : yahoo(야후 티커) / fred(FRED 시리즈) / history(직접 누적)
#   kind   : "pct" = 변화율(%) / "pp" = 변화량(%p)
#   scale  : 값에 곱할 배수 (M2: 십억달러 → 조달러)
#   prefix / suffix / digits : 화면 표시용
# =========================================================

MACRO = {
    "유동성 / 환율": {
        "US M2": {"src": "fred", "id": ["M2SL", "WM2NS"], "kind": "pct",
                  "prefix": "$", "suffix": "T", "scale": 0.001},
        "USD/KRW": {"src": "yahoo", "id": "KRW=X", "kind": "pct"},
        "USD/JPY": {"src": "yahoo", "id": "JPY=X", "kind": "pct"},
    },
    "기준금리": {
        "Korea Policy Rate": {"src": "fred", "id": "IRSTCB01KRM156N", "kind": "pp", "suffix": "%"},
        "US Policy Rate": {"src": "fred", "id": "DFEDTARU", "kind": "pp", "suffix": "%"},
        "Japan Policy Rate": {"src": "fred", "id": "IRSTCB01JPM156N", "kind": "pp", "suffix": "%"},
    },
    "시장금리": {
        "US 3M": {"src": "yahoo", "id": "^IRX", "kind": "pp", "suffix": "%"},
        "US 2Y": {"src": "fred", "id": "DGS2", "kind": "pp", "suffix": "%"},
        "US 10Y": {"src": "yahoo", "id": "^TNX", "kind": "pp", "suffix": "%"},
        "US 30Y": {"src": "yahoo", "id": "^TYX", "kind": "pp", "suffix": "%"},
    },
    "밸류에이션 / 변동성": {
        # 과거값을 주는 무료 API가 없어서 data.json에 매일 1개씩 쌓아 1M/1Y를 계산함
        # (1M 표시까지 약 한 달, 1Y 표시까지 약 1년 걸림)
        "S&P 500 Fwd Earnings Yield": {"src": "history", "kind": "pp", "suffix": "%"},
        "VIX": {"src": "yahoo", "id": "^VIX", "kind": "pct"},
    },
}

# 자동 수집이 계속 실패하는 지표는 여기에 직접 입력하면 그 값이 우선 사용됨
MANUAL_MACRO = {
    # "Korea Policy Rate": {"value": 2.50, "prev_month": 2.50, "prev_year": 3.00},
}

# =========================================================
# [설정] EARNINGS : {티커: 표시이름}  (여기에 추가/삭제)
# =========================================================

EARNINGS = {
    "NVDA": "NVIDIA", "MSFT": "Microsoft", "AAPL": "Apple", "AMZN": "Amazon",
    "GOOGL": "Alphabet", "META": "Meta", "TSLA": "Tesla",
    "AMD": "AMD", "AVGO": "Broadcom", "MU": "Micron", "TSM": "TSMC",
    "ASML": "ASML", "AMAT": "Applied Materials", "LRCX": "Lam Research",
    "KLAC": "KLA", "SNDK": "SanDisk", "INTC": "Intel",
}

# =========================================================
# [설정] EVENTS : 자동 수집이 안 될 때 직접 추가하는 일정
# name은 FOMC / CPI / NFP / PCE 중 하나, date는 미국 현지 날짜
# =========================================================

MANUAL_EVENTS = [
    # {"name": "CPI", "date": "2026-10-14"},
]


# =========================================================
# 공통 유틸
# =========================================================

def rnd(x, n=4):
    return None if x is None else round(x, n)


def pick_base(series, period):
    """series: 날짜 오름차순 [(date, value)].
    period="month" → 지난달 마지막 거래일 종가 (1M 기준)
    period="year"  → 작년 마지막 거래일 종가  (1Y 기준)
    기준일은 series의 최신 날짜. 해당 값이 없으면 None."""
    if not series:
        return None
    last = series[-1][0]
    limit = last.replace(day=1) if period == "month" else date(last.year, 1, 1)
    older = [v for d, v in series if d < limit]
    return older[-1] if older else None


def load_old():
    try:
        with open("data.json", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


OLD = load_old()


# =========================================================
# Yahoo Finance 시세 (기존 방식 유지: chart API, 2년 일봉)
# =========================================================

_YAHOO_CACHE = {}


def fetch_yahoo(ticker):
    if ticker in _YAHOO_CACHE:
        return _YAHOO_CACHE[ticker]

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=2y&interval=1d"

    last_err = None
    for _ in range(2):  # 일시적 실패 대비 1회 재시도
        try:
            result = requests.get(url, headers=UA, timeout=20).json()["chart"]["result"][0]
            break
        except Exception as e:
            last_err = e
    else:
        raise last_err

    closes = result["indicators"]["quote"][0]["close"]
    series = [
        (datetime.fromtimestamp(t, timezone.utc).date(), c)
        for t, c in zip(result["timestamp"], closes)
        if c is not None
    ]
    meta = result["meta"]

    data = {
        "price": meta.get("regularMarketPrice") or series[-1][1],
        "currency": meta.get("currency", "USD"),
        "series": series,
    }
    _YAHOO_CACHE[ticker] = data
    return data


BROWSER_UA = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "text/csv,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

_fred_net_fail = 0  # 접속 자체가 막힌 횟수 (연달아 막히면 나머지는 바로 포기 → 실행시간 절약)


def _parse_fred_csv(text):
    rows = []
    for line in text.strip().splitlines()[1:]:
        parts = line.split(",")
        try:
            rows.append((datetime.strptime(parts[0], "%Y-%m-%d").date(), float(parts[1])))
        except (ValueError, IndexError):
            continue  # 결측('.') 건너뜀
    return rows


def _parse_fred_txt(text):
    return [
        (datetime.strptime(d, "%Y-%m-%d").date(), float(v))
        for d, v in re.findall(r"^(\d{4}-\d{2}-\d{2})\s+(-?[\d.]+)\s*$", text, re.M)
    ]


def fetch_fred(series_ids):
    """FRED 공개 데이터 (API 키 불필요). 시리즈 ID를 리스트로 주면 앞에서부터 시도."""
    global _fred_net_fail
    ids = [series_ids] if isinstance(series_ids, str) else series_ids
    since = (TODAY - timedelta(days=800)).isoformat()
    errors = []

    for sid in ids:
        sources = [
            (f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={since}", _parse_fred_csv),
            (f"https://fred.stlouisfed.org/data/{sid}.txt", _parse_fred_txt),
        ]
        for url, parser in sources:
            if _fred_net_fail >= 2:
                raise RuntimeError("FRED 접속 불가 (이전 요청에서 연결 실패)")
            try:
                r = requests.get(url, headers=BROWSER_UA, timeout=15)
                r.raise_for_status()
                rows = parser(r.text)
                rows = [x for x in rows if x[0] >= TODAY - timedelta(days=800)]
                if rows:
                    _fred_net_fail = 0
                    return rows
                errors.append(f"{sid}: 빈 데이터")
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                _fred_net_fail += 1
                errors.append(f"{sid}: 연결 실패 {type(e).__name__}")
            except Exception as e:
                errors.append(f"{sid}: {e}")

    raise RuntimeError("FRED 실패 → " + " | ".join(errors[-3:]))


def fetch_forward_earnings_yield():
    data = requests.get(
        "https://historyofmarket.com/api/sp500/forward-pe.json",
        headers=UA, timeout=20,
    ).json()
    return 100 / data["current"]["forward"]


# =========================================================
# MARKET
# =========================================================

market = {}

for sector, items in MARKET.items():
    market[sector] = {}
    for name, ticker in items.items():
        try:
            y = fetch_yahoo(ticker)
            market[sector][name] = {
                "ticker": ticker,
                "currency": y["currency"],
                "price": rnd(y["price"]),
                "prev_month": rnd(pick_base(y["series"], "month")),
                "prev_year": rnd(pick_base(y["series"], "year")),
            }
        except Exception as e:
            print(f"[warn] MARKET {name}({ticker}) 실패: {e}")
            prev = OLD.get("market", {}).get(sector, {}).get(name)
            if prev:  # 실패하면 직전 값 유지 → 화면이 비지 않게
                market[sector][name] = prev


# =========================================================
# MACRO
# =========================================================

history = OLD.get("history", {})  # {지표명: {"YYYY-MM-DD": 값}}

macro = {}

for group, items in MACRO.items():
    macro[group] = {}
    for name, spec in items.items():

        display = {k: spec[k] for k in ("kind", "prefix", "suffix", "digits") if k in spec}

        try:
            if name in MANUAL_MACRO:
                m = MANUAL_MACRO[name]
                item = {"value": m["value"], "prev_month": m.get("prev_month"),
                        "prev_year": m.get("prev_year")}

            else:
                if spec["src"] == "yahoo":
                    y = fetch_yahoo(spec["id"])
                    series, value = y["series"], y["price"]

                elif spec["src"] == "fred":
                    series = fetch_fred(spec["id"])
                    value = series[-1][1]

                else:  # history
                    h = history.setdefault(name, {})
                    h[TODAY.isoformat()] = round(fetch_forward_earnings_yield(), 3)
                    cutoff = (TODAY - timedelta(days=400)).isoformat()
                    for k in [k for k in h if k < cutoff]:
                        del h[k]
                    series = sorted((date.fromisoformat(k), v) for k, v in h.items())
                    value = series[-1][1]

                s = spec.get("scale", 1)
                pm, py = pick_base(series, "month"), pick_base(series, "year")
                item = {
                    "value": value * s,
                    "prev_month": None if pm is None else pm * s,
                    "prev_year": None if py is None else py * s,
                }

            item = {k: rnd(v) for k, v in item.items()}
            macro[group][name] = {**item, **display}

        except Exception as e:
            print(f"[warn] MACRO {name} 실패: {e}")
            prev = OLD.get("macro", {}).get(group, {}).get(name)
            if prev and prev.get("value") is not None:
                macro[group][name] = prev
            else:  # 값이 없어도 행은 표시 ("-") → 어떤 지표가 실패했는지 화면에서 보임
                macro[group][name] = {"value": None, "prev_month": None,
                                      "prev_year": None, **display}


# =========================================================
# EVENTS (FOMC / CPI / NFP / PCE) - 미국 현지 날짜 기준, 다음 예정 1건씩
# =========================================================

MONTH_RE = ("January|February|March|April|May|June|July|August|"
            "September|October|November|December")
MONTHS = {m: i for i, m in enumerate(MONTH_RE.split("|"), start=1)}


def strip_html(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def fomc_dates():
    """Fed 캘린더: 회의 마지막 날(성명 발표일)."""
    html = requests.get(
        "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        headers=UA, timeout=20,
    ).text
    text = strip_html(html)

    # "2026 FOMC Meetings" 처럼 연도 헤더 기준으로 구간을 나눔
    parts = re.split(r"(\d{4}) FOMC Meetings", text)
    if len(parts) == 1:
        parts = ["", str(TODAY.year), text]

    dates = set()
    for i in range(1, len(parts) - 1, 2):
        year = int(parts[i])
        for month, _d1, d2 in re.findall(
            rf"({MONTH_RE})\s+(\d{{1,2}})\s*[-–]\s*(\d{{1,2}})", parts[i + 1]
        ):
            try:
                dates.add(date(year, MONTHS[month], int(d2)))
            except ValueError:
                pass
    return sorted(dates)


def bls_dates():
    """BLS 발표 일정(.ics): CPI, 고용보고서(NFP)."""
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
        "Accept": "text/calendar,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.9",
    }
    r = requests.get("https://www.bls.gov/schedule/news_release/bls.ics",
                     headers=headers, timeout=20)
    r.raise_for_status()

    out = {"CPI": [], "NFP": []}
    for block in r.text.split("BEGIN:VEVENT")[1:]:
        d = re.search(r"DTSTART[^:\r\n]*:(\d{8})", block)
        s = re.search(r"SUMMARY:(.*)", block)
        if not d or not s:
            continue
        summary = s.group(1)
        day = datetime.strptime(d.group(1), "%Y%m%d").date()
        if "Consumer Price Index" in summary:
            out["CPI"].append(day)
        elif "Employment Situation" in summary:
            out["NFP"].append(day)
    return out


def pce_dates():
    """BEA 일정: Personal Income and Outlays(PCE 포함)."""
    html = requests.get("https://www.bea.gov/news/schedule", headers=UA, timeout=20).text
    text = strip_html(html)

    dates = []
    for month, day in re.findall(
        r"([A-Z][a-z]+)\s+(\d{1,2}).{0,300}?Personal Income and Outlays", text, re.S
    ):
        if month in MONTHS:
            try:
                dates.append(date(TODAY.year, MONTHS[month], int(day)))
            except ValueError:
                pass
    return dates


found = {"FOMC": [], "CPI": [], "NFP": [], "PCE": []}

try:
    found["FOMC"] += fomc_dates()
except Exception as e:
    print(f"[warn] FOMC 일정 실패: {e}")

try:
    b = bls_dates()
    found["CPI"] += b["CPI"]
    found["NFP"] += b["NFP"]
except Exception as e:
    print(f"[warn] CPI/NFP 일정 실패 (MANUAL_EVENTS로 직접 입력 가능): {e}")

try:
    found["PCE"] += pce_dates()
except Exception as e:
    print(f"[warn] PCE 일정 실패: {e}")

for e in MANUAL_EVENTS:
    try:
        found.setdefault(e["name"], []).append(date.fromisoformat(e["date"]))
    except Exception as ex:
        print(f"[warn] MANUAL_EVENTS 형식 오류 {e}: {ex}")

events = []
for name, days in found.items():
    upcoming = sorted(d for d in days if d >= TODAY)
    if upcoming:
        events.append({
            "name": name,
            "date": upcoming[0].isoformat(),
            "d_day": (upcoming[0] - TODAY).days,
        })
events.sort(key=lambda e: e["d_day"])


# =========================================================
# EARNINGS (Yahoo quoteSummary - 쿠키/crumb 필요)
#   다음 발표: 날짜 / EPS 예상 / 매출 예상
#   최근 3분기: EPS 예상·실제, 매출 예상·실제 (트렌드 확인용)
# =========================================================

def yahoo_session():
    s = requests.Session()
    s.headers.update(UA)
    s.get("https://fc.yahoo.com", timeout=15)  # 쿠키 발급용 (404가 와도 정상)
    crumb = s.get("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=15).text.strip()
    if not crumb or "<" in crumb or " " in crumb:
        raise ValueError(f"crumb 발급 실패: {crumb[:60]}")
    return s, crumb


def raw(x):
    return x.get("raw") if isinstance(x, dict) else None


def quarter_key(label):
    """'2Q2025' → (2025, 2) : 분기 정렬용"""
    try:
        return (int(label[2:]), int(label[0]))
    except Exception:
        return (0, 0)


def fetch_earnings(session, crumb, ticker):
    url = (f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}"
           f"?modules=calendarEvents,earnings&crumb={quote(crumb)}")
    res = session.get(url, timeout=20).json()["quoteSummary"]["result"][0]

    # --- 다음 발표 ---
    ce = res["calendarEvents"]["earnings"]
    dates = sorted(
        d["fmt"] for d in ce.get("earningsDate", [])
        if d.get("fmt") and d["fmt"] >= TODAY.isoformat()
    )

    # --- 지난 분기들 (EPS 예상/실제 + 매출 실제) ---
    earn = res.get("earnings") or {}
    chart = earn.get("earningsChart") or {}
    fin = earn.get("financialsChart") or {}

    rev_by_label = {q.get("date"): raw(q.get("revenue")) for q in fin.get("quarterly", [])}
    past = [
        {"label": q.get("date"), "eps_est": raw(q.get("estimate")),
         "eps_act": raw(q.get("actual")), "rev_act": rev_by_label.get(q.get("date"))}
        for q in chart.get("quarterly", []) if q.get("date")
    ]
    past.sort(key=lambda q: quarter_key(q["label"]))

    # 지금 예상 중인 분기 이름 (예: 3Q2026) → 예상치 저장용 키
    cq, cy = chart.get("currentQuarterEstimateDate"), chart.get("currentQuarterEstimateYear")
    next_label = f"{cq}{cy}" if cq and cy else None

    return {
        "date": dates[0] if dates else None,
        "eps_est": raw(ce.get("earningsAverage")),
        "rev_est": raw(ce.get("revenueAverage")),
        "next_label": next_label,
        "past": past,
    }


earnings = []
old_earn = {e["symbol"]: e for e in OLD.get("earnings", []) if "symbol" in e}

# 매출 "예상치"는 Yahoo가 과거분을 안 줘서, 발표 전 예상치를 매번 저장해 두었다가
# 실제값이 나오면 옆에 붙여 보여줌 (저장 시작 이후 분기부터 표시됨)
est_hist = history.setdefault("earnings_est", {})  # {티커: {분기: {eps_est, rev_est}}}

try:
    sess, crumb = yahoo_session()
except Exception as e:
    sess = crumb = None
    print(f"[warn] EARNINGS 세션 실패: {e}")

for symbol, company in EARNINGS.items():
    row = {"symbol": symbol, "name": company, "date": None, "d_day": None,
           "eps_est": None, "rev_est": None, "quarters": []}
    try:
        if sess is None:
            raise RuntimeError("세션 없음")
        got = fetch_earnings(sess, crumb, symbol)

        saved = est_hist.setdefault(symbol, {})
        if got["next_label"] and (got["eps_est"] is not None or got["rev_est"] is not None):
            saved[got["next_label"]] = {"eps_est": got["eps_est"], "rev_est": got["rev_est"]}
        for k in list(saved)[:-8]:  # 최근 8분기만 보관
            del saved[k]

        quarters = []
        for q in got["past"]:
            if q["eps_act"] is None and q["rev_act"] is None:
                continue  # 아직 발표 전인 분기는 제외
            mem = saved.get(q["label"], {})
            quarters.append({
                "label": q["label"],
                "eps_est": rnd(q["eps_est"] if q["eps_est"] is not None else mem.get("eps_est")),
                "eps_act": rnd(q["eps_act"]),
                "rev_est": mem.get("rev_est"),
                "rev_act": q["rev_act"],
            })

        row.update({"date": got["date"], "eps_est": rnd(got["eps_est"]),
                    "rev_est": got["rev_est"], "quarters": quarters[-3:]})
    except Exception as e:
        print(f"[warn] EARNINGS {symbol} 실패: {e}")
        prev = old_earn.get(symbol)
        if prev:  # 실패하면 직전 값 유지
            row.update({k: prev.get(k) for k in ("eps_est", "rev_est")})
            row["quarters"] = prev.get("quarters", [])
            if prev.get("date") and prev["date"] >= TODAY.isoformat():
                row["date"] = prev["date"]

    if row["date"]:
        row["d_day"] = (date.fromisoformat(row["date"]) - TODAY).days
    earnings.append(row)

earnings.sort(key=lambda r: (r["d_day"] is None, r["d_day"] if r["d_day"] is not None else 0))


# =========================================================
# 저장
# =========================================================

output = {
    "updated_at": NOW.strftime("%Y-%m-%d %H:%M KST"),
    "macro": macro,
    "events": events,
    "earnings": earnings,
    "market": market,
    "history": history,  # 화면에는 안 쓰임. 지표 히스토리 누적용
}

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=1)

n_market = sum(len(v) for v in market.values())
n_macro = sum(len(v) for v in macro.values())
print(f"saved data.json | market {n_market} | macro {n_macro} | "
      f"events {len(events)} | earnings {sum(1 for e in earnings if e['date'])}/{len(earnings)} "
      f"(지난분기 있음 {sum(1 for e in earnings if e['quarters'])})")
