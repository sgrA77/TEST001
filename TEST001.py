"""
Market Dashboard 데이터 수집기   TEST001.py → data.json → index.html (GitHub Pages)

GitHub Actions(test.yml)가 10분마다 이 파일을 실행 → data.json 저장·커밋 → index.html 이 읽어서 표시.

■ 수정은 아래 [설정] 구역에서만 하면 됩니다. (그 아래 코드는 건드릴 필요 없음)
■ 한 곳이 실패해도 나머지는 계속 진행합니다.
  - 실패한 항목은 직전 data.json 값을 그대로 보여주고 화면에 "지연" 표시가 붙습니다.
  - 실패 사유는 화면 맨 아래 "데이터 수집 경고"에 표시됩니다.
"""

import csv
import io
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

import requests


# ╔═══════════════════════════════════════════════════════╗
# ║                       [설정]                          ║
# ╚═══════════════════════════════════════════════════════╝

# ---------------------------------------------------------
# MARKET : 섹터 → {표시이름: ("Yahoo 티커", "테마")}
#   - 섹터 순서 = 화면 순서
#   - 같은 종목이 여러 섹터에 있어도 됨 (요청은 한 번만 나감)
#   - 선물(=F)은 연결 시세라 월물 교체 시기에 1M/1Y가 실제 표기와 조금 다를 수 있음
# ---------------------------------------------------------
MARKET = {
    "에너지 / 원자재": {
        "Bitcoin": ("BTC-USD", "Crypto"), "Gold": ("GC=F", "귀금속"), "Silver": ("SI=F", "귀금속"),
        "Copper": ("HG=F", "산업금속"), "WTI Oil": ("CL=F", "원유"), "Natural Gas": ("NG=F", "천연가스"),
    },
    "지수": {"SPY": ("SPY", "S&P 500"), "QQQ": ("QQQ", "Nasdaq 100")},
    "레버리지 지수": {"SPXL 3x": ("SPXL", "S&P 500 3x"), "QLD 2x": ("QLD", "Nasdaq 100 2x")},
    "MAG7": {
        "NVDA": ("NVDA", "AI · GPU"), "MSFT": ("MSFT", "Cloud · AI"), "AAPL": ("AAPL", "Device"),
        "AMZN": ("AMZN", "Cloud · 커머스"), "GOOGL": ("GOOGL", "검색 · AI"),
        "META": ("META", "SNS · AI"), "TSLA": ("TSLA", "EV · 로보틱스"),
    },
    "AI 소프트웨어": {"ORCL": ("ORCL", "Cloud · DB"), "PLTR": ("PLTR", "AI 데이터 분석")},
    "Memory": {
        "MU": ("MU", "DRAM · HBM"), "SK Hynix": ("000660.KS", "DRAM · HBM"),
        "Samsung": ("005930.KS", "메모리 · 파운드리"),
    },
    "GPU / AI Chip": {"AMD": ("AMD", "GPU"), "AVGO": ("AVGO", "커스텀 AI칩"), "CBRS": ("CBRS", "웨이퍼 AI칩")},
    "CPU": {"AMD": ("AMD", "CPU"), "INTC": ("INTC", "CPU · 파운드리")},
    "Storage": {"SNDK": ("SNDK", "NAND")},
    "FAB": {"TSM": ("TSM", "파운드리")},
    "Semiconductor Equipment": {
        "ASML": ("ASML", "EUV 노광"), "AMAT": ("AMAT", "증착 · 식각"),
        "LRCX": ("LRCX", "식각"), "KLAC": ("KLAC", "검사 · 계측"),
    },
    # --- AI 트렌드 (증권사 AI 밸류체인 분석에서 공통으로 꼽는 단계별 대장주) ---
    "AI 네트워크 / 광통신": {
        "ANET": ("ANET", "AI 스위치"), "MRVL": ("MRVL", "커스텀칩 · 광 DSP"),
        "CIEN": ("CIEN", "광전송"), "COHR": ("COHR", "광모듈 · 레이저"),
    },
    "AI 전력 / 냉각": {
        "VRT": ("VRT", "전력 · 냉각"), "GEV": ("GEV", "가스터빈 · 전력망"),
        "ETN": ("ETN", "전기설비"), "CEG": ("CEG", "원전 전력"), "VST": ("VST", "발전"),
    },
    "데이터센터 / AI 클라우드": {
        "CRWV": ("CRWV", "GPU 클라우드"), "EQIX": ("EQIX", "데이터센터 리츠"),
        "DLR": ("DLR", "데이터센터 리츠"),
    },
    "AI 서버": {"DELL": ("DELL", "AI 서버"), "SMCI": ("SMCI", "AI 서버")},
}

# 화면에서 처음에 접혀 있을 MARKET 섹터 (제목을 누르면 펼쳐짐)
FOLDED_SECTORS = ["에너지 / 원자재"]

# 화면 맨 위에 현재값만 크게 보여줄 지표 (아래 MACRO 의 지표명)
TOP_BAR = ["VIX", "USD/KRW", "US 10Y"]

# ---------------------------------------------------------
# MACRO : 그룹 → {지표명: 스펙}
#   src    : 데이터 출처. 앞에서부터 시도하고 실패하면 다음 출처로 자동 전환
#            "yahoo:^VIX"     Yahoo 티커
#            "treasury:2 Yr"  미국 재무부 일일 수익률 (CSV 컬럼명)
#            "fred:DGS2"      FRED 시리즈 (아래 FRED_API_KEY 권장)
#            "fedh6:M2"       Fed H.6 (미국 M2)
#            "bis:KR"         BIS 중앙은행 정책금리 (KR / US / JP)
#            "fwd_ey"         S&P500 선행 이익수익률 (과거값이 없어 data.json 에 매일 누적)
#   kind   : "pct" = 색을 변화율(%)로 판단 / "pp" = 색을 변화량(%p)으로 판단
#   desc   : 카드에 작게 표시할 설명
#   prefix / suffix / digits : 표시 형식 (기본 소수 2자리)
#   scale  : 값에 곱할 배수 (M2: 십억달러 → 조달러)
#   daily  : False 면 전일 대비 증감을 표시하지 않음 (월간·계단식 데이터)
#   static : 모든 출처가 실패하고 직전 값도 없을 때 쓰는 값
# ---------------------------------------------------------
MACRO = {
    "유동성 / 환율": {
        "US M2": {"src": ["fedh6:M2", "fred:M2SL"], "kind": "pct", "desc": "미국 통화량",
                  "prefix": "$", "suffix": "T", "scale": 0.001, "daily": False, "static": 23.0},
        "USD/KRW": {"src": ["yahoo:KRW=X"], "kind": "pct", "desc": "원 / 달러", "digits": 1},
        "USD/JPY": {"src": ["yahoo:JPY=X"], "kind": "pct", "desc": "엔 / 달러"},
    },
    "기준금리": {
        "Korea Policy Rate": {"src": ["bis:KR"], "kind": "pp", "desc": "한국은행", "suffix": "%",
                              "daily": False, "static": 3.0},
        "US Policy Rate": {"src": ["bis:US"], "kind": "pp", "desc": "연준 (목표범위 중간값)", "suffix": "%",
                           "digits": 3, "daily": False, "static": 3.875},
        "Japan Policy Rate": {"src": ["bis:JP"], "kind": "pp", "desc": "일본은행", "suffix": "%",
                              "daily": False, "static": 1.25},
    },
    "시장금리": {
        "US 3M": {"src": ["yahoo:^IRX", "treasury:3 Mo"], "kind": "pp", "desc": "미 국채 3개월", "suffix": "%"},
        "US 2Y": {"src": ["treasury:2 Yr", "fred:DGS2"], "kind": "pp", "desc": "미 국채 2년", "suffix": "%"},
        "US 10Y": {"src": ["yahoo:^TNX", "treasury:10 Yr"], "kind": "pp", "desc": "미 국채 10년", "suffix": "%"},
        "US 30Y": {"src": ["yahoo:^TYX", "treasury:30 Yr"], "kind": "pp", "desc": "미 국채 30년", "suffix": "%"},
    },
    "밸류에이션 / 위험": {
        "S&P 500 Fwd EY": {"src": ["fwd_ey"], "kind": "pp", "desc": "12개월 선행 이익수익률", "suffix": "%",
                           "daily": False},
        "VIX": {"src": ["yahoo:^VIX"], "kind": "pct", "desc": "변동성 지수"},
        "HY Spread": {"src": ["fred:BAMLH0A0HYM2"], "kind": "pp", "desc": "하이일드 OAS", "suffix": "%"},
        "BBB Spread": {"src": ["fred:BAMLC0A4CBBB"], "kind": "pp", "desc": "BBB 회사채 OAS", "suffix": "%"},
    },
}

# 기준금리는 BIS 반영이 며칠~몇 주 늦음. 바뀐 날 바로 반영하려면 여기에 추가 (BIS가 따라잡으면 자동 무시)
RATE_CHANGES = {
    "Japan Policy Rate": [("2026-09-18", 1.25)],   # BOJ 1.00 → 1.25
    # "Korea Policy Rate": [("2026-10-22", 3.25)],
    # "US Policy Rate": [("2026-10-28", 3.625)],   # 목표범위 중간값
}

# 자동 수집이 계속 실패하는 지표는 직접 입력 (이 값이 우선 사용됨)
MANUAL_MACRO = {
    # "Korea Policy Rate": {"value": 3.00, "m1": 3.00, "y1": 3.00, "y2": 3.25},
}

# FRED(HY/BBB 스프레드 등)는 GitHub 서버에서 웹 다운로드가 자주 막힙니다.
# https://fredaccount.stlouisfed.org/apikeys 에서 무료 키를 받아 넣으면 공식 API 로 받아 가장 확실합니다.
# (저장소가 공개라면 키가 보이므로 FRED 전용 무료 키만 사용)
FRED_API_KEY = ""

# ---------------------------------------------------------
# EARNINGS : 실적 추적 기업 {티커: 이름}
# ---------------------------------------------------------
EARNINGS = {
    "NVDA": "NVIDIA", "MSFT": "Microsoft", "AAPL": "Apple", "AMZN": "Amazon",
    "GOOGL": "Alphabet", "META": "Meta", "TSLA": "Tesla",
    "AMD": "AMD", "AVGO": "Broadcom", "MU": "Micron", "TSM": "TSMC",
    "ASML": "ASML", "AMAT": "Applied Materials", "LRCX": "Lam Research",
    "KLAC": "KLA", "SNDK": "SanDisk", "INTC": "Intel",
}

# 실적 발표가 이 일수 이내면 EVENTS 에도 함께 표시
EARN_SOON_DAYS = 3

# ---------------------------------------------------------
# EVENTS
# ---------------------------------------------------------
# 직접 추가하는 일정 (미국 현지 날짜). IPO 는 kind 를 "ipo" 로.
MANUAL_EVENTS = [
    # {"name": "CPI", "date": "2026-10-14"},
    # {"name": "Anthropic", "date": "2026-11-12", "kind": "ipo"},
]

# 자동 수집이 실패했을 때 쓰는 내장 일정 (Fed / BLS / BEA 공식 일정, 연 1회 갱신)
BUILTIN_EVENTS = {
    "FOMC": ["2026-10-28", "2026-12-09"],
    "CPI": ["2026-10-14", "2026-11-10", "2026-12-10"],
    "NFP": ["2026-10-02", "2026-11-06", "2026-12-04"],
    "PCE": ["2026-10-29", "2026-11-25"],
}

# 발표 시각 (미국 동부시간 시:분) → 화면에서 한국시간·남은 시간으로 바뀜
EVENT_TIMES = {"FOMC": (14, 0), "Fed Press": (14, 30), "CPI": (8, 30), "NFP": (8, 30), "PCE": (8, 30)}

# 미국 상장 IPO(Nasdaq 캘린더) 중 회사 이름에 아래 단어가 있으면 AI 관련으로 보고 표시
IPO_AI_KEYWORDS = [
    "anthropic", "openai", "databricks", "xai", "spacex", "cerebras", "coreweave", "lambda", "crusoe",
    "scale ai", "perplexity", "mistral", "groq", "sambanova", "nscale", "nebius",
    "artificial intelligence", "robotics", "machine learning", "generative",
]


# ╔═══════════════════════════════════════════════════════╗
# ║            이 아래는 수정할 필요 없음                  ║
# ╚═══════════════════════════════════════════════════════╝

KST = timezone(timedelta(hours=9))
NOW = datetime.now(KST)
TODAY = NOW.date()
try:
    from zoneinfo import ZoneInfo
    NY = ZoneInfo("America/New_York")
except Exception:
    NY = None

UA = {"User-Agent": "Mozilla/5.0"}
BROWSER = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "text/csv,text/plain,application/json,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

WARNINGS = []


def warn(msg):
    print("[warn] " + msg)
    if len(WARNINGS) < 40:
        WARNINGS.append(str(msg)[:220])


def rnd(x, n=4):
    return None if x is None else round(x, n)


def get_text(url, headers=BROWSER, timeout=20):
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.text


def load_old():
    try:
        with open("data.json", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ---------------------------------------------------------
# 기준값: 1M = 전월 말, 1Y = 전년 말, 2Y = 재작년 말 종가
# ---------------------------------------------------------

def bases(series):
    """series: 날짜 오름차순 [(date, 값)] → {"m1", "y1", "y2"} (최신 날짜 기준)"""
    if not series:
        return {"m1": None, "y1": None, "y2": None}
    last = series[-1][0]

    def before(limit):
        older = [v for d, v in series if d < limit]
        return older[-1] if older else None

    return {
        "m1": before(last.replace(day=1)),
        "y1": before(date(last.year, 1, 1)),
        "y2": before(date(last.year - 1, 1, 1)),
    }


# =========================================================
# 데이터 출처
# =========================================================

# ---- Yahoo Finance (chart API, 3년 일봉) ----
_YAHOO = {}


def yahoo(ticker):
    """{"price", "prev", "series", "currency", "turnover"}  (실패도 캐시해서 재요청 안 함)"""
    if ticker in _YAHOO:
        hit = _YAHOO[ticker]
        if isinstance(hit, Exception):
            raise hit
        return hit

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=3y&interval=1d"
    try:
        res = None
        for attempt in range(3):
            try:
                r = requests.get(url, headers=UA, timeout=20)
                if r.status_code == 429:          # 요청 과다 → 잠깐 쉬고 재시도
                    time.sleep(2 + attempt * 2)
                    continue
                js = r.json().get("chart") or {}
                if not js.get("result"):
                    err = js.get("error")
                    err = err.get("description") if isinstance(err, dict) else err
                    raise LookupError(f"티커 없음/조회 실패 ({err or r.status_code})")
                res = js["result"][0]
                break
            except LookupError:
                raise
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(1)
        if res is None:
            raise RuntimeError("Yahoo 429 (요청 과다)")

        q = res["indicators"]["quote"][0]
        series = [(datetime.fromtimestamp(t, timezone.utc).date(), c)
                  for t, c in zip(res["timestamp"], q["close"]) if c is not None]
        if not series:
            raise RuntimeError("시세 없음")
        meta = res["meta"]
        price = meta.get("regularMarketPrice") or series[-1][1]

        # 전일 종가: 마지막 봉이 '오늘(최근 거래 시각)' 봉이면 그 앞 봉, 아니면 마지막 봉
        prev = series[-2][1] if len(series) >= 2 else None
        rmt = meta.get("regularMarketTime")
        if rmt and series[-1][0] < datetime.fromtimestamp(rmt, timezone.utc).date():
            prev = series[-1][1]

        # 거래대금: 주식/ETF = 거래량 × 가격, 코인 = 거래량(이미 달러), 선물·환율·지수 = 없음
        vols = q.get("volume") or []
        volume = meta.get("regularMarketVolume") or next((v for v in reversed(vols) if v), None)
        itype = meta.get("instrumentType")
        turnover = None
        if volume and itype == "CRYPTOCURRENCY":
            turnover = volume
        elif volume and itype in ("EQUITY", "ETF"):
            turnover = volume * price

        out = {"price": price, "prev": prev, "series": series,
               "currency": meta.get("currency") or "USD", "turnover": turnover}
        _YAHOO[ticker] = out
        return out
    except Exception as e:
        _YAHOO[ticker] = e
        raise


def prefetch_yahoo(tickers):
    """여러 티커를 동시에 받아 두기 (실행 시간 단축)"""
    def one(t):
        try:
            yahoo(t)
        except Exception:
            pass
    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(one, sorted(set(tickers))))


# ---- FRED ----
_fred_net_fail = 0   # 웹 접속이 연달아 막히면 나머지는 바로 건너뜀 (실행 시간 절약)


def _fred_csv(text):
    rows = []
    for line in text.strip().splitlines()[1:]:
        parts = line.split(",")
        try:
            rows.append((date.fromisoformat(parts[0]), float(parts[1])))
        except (ValueError, IndexError):
            continue   # 결측('.')
    return rows


def _fred_api(text):
    return [(date.fromisoformat(o["date"]), float(o["value"]))
            for o in json.loads(text)["observations"] if o["value"] not in (".", "")]


def fred(sid):
    """시도 순서: 공식 API(키가 있을 때) → FRED 웹 CSV → ALFRED(자매 사이트) CSV"""
    global _fred_net_fail
    since = (TODAY - timedelta(days=1100)).isoformat()
    tries = []
    if FRED_API_KEY:
        tries.append(("https://api.stlouisfed.org/fred/series/observations?series_id="
                      f"{sid}&api_key={FRED_API_KEY}&file_type=json&observation_start={since}", _fred_api, False))
    tries += [
        (f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={since}", _fred_csv, True),
        (f"https://alfred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={since}", _fred_csv, True),
    ]
    errors = []
    for url, parse, is_web in tries:
        if is_web and _fred_net_fail >= 4:
            errors.append("웹 접속 생략(앞선 연결 실패)")
            continue
        try:
            r = requests.get(url, headers=BROWSER, timeout=(10, 40))
            r.raise_for_status()
            rows = parse(r.text)
            if rows:
                if is_web:
                    _fred_net_fail = 0
                return sorted(rows)
            errors.append("데이터 없음")
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if is_web:
                _fred_net_fail += 1
            errors.append(f"연결 실패 {type(e).__name__}")
        except Exception as e:
            errors.append(f"{type(e).__name__} {str(e)[:80]}")
    hint = "" if FRED_API_KEY else " (해결: FRED_API_KEY 에 무료 키 입력)"
    raise RuntimeError(f"FRED {sid} 실패 → " + " | ".join(errors) + hint)


# ---- Fed H.6 (M2, 월간 계절조정, 십억달러) ----
def fedh6(col):
    url = ("https://www.federalreserve.gov/datadownload/Output.aspx?rel=H6"
           "&series=798e2796917702a5f8423426ba7e6b42&lastobs=40&from=&to="
           "&filetype=csv&label=include&layout=seriescolumn")
    rows = list(csv.reader(io.StringIO(get_text(url))))
    idx = next((i for i, h in enumerate(rows[0]) if h.startswith(f"{col}; Seasonally adjusted")), None)
    if idx is None:
        raise RuntimeError(f"H.6 '{col}; Seasonally adjusted' 열 없음")
    out = []
    for r in rows[1:]:
        if len(r) > idx and re.fullmatch(r"\d{4}-\d{2}", r[0]) and r[idx].strip():
            try:
                out.append((date.fromisoformat(r[0] + "-01"), float(r[idx])))
            except ValueError:
                pass
    if not out:
        raise RuntimeError("H.6 데이터 없음")
    return sorted(out)


# ---- BIS 정책금리 (일별, KR/JP/US 한 번에) ----
_BIS = {}


def bis(area):
    if not _BIS:
        since = (TODAY - timedelta(days=1100)).isoformat()
        url = ("https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/D.KR+JP+US"
               f"?detail=dataonly&format=csv&startPeriod={since}")
        for r in csv.DictReader(io.StringIO(get_text(url, timeout=30))):
            try:
                _BIS.setdefault(r["REF_AREA"], []).append(
                    (date.fromisoformat(r["TIME_PERIOD"]), float(r["OBS_VALUE"])))
            except (KeyError, ValueError):
                continue
        if not _BIS:
            raise RuntimeError("BIS 데이터 없음")
    if area not in _BIS:
        raise RuntimeError(f"BIS 에 {area} 없음")
    return sorted(_BIS[area])


def with_rate_changes(name, series):
    """정책금리: RATE_CHANGES 반영 + 마지막 값을 오늘까지 연장 (금리는 계단식)"""
    d = dict(series)
    for day, v in RATE_CHANGES.get(name, []):
        day = date.fromisoformat(day)
        before = [x for k, x in sorted(d.items()) if k < day]
        old = before[-1] if before else None
        for k in [k for k in d if k >= day and d[k] == old]:
            del d[k]           # BIS 가 아직 옛 금리로 채워둔 구간 제거
        d[day] = v
    s = sorted(d.items())
    if s and s[-1][0] < TODAY:
        s.append((TODAY, s[-1][1]))
    return s


# ---- 미국 재무부 일일 수익률 (3년치) ----
_TREASURY = {}


def treasury(col):
    if not _TREASURY:
        for yr in (TODAY.year - 2, TODAY.year - 1, TODAY.year):
            url = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
                   f"daily-treasury-rates.csv/{yr}/all?field_tdr_date_value={yr}"
                   "&type=daily_treasury_yield_curve")
            try:
                for r in csv.DictReader(io.StringIO(get_text(url))):
                    try:
                        d = datetime.strptime(r["Date"], "%m/%d/%Y").date()
                    except (KeyError, ValueError):
                        continue
                    for k, v in r.items():
                        try:
                            _TREASURY.setdefault(k, []).append((d, float(v)))
                        except (TypeError, ValueError):
                            pass
            except Exception as e:
                warn(f"Treasury {yr}년 CSV 실패: {e}")
    if col not in _TREASURY:
        raise RuntimeError(f"Treasury '{col}' 데이터 없음")
    return sorted(_TREASURY[col])


# ---- S&P500 선행 이익수익률 (현재값만 제공 → history 에 누적) ----
def fwd_ey(history):
    data = requests.get("https://historyofmarket.com/api/sp500/forward-pe.json", headers=UA, timeout=20).json()
    h = history.setdefault("S&P 500 Fwd EY", {})
    h[TODAY.isoformat()] = round(100 / data["current"]["forward"], 3)
    cutoff = (TODAY - timedelta(days=800)).isoformat()
    for k in [k for k in h if k < cutoff]:
        del h[k]
    return sorted((date.fromisoformat(k), v) for k, v in h.items())


def load_source(src, name, history):
    """출처 문자열 → (series, 현재값, 전일값 또는 None)"""
    kind, _, arg = src.partition(":")
    if kind == "yahoo":
        y = yahoo(arg)
        return y["series"], y["price"], y["prev"]
    if kind == "fwd_ey":
        s = fwd_ey(history)
        return s, s[-1][1], None
    if kind == "bis":
        s = with_rate_changes(name, bis(arg))
        return s, s[-1][1], None
    s = {"fred": fred, "fedh6": fedh6, "treasury": treasury}[kind](arg)
    if name in RATE_CHANGES:
        s = with_rate_changes(name, s)
    return s, s[-1][1], (s[-2][1] if len(s) >= 2 else None)


# =========================================================
# MARKET
# =========================================================

def build_market(old):
    old_items = {}
    for sec in old.get("market", []) if isinstance(old.get("market"), list) else []:
        for it in sec.get("items", []):
            old_items[(sec.get("sector"), it.get("name"))] = it

    prefetch_yahoo([t for items in MARKET.values() for t, _ in items.values()])

    out = []
    for sector, items in MARKET.items():
        rows = []
        for name, (ticker, theme) in items.items():
            try:
                y = yahoo(ticker)
                b = bases(y["series"])
                rows.append({
                    "name": name, "ticker": ticker, "theme": theme, "currency": y["currency"],
                    "price": rnd(y["price"]), "prev": rnd(y["prev"]),
                    "m1": rnd(b["m1"]), "y1": rnd(b["y1"]), "y2": rnd(b["y2"]),
                    "turnover": rnd(y["turnover"], 0),
                })
            except Exception as e:
                warn(f"MARKET {name}({ticker}) 실패: {e}")
                prev = old_items.get((sector, name))
                if prev:
                    rows.append({**prev, "stale": True})
        out.append({"sector": sector, "folded": sector in FOLDED_SECTORS, "items": rows})
    return out


# =========================================================
# MACRO
# =========================================================

def build_macro(old, history):
    old_items = {}
    for g in old.get("macro", []) if isinstance(old.get("macro"), list) else []:
        for it in g.get("items", []):
            old_items[it.get("name")] = it

    prefetch_yahoo([s.split(":", 1)[1] for items in MACRO.values()
                    for spec in items.values() for s in spec["src"] if s.startswith("yahoo:")])

    out = []
    for group, items in MACRO.items():
        rows = []
        for name, spec in items.items():
            show = {"name": name, "desc": spec.get("desc", ""), "kind": spec.get("kind", "pct"),
                    "prefix": spec.get("prefix", ""), "suffix": spec.get("suffix", ""),
                    "digits": spec.get("digits", 2)}
            vals = None

            if name in MANUAL_MACRO:
                m = MANUAL_MACRO[name]
                vals = {"value": m.get("value"), "prev": m.get("prev"),
                        "m1": m.get("m1"), "y1": m.get("y1"), "y2": m.get("y2")}
            else:
                for src in spec["src"]:
                    try:
                        series, value, prev = load_source(src, name, history)
                        k = spec.get("scale", 1)
                        b = bases(series)
                        if not spec.get("daily", True):
                            prev = None
                        vals = {"value": value * k,
                                "prev": None if prev is None else prev * k,
                                **{p: (None if v is None else v * k) for p, v in b.items()}}
                        print(f"[ok] MACRO {name} = {vals['value']:.4g} ({src})")
                        break
                    except Exception as e:
                        warn(f"MACRO {name} ← {src} 실패: {e}")

            if vals is not None:
                rows.append({**show, **{k: rnd(v) for k, v in vals.items()}})
            elif old_items.get(name, {}).get("value") is not None:
                rows.append({**old_items[name], **show, "stale": True})
                warn(f"MACRO {name}: 전부 실패 → 직전 값 표시")
            else:
                rows.append({**show, "value": spec.get("static"), "prev": None,
                             "m1": None, "y1": None, "y2": None, "stale": True})
                warn(f"MACRO {name}: 전부 실패 → 기본값 표시")
        out.append({"group": group, "items": rows})
    return out


def build_top(macro):
    by_name = {it["name"]: it for g in macro for it in g["items"]}
    return [{k: by_name[n].get(k) for k in ("name", "value", "prefix", "suffix", "digits")}
            for n in TOP_BAR if n in by_name]


# =========================================================
# EARNINGS (Yahoo quoteSummary: 쿠키 + crumb 필요)
# =========================================================

def yahoo_session():
    s = requests.Session()
    s.headers.update(UA)
    s.get("https://fc.yahoo.com", timeout=15)      # 쿠키 발급용 (404 여도 정상)
    crumb = s.get("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=15).text.strip()
    if not crumb or "<" in crumb or " " in crumb:
        raise ValueError(f"crumb 발급 실패: {crumb[:60]}")
    return s, crumb


def _raw(x):
    return x.get("raw") if isinstance(x, dict) else None


def _qkey(label):            # '2Q2025' → (2025, 2)
    try:
        return int(label[2:]), int(label[0])
    except Exception:
        return 0, 0


def fetch_earnings(sess, crumb, ticker):
    url = (f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}"
           f"?modules=calendarEvents,earnings&crumb={quote(crumb)}")
    res = sess.get(url, timeout=20).json()["quoteSummary"]["result"][0]

    ce = res["calendarEvents"]["earnings"]
    nxt = sorted((d["fmt"], d.get("raw")) for d in ce.get("earningsDate", [])
                 if d.get("fmt") and d["fmt"] >= TODAY.isoformat())

    earn = res.get("earnings") or {}
    chart = earn.get("earningsChart") or {}
    rev = {q.get("date"): _raw(q.get("revenue")) for q in (earn.get("financialsChart") or {}).get("quarterly", [])}
    past = sorted(({"label": q.get("date"), "eps_est": _raw(q.get("estimate")),
                    "eps_act": _raw(q.get("actual")), "rev_act": rev.get(q.get("date"))}
                   for q in chart.get("quarterly", []) if q.get("date")), key=lambda q: _qkey(q["label"]))

    cq, cy = chart.get("currentQuarterEstimateDate"), chart.get("currentQuarterEstimateYear")
    return {"date": nxt[0][0] if nxt else None, "ts": nxt[0][1] if nxt else None,
            "eps_est": _raw(ce.get("earningsAverage")), "rev_est": _raw(ce.get("revenueAverage")),
            "next_label": f"{cq}{cy}" if cq and cy else None, "past": past}


def build_earnings(old, history):
    old_rows = {e.get("symbol"): e for e in old.get("earnings", []) if isinstance(e, dict)}
    # 매출 '예상치'는 과거분을 주지 않아서, 발표 전 예상치를 저장해 두었다가 실제값 옆에 붙임
    est_hist = history.setdefault("earnings_est", {})

    try:
        sess, crumb = yahoo_session()
    except Exception as e:
        sess = crumb = None
        warn(f"EARNINGS 세션 실패: {e}")

    rows = []
    for sym, company in EARNINGS.items():
        row = {"symbol": sym, "name": company, "date": None, "ts": None,
               "eps_est": None, "rev_est": None, "quarters": []}
        try:
            if sess is None:
                raise RuntimeError("세션 없음")
            got = fetch_earnings(sess, crumb, sym)

            saved = est_hist.setdefault(sym, {})
            if got["next_label"] and (got["eps_est"] is not None or got["rev_est"] is not None):
                saved[got["next_label"]] = {"eps_est": got["eps_est"], "rev_est": got["rev_est"]}
            for k in list(saved)[:-8]:
                del saved[k]

            quarters = []
            for q in got["past"]:
                if q["eps_act"] is None and q["rev_act"] is None:
                    continue
                mem = saved.get(q["label"], {})
                quarters.append({"label": q["label"],
                                 "eps_est": rnd(q["eps_est"] if q["eps_est"] is not None else mem.get("eps_est")),
                                 "eps_act": rnd(q["eps_act"]),
                                 "rev_est": rnd(mem.get("rev_est"), 0), "rev_act": rnd(q["rev_act"], 0)})
            row.update({"date": got["date"], "ts": got["ts"], "eps_est": rnd(got["eps_est"]),
                        "rev_est": rnd(got["rev_est"], 0), "quarters": quarters[-3:]})
        except Exception as e:
            warn(f"EARNINGS {sym} 실패: {e}")
            prev = old_rows.get(sym)
            if prev:
                row.update({k: prev.get(k) for k in ("eps_est", "rev_est", "quarters")})
                if prev.get("date") and prev["date"] >= TODAY.isoformat():
                    row.update({"date": prev["date"], "ts": prev.get("ts")})
                row["stale"] = True
        rows.append(row)

    rows.sort(key=lambda r: (r["date"] is None, r["ts"] or 0, r["date"] or ""))
    return rows


# =========================================================
# EVENTS (FOMC / Fed Press / CPI / NFP / PCE / AI IPO / 임박한 실적)
# =========================================================

MONTH_RE = "January|February|March|April|May|June|July|August|September|October|November|December"
MONTHS = {m: i for i, m in enumerate(MONTH_RE.split("|"), start=1)}


def _strip_html(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def fomc_dates():
    """Fed 캘린더: 회의 마지막 날(성명 발표일)"""
    text = _strip_html(get_text("https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"))
    parts = re.split(r"(\d{4}) FOMC Meetings", text)
    if len(parts) == 1:
        parts = ["", str(TODAY.year), text]
    out = set()
    for i in range(1, len(parts) - 1, 2):
        for month, _d1, d2 in re.findall(rf"({MONTH_RE})\s+(\d{{1,2}})\s*[-–]\s*(\d{{1,2}})", parts[i + 1]):
            try:
                out.add(date(int(parts[i]), MONTHS[month], int(d2)))
            except ValueError:
                pass
    return sorted(out)


def bls_dates():
    """BLS .ics 일정: CPI, 고용보고서(NFP). GitHub 서버를 자주 차단함 → 실패 시 내장 일정"""
    text = re.sub(r"\r?\n[ \t]", "", get_text("https://www.bls.gov/schedule/news_release/bls.ics"))
    out = {"CPI": [], "NFP": []}
    for block in text.split("BEGIN:VEVENT")[1:]:
        d = re.search(r"DTSTART[^:\r\n]*:(\d{8})", block)
        s = re.search(r"SUMMARY:(.*)", block)
        if not d or not s:
            continue
        summary, day = s.group(1).strip(), datetime.strptime(d.group(1), "%Y%m%d").date()
        if re.fullmatch(r"Consumer Price Index( for .*)?", summary, re.I):
            out["CPI"].append(day)
        elif re.fullmatch(r"Employment Situation( for .*)?", summary, re.I):
            out["NFP"].append(day)
    return out


def pce_dates():
    """BEA 일정: 'October 29 8:30 AM | News | Personal Income and Outlays, September 2026'"""
    text = _strip_html(get_text("https://www.bea.gov/news/schedule"))
    out = []
    for m_rel, d_rel, m_ref, y_ref in re.findall(
        rf"({MONTH_RE})\s+(\d{{1,2}})(?:,?\s*\d{{4}})?\s+\d{{1,2}}:\d{{2}}\s*[AP]M[\s|]*"
        rf"(?:News|Data|Release)?[\s|]*Personal Income and Outlays,?\s+({MONTH_RE})\s+(\d{{4}})", text):
        yr = int(y_ref) + (1 if MONTHS[m_rel] < MONTHS[m_ref] else 0)   # 12월분은 다음 해 발표
        try:
            out.append(date(yr, MONTHS[m_rel], int(d_rel)))
        except ValueError:
            pass
    return out


def ai_ipo_dates():
    """Nasdaq IPO 캘린더(이번 달~2개월 뒤)에서 AI 관련 미국 상장 예정 → [(회사명, 날짜)]"""
    out = []
    for k in range(3):
        y, m = TODAY.year + (TODAY.month - 1 + k) // 12, (TODAY.month - 1 + k) % 12 + 1
        r = requests.get(f"https://api.nasdaq.com/api/ipo/calendar?date={y}-{m:02d}",
                         headers={**BROWSER, "Accept": "application/json, text/plain, */*",
                                  "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"},
                         timeout=20)
        r.raise_for_status()
        up = ((r.json().get("data") or {}).get("upcoming") or {})
        for row in ((up.get("upcomingTable") or {}).get("rows") or []):
            name = (row.get("companyName") or "").strip()
            d = row.get("expectedPriceDate") or ""
            if not name or not re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", d):
                continue
            if any(w in name.lower() for w in IPO_AI_KEYWORDS) or re.search(r"(?<![A-Za-z])AI(?![A-Za-z])", name):
                short = re.sub(r",?\s+(Inc\.?|Corp\.?|Corporation|Ltd\.?|Limited|Holdings?|Co\.?|PLC|N\.V\.|PBC)$",
                               "", name, flags=re.I)
                out.append((short, datetime.strptime(d, "%m/%d/%Y").date()))
    return out


def event_ts(name, d):
    t = EVENT_TIMES.get(name)
    if not t or NY is None:
        return None
    return int(datetime(d.year, d.month, d.day, t[0], t[1], tzinfo=NY).timestamp())


def build_events(earnings):
    found = {}       # (kind, name) → [date]

    def add(kind, name, days):
        found.setdefault((kind, name), []).extend(days)

    def auto_or_builtin(name, fn):
        got = []
        try:
            got = fn()
        except Exception as e:
            print(f"[info] {name} 자동 수집 실패 → 내장 일정 ({str(e)[:80]})")
        if not any(d >= TODAY for d in got):
            got = list(got) + [date.fromisoformat(x) for x in BUILTIN_EVENTS.get(name, [])]
        return got

    fomc = auto_or_builtin("FOMC", fomc_dates)
    add("macro", "FOMC", fomc)
    add("macro", "Fed Press", fomc)          # 성명 당일 오후 의장 기자회견
    try:
        b = bls_dates()
    except Exception as e:
        print(f"[info] BLS 접속 불가 → 내장 일정 ({str(e)[:60]})")
        b = {"CPI": [], "NFP": []}
    add("macro", "CPI", auto_or_builtin("CPI", lambda: b["CPI"]))
    add("macro", "NFP", auto_or_builtin("NFP", lambda: b["NFP"]))
    add("macro", "PCE", auto_or_builtin("PCE", pce_dates))

    try:
        for name, d in ai_ipo_dates():
            add("ipo", name, [d])
    except Exception as e:
        warn(f"AI IPO 일정 수집 실패 (MANUAL_EVENTS 로 직접 추가 가능): {str(e)[:100]}")

    for e in MANUAL_EVENTS:
        try:
            add(e.get("kind", "macro"), e["name"], [date.fromisoformat(e["date"])])
        except Exception as ex:
            warn(f"MANUAL_EVENTS 형식 오류 {e}: {ex}")

    events = []
    for (kind, name), days in found.items():
        upcoming = sorted({d for d in days
                           if (event_ts(name, d) or 0) > NOW.timestamp() or (event_ts(name, d) is None and d >= TODAY)})
        if upcoming:
            d = upcoming[0]
            events.append({"kind": kind, "name": name, "date": d.isoformat(), "ts": event_ts(name, d)})

    for r in earnings:       # 임박한 실적 발표
        if r["date"] and (date.fromisoformat(r["date"]) - TODAY).days <= EARN_SOON_DAYS:
            events.append({"kind": "earn", "name": r["symbol"], "date": r["date"], "ts": r["ts"]})

    def sort_key(e):
        if e["ts"]:
            return e["ts"]
        return datetime.fromisoformat(e["date"]).replace(tzinfo=KST).timestamp() + 86400
    events.sort(key=sort_key)
    return events


# =========================================================
# 실행
# =========================================================

def main():
    old = load_old()
    history = old.get("history") or {}
    if "S&P 500 Fwd Earnings Yield" in history and "S&P 500 Fwd EY" not in history:
        history["S&P 500 Fwd EY"] = history.pop("S&P 500 Fwd Earnings Yield")   # 이전 버전 누적값 이어받기

    def step(label, fn, fallback):
        try:
            return fn()
        except Exception as e:          # 영역 하나가 통째로 실패해도 나머지는 저장
            warn(f"{label} 전체 실패: {type(e).__name__} {e}")
            return fallback

    market = step("MARKET", lambda: build_market(old), [])
    macro = step("MACRO", lambda: build_macro(old, history), [])
    earnings = step("EARNINGS", lambda: build_earnings(old, history), [])
    events = step("EVENTS", lambda: build_events(earnings), [])

    output = {
        "updated_at": NOW.strftime("%Y-%m-%d %H:%M"),
        "updated_ts": int(NOW.timestamp()),
        "top": build_top(macro),
        "events": events,
        "market": market,
        "macro": macro,
        "earnings": earnings,
        "warnings": WARNINGS,
        "history": history,            # 화면에는 안 쓰임 (누적 데이터 보관용)
    }
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=1)

    print(f"saved data.json | market {sum(len(s['items']) for s in market)} | "
          f"macro {sum(len(g['items']) for g in macro)} | events {len(events)} | "
          f"earnings {sum(1 for e in earnings if e['date'])}/{len(earnings)} | warnings {len(WARNINGS)}")


if __name__ == "__main__":
    main()
