"""
Market Dashboard 데이터 수집 (TEST001.py → data.json)

수정하는 곳은 아래 [설정] 구역뿐입니다.
  - MARKET  : 관심종목 (섹터 → 표시이름 → Yahoo 티커)
  - MACRO   : 거시 지표 (+ RATE_CHANGES: 기준금리 변경 즉시 반영)
  - EARNINGS: 실적 발표 추적 기업
  - MANUAL_EVENTS / MANUAL_MACRO : 자동 수집이 안 될 때 직접 넣는 값
"""

import csv
import io
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
    # "표시이름": "티커"  또는  "표시이름": ("티커", "테마 라벨")   ← 테마 라벨은 카드에 작게 표시됨
    # 선물은 연결(front-month) 시세라 월물 교체 시기에 1M/1Y가 실제 시장 표기와 조금 다를 수 있음
    "에너지 / 원자재": {
        "Bitcoin": ("BTC-USD", "Crypto"), "Gold": ("GC=F", "귀금속"), "Silver": ("SI=F", "귀금속"),
        "Copper": ("HG=F", "산업금속"), "WTI Oil": ("CL=F", "원유"), "Natural Gas": ("NG=F", "천연가스"),
    },
    "지수": {"SPY": ("SPY", "S&P 500"), "QQQ": ("QQQ", "Nasdaq 100")},
    "레버리지 지수": {"SPXL 3x": ("SPXL", "S&P 500 3x"), "QLD 2x": ("QLD", "Nasdaq 100 2x"),
                "TQQQ 3x": ("TQQQ", "Nasdaq 100 3x")},
    # --- 거래량·관심도 최상위 반도체/AI ETF (개인 투자자 인기 레버리지 포함) ---
    "반도체 ETF": {
        "SMH": ("SMH", "반도체 지수 (시총가중)"), "SOXX": ("SOXX", "필라델피아 반도체"),
        "SOXL 3x": ("SOXL", "반도체 3x"), "NVDL 2x": ("NVDL", "NVDA 2x"),
    },
    "AI ETF": {
        "AIQ": ("AIQ", "AI · 빅데이터"), "BOTZ": ("BOTZ", "AI · 로보틱스"),
        "IGV": ("IGV", "소프트웨어"),
    },
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

    # --- AI 트렌드 (증권사 AI 밸류체인 분석에서 공통으로 꼽는 단계별 대장주, 시총 큰 종목 위주) ---
    "AI 네트워크 / 광통신": {      # GPU 클러스터 연결: 스위치·광모듈·DSP
        "ANET": ("ANET", "AI 데이터센터 스위치"), "MRVL": ("MRVL", "커스텀칩 · 광 DSP"),
        "CIEN": ("CIEN", "광전송"), "COHR": ("COHR", "광모듈 · 레이저"),
    },
    "AI 전력 / 냉각": {            # 데이터센터 병목 = 전력: 발전·전기설비·냉각
        "VRT": ("VRT", "전력 · 냉각 설비"), "GEV": ("GEV", "가스터빈 · 전력망"),
        "ETN": ("ETN", "전기설비"), "CEG": ("CEG", "원전 전력"), "VST": ("VST", "발전 · PPA"),
    },
    "데이터센터 / AI 클라우드": {  # AI 연산 임대·부지
        "CRWV": ("CRWV", "GPU 클라우드"), "EQIX": ("EQIX", "데이터센터 리츠"),
        "DLR": ("DLR", "데이터센터 리츠"),
    },
    "AI 서버": {"DELL": ("DELL", "AI 서버"), "SMCI": ("SMCI", "AI 서버 · 액침냉각")},
}

# =========================================================
# [설정] Market Growth : 현재가 기준 단순 연평균 성장률 = (현재가 / N년 전 가격 - 1) × 100 ÷ N
#   가격지수 기준(배당 미포함). 지수 ETF가 아니라 지수 자체를 써야 20년 데이터가 있음
# =========================================================

GROWTH = {"S&P 500": "^GSPC", "QQQ (Nasdaq 100)": "^NDX", "KOSPI": "^KS11", "KOSDAQ": "^KQ11"}
GROWTH_YEARS = [3, 5, 10, 15, 20]

# =========================================================
# [설정] MACRO : 그룹 -> {지표명: 스펙}
#   src    : 데이터 출처 (앞에서부터 시도, 실패하면 다음 출처로 자동 전환)
#            "fedh6:M2"      Fed H.6 (미국 M2, federalreserve.gov)
#            "bis:KR"        BIS 중앙은행 정책금리 (KR / JP / US)
#            "treasury:2 Yr" 미국 재무부 일일 수익률 (컬럼명)
#            "fred:DGS2"     FRED 시리즈
#            "yahoo:^VIX"    Yahoo 티커
#            "history"       data.json에 매일 누적 (Fwd Earnings Yield)
#   kind   : "pct" = 변화율(%) / "pp" = 변화량(%p)
#   scale  : 값에 곱할 배수 (M2: 십억달러 → 조달러)
#   static : 모든 출처가 실패했을 때 마지막으로 쓰는 값 ("캐시" 표시가 붙음)
#   chips  : "pct" 이면 1M/1Y/2Y 칸을 실제값 대신 변동률(%)로 표시 (기본은 실제값)
#   prefix / suffix : 화면 표시용
# =========================================================

MACRO = {
    "유동성 / 환율": {
        "US M2": {"src": ["fedh6:M2", "fred:M2SL"], "kind": "pct",
                  "prefix": "$", "suffix": "T", "scale": 0.001, "static": 23.0,
                  "day": False},  # day=False: 월간 데이터라 당일 변동률 없음
        "USD/KRW": {"src": ["yahoo:KRW=X"], "kind": "pct"},
        "USD/JPY": {"src": ["yahoo:JPY=X"], "kind": "pct"},
    },
    "기준금리": {
        "Korea Policy Rate": {"src": ["bis:KR"], "kind": "pp", "suffix": "%", "static": 3.0},
        "US Policy Rate": {"src": ["bis:US"], "kind": "pp", "suffix": "%", "static": 3.875},
        "Japan Policy Rate": {"src": ["bis:JP"], "kind": "pp", "suffix": "%", "static": 1.25},
    },
    "시장금리": {
        "US 3M": {"src": ["yahoo:^IRX", "treasury:3 Mo"], "kind": "pp", "suffix": "%"},
        "US 2Y": {"src": ["treasury:2 Yr", "fred:DGS2"], "kind": "pp", "suffix": "%"},
        "US 10Y": {"src": ["yahoo:^TNX", "treasury:10 Yr"], "kind": "pp", "suffix": "%"},
        "US 30Y": {"src": ["yahoo:^TYX", "treasury:30 Yr"], "kind": "pp", "suffix": "%"},
    },
    "밸류에이션 / 변동성": {
        # 과거값을 주는 무료 API가 없어서 data.json에 매일 1개씩 쌓아 1M/1Y를 계산함
        # (1M 표시까지 약 한 달, 1Y 표시까지 약 1년 걸림)
        "S&P 500 Fwd Earnings Yield": {"src": ["history"], "kind": "pp", "suffix": "%"},
        "VIX": {"src": ["yahoo:^VIX"], "kind": "pct"},
        # 신용 스프레드 (ICE BofA OAS, FRED). 단위 %, 변화는 %p. 하루 정도 늦게 갱신됨
        "HY Spread": {"src": ["fred:BAMLH0A0HYM2"], "kind": "pp", "suffix": "%"},
        "BBB Spread": {"src": ["fred:BAMLC0A4CBBB"], "kind": "pp", "suffix": "%"},
    },
}

# 기준금리는 BIS 데이터가 며칠~몇 주 늦게 반영됨. 금리가 바뀐 날 바로 반영하려면 여기에 추가.
# 형식: "지표명": [("변경일", 새 금리), ...]   (BIS가 따라잡으면 자동으로 무시됨)
RATE_CHANGES = {
    "Japan Policy Rate": [("2026-09-18", 1.25)],   # BOJ 인상 1.00 → 1.25
    # "Korea Policy Rate": [("2026-10-22", 3.25)],
    # "US Policy Rate": [("2026-10-28", 3.625)],   # 미국은 목표범위 중간값(예: 3.75~4.00 → 3.875)
}

# 자동 수집이 계속 실패하는 지표는 여기에 직접 입력하면 그 값이 우선 사용됨
MANUAL_MACRO = {
    # "Korea Policy Rate": {"value": 3.00, "prev_month": 2.75, "prev_year": 2.50},
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
# name은 FOMC / Fed Press / CPI / NFP / PCE, date는 미국 현지 날짜 (내장·자동 일정에 추가됨)
# =========================================================

MANUAL_EVENTS = [
    # {"name": "CPI", "date": "2026-10-14"},
    # IPO 는 이름을 "IPO · 회사명" 으로 쓰면 됨 (미국 현지 날짜). 아직 날짜가 안 정해진 건 정해지면 추가:
    # {"name": "IPO · Anthropic", "date": "2026-11-12"},
    # 날짜 미정이면 date 대신 note: (언론 보도 기준, 확정 아님)
    {"name": "IPO · Anthropic", "note": "11월 예상(보도)"},
]

# 미국 상장(Nasdaq IPO 캘린더) 중 AI 관련만 EVENTS 에 자동 표시.
# 회사 이름에 아래 단어가 들어 있으면 AI 관련으로 봄 (대소문자 무시). 필요하면 추가/삭제.
IPO_AI_KEYWORDS = [
    "anthropic", "openai", "databricks", "xai", "spacex", "cerebras", "coreweave", "lambda", "crusoe",
    "scale ai", "perplexity", "mistral", "groq", "sambanova", "nscale", "nebius",
    "artificial intelligence", "robotics", "machine learning", "generative", "intelligen", "neural", "compute",
]
IPO_AI_REGEX = r"(?<![A-Za-z])AI(?![A-Za-z])"   # 'AI' 단어 단독 (예: "Foo AI Inc")


# =========================================================
# 공통 유틸
# =========================================================

def rnd(x, n=4):
    return None if x is None else round(x, n)


def pick_base(series, period):
    """series: 날짜 오름차순 [(date, value)].
    period="month" → 지난달 마지막 거래일 종가 (1M 기준)
    period="year"  → 작년 마지막 거래일 종가  (1Y 기준)
    period="2year" → 재작년 마지막 거래일 종가 (2Y 기준, MACRO만)
    기준일은 series의 최신 날짜. 해당 값이 없으면 None."""
    if not series:
        return None
    last = series[-1][0]
    if period == "month":
        limit = last.replace(day=1)
    elif period == "year":
        limit = date(last.year, 1, 1)
    else:  # "2year" → 재작년 마지막 거래일 종가 (MACRO 전용)
        limit = date(last.year - 1, 1, 1)
    older = [v for d, v in series if d < limit]
    return older[-1] if older else None


def load_old():
    try:
        with open("data.json", encoding="utf-8") as f:
            old = json.load(f)
    except Exception:
        return {}
    # 예전 형식(리스트 등)의 data.json 이 남아 있어도 에러 안 나게 형식 검사
    if not isinstance(old, dict):
        return {}
    for k, t in (("macro", dict), ("market", dict), ("history", dict), ("earnings", list)):
        if not isinstance(old.get(k), t):
            old[k] = t()
    return old


OLD = load_old()

WARNINGS = []   # 수집 실패 사유 → data.json에 저장되어 화면 맨 아래 "수집 경고"에 표시됨


def warn(msg):
    print("[warn] " + msg)
    if len(WARNINGS) < 40:
        WARNINGS.append(msg[:220])


# =========================================================
# Yahoo Finance 시세 (기존 방식 유지: chart API, 3년 일봉)
# =========================================================

_YAHOO_CACHE = {}


def fetch_yahoo(ticker):
    if ticker in _YAHOO_CACHE:
        return _YAHOO_CACHE[ticker]

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=3y&interval=1d"

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
    price = meta.get("regularMarketPrice") or series[-1][1]

    # 거래대금 = 거래량 × 가격 (주식/ETF). 코인은 거래량이 이미 달러 기준. 선물·환율·지수는 제외
    vols = result["indicators"]["quote"][0].get("volume") or []
    volume = meta.get("regularMarketVolume") or next((v for v in reversed(vols) if v), None)
    itype = meta.get("instrumentType")
    if not volume:
        turnover = None
    elif itype == "CRYPTOCURRENCY":
        turnover = volume
    elif itype in ("EQUITY", "ETF"):
        turnover = volume * price
    else:
        turnover = None

    data = {
        "price": price,
        "currency": meta.get("currency", "USD"),
        "series": series,
        "prev_day": series[-2][1] if len(series) >= 2 else None,  # 직전 거래일 종가 → 당일 변동률
        "turnover": turnover,
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


# FRED가 GitHub Actions 서버에서 막히거나 느릴 때를 위한 선택 사항:
# https://fredaccount.stlouisfed.org/apikeys 에서 무료 API 키를 받아 아래에 넣으면
# 웹 다운로드가 실패해도 공식 API(api.stlouisfed.org)로 한 번 더 시도함. 비워두면 사용 안 함.
# (저장소가 공개라면 키가 노출되니 FRED 전용 무료 키만 사용)
FRED_API_KEY = ""


def _parse_fred_api(text):
    return [(date.fromisoformat(o["date"]), float(o["value"]))
            for o in json.loads(text)["observations"] if o["value"] not in (".", "")]


def fetch_fred(series_ids):
    """FRED 공개 데이터. 시리즈 ID를 리스트로 주면 앞에서부터 시도.
    시도 순서: 공식 API(키가 있을 때) → FRED 웹 CSV → ALFRED(FRED 자매 사이트) CSV
    (GitHub Actions에서 FRED 웹이 ReadTimeout 나는 경우가 있어 API 키 사용을 권장)"""
    global _fred_net_fail
    ids = [series_ids] if isinstance(series_ids, str) else series_ids
    since = (TODAY - timedelta(days=1000)).isoformat()
    errors = []

    for sid in ids:
        sources = []
        if FRED_API_KEY:
            sources.append((
                "https://api.stlouisfed.org/fred/series/observations?series_id="
                f"{sid}&api_key={FRED_API_KEY}&file_type=json&observation_start={since}",
                _parse_fred_api, False))
        sources += [
            (f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={since}", _parse_fred_csv, True),
            (f"https://alfred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={since}", _parse_fred_csv, True),
        ]

        for url, parser, is_web in sources:
            if is_web and _fred_net_fail >= 4:
                errors.append(f"{sid}: 웹 접속 생략(앞선 연결 실패)")
                continue
            try:
                r = requests.get(url, headers=BROWSER_UA, timeout=(10, 40))  # (연결, 응답대기) 초
                r.raise_for_status()
                rows = [x for x in parser(r.text) if x[0] >= TODAY - timedelta(days=1000)]
                if rows:
                    if is_web:
                        _fred_net_fail = 0
                    return rows
                errors.append(f"{sid}: 응답에 데이터 없음")
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                if is_web:
                    _fred_net_fail += 1
                errors.append(f"{sid}: 연결 실패 {type(e).__name__}")
            except Exception as e:
                errors.append(f"{sid}: {type(e).__name__} {str(e)[:100]}")

    hint = "" if FRED_API_KEY else " (해결: TEST001.py의 FRED_API_KEY에 무료 키 입력)"
    raise RuntimeError("FRED 실패 → " + " | ".join(errors[-5:]) + hint)


def fetch_forward_earnings_yield():
    data = requests.get(
        "https://historyofmarket.com/api/sp500/forward-pe.json",
        headers=UA, timeout=20,
    ).json()
    return 100 / data["current"]["forward"]


def _get(url, **kw):
    r = requests.get(url, headers=BROWSER_UA, timeout=kw.pop("timeout", 20), **kw)
    r.raise_for_status()
    return r.text


def fetch_fedh6(col):
    """Fed H.6 (월간, 계절조정). col='M2' → 'M2; Seasonally adjusted' 열. 단위: 십억달러."""
    url = ("https://www.federalreserve.gov/datadownload/Output.aspx?rel=H6"
           "&series=798e2796917702a5f8423426ba7e6b42&lastobs=40&from=&to="
           "&filetype=csv&label=include&layout=seriescolumn")
    rows = list(csv.reader(io.StringIO(_get(url))))
    idx = next((i for i, h in enumerate(rows[0]) if h.startswith(f"{col}; Seasonally adjusted")), None)
    if idx is None:
        raise RuntimeError(f"H.6에서 '{col}; Seasonally adjusted' 열을 찾지 못함")
    out = []
    for r in rows[1:]:
        if len(r) > idx and re.fullmatch(r"\d{4}-\d{2}", r[0]) and r[idx].strip():
            try:
                out.append((datetime.strptime(r[0] + "-01", "%Y-%m-%d").date(), float(r[idx])))
            except ValueError:
                pass
    if not out:
        raise RuntimeError("H.6 데이터 없음")
    return sorted(out)


_BIS = {}


def fetch_bis(area):
    """BIS 정책금리 일별 데이터 (KR/JP/US). 한 번만 받아서 3개국 공유."""
    if not _BIS:
        since = (TODAY - timedelta(days=1000)).isoformat()
        url = ("https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/D.KR+JP+US"
               f"?detail=dataonly&format=csv&startPeriod={since}")
        for r in csv.DictReader(io.StringIO(_get(url, timeout=30))):
            try:
                _BIS.setdefault(r["REF_AREA"], []).append(
                    (date.fromisoformat(r["TIME_PERIOD"]), float(r["OBS_VALUE"])))
            except (KeyError, ValueError):
                continue
        if not _BIS:
            raise RuntimeError("BIS 데이터 없음")
    if area not in _BIS:
        raise RuntimeError(f"BIS에 {area} 없음")
    return sorted(_BIS[area])


def fetch_treasury(col):
    """미국 재무부 일일 par yield (올해+작년). col 예: '2 Yr', '3 Mo', '10 Yr'."""
    out = []
    for yr in (TODAY.year - 2, TODAY.year - 1, TODAY.year):
        url = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
               f"daily-treasury-rates.csv/{yr}/all?field_tdr_date_value={yr}"
               "&type=daily_treasury_yield_curve")
        try:
            for r in csv.DictReader(io.StringIO(_get(url))):
                try:
                    out.append((datetime.strptime(r["Date"], "%m/%d/%Y").date(), float(r[col])))
                except (KeyError, ValueError, TypeError):
                    continue
        except Exception as e:
            warn(f"Treasury {yr}: {e}")
    if not out:
        raise RuntimeError("Treasury 데이터 없음")
    return sorted(out)


def with_rate_changes(name, series):
    """정책금리: 수동 변경 내역을 합치고, 마지막 값을 오늘까지 이어붙임(금리는 계단식)."""
    d = dict(series)
    for day, v in RATE_CHANGES.get(name, []):
        day = date.fromisoformat(day)
        before = [x for k, x in sorted(d.items()) if k < day]
        old = before[-1] if before else None
        for k in [k for k in d if k >= day and d[k] == old]:
            del d[k]                 # BIS가 아직 옛 금리로 채워둔 구간 제거
        d[day] = v
    s = sorted(d.items())
    if s[-1][0] < TODAY:
        s.append((TODAY, s[-1][1]))
    return s


def get_series(source):
    """'종류:인자' 문자열 → (series, 현재값)"""
    kind, _, arg = source.partition(":")
    if kind == "yahoo":
        y = fetch_yahoo(arg)
        return y["series"], y["price"]
    if kind == "fred":
        s = fetch_fred(arg)
    elif kind == "fedh6":
        s = fetch_fedh6(arg)
    elif kind == "bis":
        s = fetch_bis(arg)
    elif kind == "treasury":
        s = fetch_treasury(arg)
    else:
        raise ValueError(f"알 수 없는 출처 {source}")
    return s, s[-1][1]


# =========================================================
# MARKET
# =========================================================

market = {}

for sector, items in MARKET.items():
    market[sector] = {}
    for name, spec in items.items():
        ticker, theme = spec if isinstance(spec, tuple) else (spec, "")
        try:
            y = fetch_yahoo(ticker)
            market[sector][name] = {
                "ticker": ticker,
                "theme": theme,
                "currency": y["currency"],
                "price": rnd(y["price"]),
                "prev_day": rnd(y["prev_day"]),
                "turnover": rnd(y["turnover"], 0),
                "prev_month": rnd(pick_base(y["series"], "month")),
                "prev_year": rnd(pick_base(y["series"], "year")),
                "prev_2year": rnd(pick_base(y["series"], "2year")),
            }
        except Exception as e:
            warn(f"MARKET {name}({ticker}) 실패: {e}")
            prev = OLD.get("market", {}).get(sector, {}).get(name)
            if prev:  # 실패하면 직전 값 유지 → 화면이 비지 않게
                market[sector][name] = prev



# =========================================================
# MACRO  (출처를 순서대로 시도 → 다 실패하면 직전 값 → static 값, 이때 "stale" 표시)
# =========================================================

history = OLD.get("history", {})  # {지표명: {"YYYY-MM-DD": 값}}

macro = {}

for group, items in MACRO.items():
    macro[group] = {}
    for name, spec in items.items():

        display = {k: spec[k] for k in ("kind", "prefix", "suffix", "digits", "chips") if k in spec}
        item = None

        if name in MANUAL_MACRO:
            m = MANUAL_MACRO[name]
            item = {"value": m["value"], "prev_month": m.get("prev_month"),
                    "prev_year": m.get("prev_year"),
                    "prev_2year": m.get("prev_2year"), "prev_day": m.get("prev_day")}
            used = "manual"
        else:
            errors = []
            for source in spec["src"]:
                try:
                    if source == "history":
                        h = history.setdefault(name, {})
                        h[TODAY.isoformat()] = round(fetch_forward_earnings_yield(), 3)
                        cutoff = (TODAY - timedelta(days=400)).isoformat()
                        for k in [k for k in h if k < cutoff]:
                            del h[k]
                        series = sorted((date.fromisoformat(k), v) for k, v in h.items())
                        value = series[-1][1]
                    else:
                        series, value = get_series(source)
                        if name in RATE_CHANGES or source.startswith("bis"):
                            series = with_rate_changes(name, series)
                            value = series[-1][1]

                    s = spec.get("scale", 1)
                    # 당일 변동률은 일별 시세 출처(yahoo/treasury/fred)만. 정책금리·월간 M2·누적 지표는 제외
                    daily = source.split(":")[0] in ("yahoo", "treasury", "fred") and spec.get("day", True)
                    pd_ = series[-2][1] if daily and len(series) >= 2 else None
                    pm, py, p2 = (pick_base(series, "month"), pick_base(series, "year"),
                                  pick_base(series, "2year"))
                    item = {"value": value * s,
                            "prev_month": None if pm is None else pm * s,
                            "prev_year": None if py is None else py * s,
                            "prev_2year": None if p2 is None else p2 * s,
                            "prev_day": None if pd_ is None else pd_ * s}
                    used = source
                    break
                except Exception as e:
                    errors.append(f"{source}: {e}")
                    warn(f"MACRO {name} ← {source} 실패: {e}")

        if item is not None:
            item = {k: rnd(v) for k, v in item.items()}
            macro[group][name] = {**item, **display}
            print(f"[ok] MACRO {name} = {item['value']} ({used})")
            continue

        prev = OLD.get("macro", {}).get(group, {}).get(name)
        if prev and prev.get("value") is not None:      # 직전 값 유지
            macro[group][name] = {**prev, "stale": True}
        elif "static" in spec:                           # 마지막 수단
            macro[group][name] = {"value": spec["static"], "prev_month": None,
                                  "prev_year": None, "stale": True, **display}
        else:
            macro[group][name] = {"value": None, "prev_month": None,
                                  "prev_year": None, **display}
        warn(f"MACRO {name} 전체 실패 → 캐시/static 사용")


# =========================================================
# EVENTS (FOMC / Fed Press / CPI / NFP / PCE) - 미국 현지 날짜, 다음 예정 1건씩
#   1순위: 공식 사이트 자동 수집  2순위: BUILTIN(내장 일정)  + MANUAL_EVENTS(직접 입력)
# =========================================================

MONTH_RE = ("January|February|March|April|May|June|July|August|"
            "September|October|November|December")
MONTHS = {m: i for i, m in enumerate(MONTH_RE.split("|"), start=1)}

# 자동 수집이 실패했을 때만 쓰이는 내장 일정 (Fed / BLS / BEA 공식 발표 기준, 연 1회 갱신)
BUILTIN_EVENTS = {
    "FOMC": ["2026-10-28", "2026-12-09"],
    "CPI": ["2026-10-14", "2026-11-10", "2026-12-10"],
    "NFP": ["2026-10-02", "2026-11-06", "2026-12-04"],
    "PCE": ["2026-09-30", "2026-10-29", "2026-11-25"],
}


def strip_html(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def fomc_dates():
    """Fed 캘린더: 회의 마지막 날(성명·기자회견일)."""
    text = strip_html(_get("https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"))

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
    """BLS 발표 일정(.ics): CPI, 고용보고서(NFP). 제목이 정확히 일치하는 것만 사용."""
    text = _get("https://www.bls.gov/schedule/news_release/bls.ics")
    text = re.sub(r"\r?\n[ \t]", "", text)  # ics 줄바꿈 접힘 해제

    out = {"CPI": [], "NFP": []}
    for block in text.split("BEGIN:VEVENT")[1:]:
        d = re.search(r"DTSTART[^:\r\n]*:(\d{8})", block)
        s = re.search(r"SUMMARY:(.*)", block)
        if not d or not s:
            continue
        summary = s.group(1).strip()
        day = datetime.strptime(d.group(1), "%Y%m%d").date()
        if re.fullmatch(r"Consumer Price Index( for .*)?", summary, re.I):
            out["CPI"].append(day)
        elif re.fullmatch(r"Employment Situation( for .*)?", summary, re.I):
            out["NFP"].append(day)
    return out


def pce_dates():
    """BEA 일정 행: 'September 30 8:30 AM | News | Personal Income and Outlays, August 2026'"""
    text = strip_html(_get("https://www.bea.gov/news/schedule"))

    dates = []
    for m_rel, d_rel, m_ref, y_ref in re.findall(
        rf"({MONTH_RE})\s+(\d{{1,2}})(?:,?\s*\d{{4}})?\s+\d{{1,2}}:\d{{2}}\s*[AP]M[\s|]*"
        rf"(?:News|Data|Release)?[\s|]*Personal Income and Outlays,?\s+({MONTH_RE})\s+(\d{{4}})",
        text,
    ):
        yr = int(y_ref) + (1 if MONTHS[m_rel] < MONTHS[m_ref] else 0)  # 12월분은 다음 해 발표
        try:
            dates.append(date(yr, MONTHS[m_rel], int(d_rel)))
        except ValueError:
            pass
    return dates


found = {"FOMC": [], "Fed Press": [], "CPI": [], "NFP": [], "PCE": []}


def collect(name, fn):
    """자동 수집 → 예정일이 하나도 없으면 내장 일정 사용"""
    got = []
    try:
        got = fn()
    except Exception as e:
        warn(f"{name} 일정 자동 수집 실패: {e}")
    if not any(d >= TODAY for d in got):
        print(f"[info] {name}: 내장 일정 사용")
        got = list(got) + [date.fromisoformat(x) for x in BUILTIN_EVENTS.get(name, [])]
    return got


found["FOMC"] = collect("FOMC", fomc_dates)
found["Fed Press"] = list(found["FOMC"])  # FOMC 성명 당일 오후 의장 기자회견

try:
    _b = bls_dates()
except Exception as e:
    _b = {"CPI": [], "NFP": []}
    print(f"[info] BLS 일정 접속 불가({str(e)[:60]}) → 내장 일정 사용")  # BLS는 GitHub 서버를 차단하는 경우가 많아 경고 대신 안내만
found["CPI"] = collect("CPI", lambda: _b["CPI"])
found["NFP"] = collect("NFP", lambda: _b["NFP"])
found["PCE"] = collect("PCE", pce_dates)

IPO_STATS = {"rows": 0, "ai": 0}


def ipo_dates():
    """Nasdaq IPO 캘린더(이번 달~2개월 뒤)에서 AI 관련 상장 예정일. 반환: [(이름, 날짜)]"""
    out = []
    for k in range(3):
        m0 = TODAY.replace(day=1)
        y, mth = m0.year + (m0.month - 1 + k) // 12, (m0.month - 1 + k) % 12 + 1
        r = requests.get(
            f"https://api.nasdaq.com/api/ipo/calendar?date={y}-{mth:02d}",
            headers={**BROWSER_UA, "Accept": "application/json, text/plain, */*",
                     "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"},
            timeout=20)
        r.raise_for_status()
        data = (r.json().get("data") or {})
        # 구조: data.upcoming.upcomingTable.rows / data.priced.rows
        groups = [((data.get("upcoming") or {}).get("upcomingTable") or {}).get("rows"),
                  (data.get("upcoming") or {}).get("rows"),
                  (data.get("priced") or {}).get("rows")]
        for rows in groups:
            for row in rows or []:
                IPO_STATS["rows"] += 1
                name = (row.get("companyName") or "").strip()
                d = row.get("expectedPriceDate") or row.get("pricedDate") or ""
                if not name or not re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", d):
                    continue
                low = name.lower()
                if any(w in low for w in IPO_AI_KEYWORDS) or re.search(IPO_AI_REGEX, name):
                    IPO_STATS["ai"] += 1
                    out.append((name, datetime.strptime(d, "%m/%d/%Y").date()))
    return out


try:
    for _n, _d in ipo_dates():
        _short = re.sub(r",?\s+(Inc\.?|Corp\.?|Corporation|Ltd\.?|Limited|Holdings?|Co\.?|PLC|N\.V\.)$", "", _n, flags=re.I)
        found.setdefault("IPO · " + _short, []).append(_d)
    if IPO_STATS["rows"] == 0:
        warn("IPO 캘린더 응답에 종목이 0개 (Nasdaq 차단/구조 변경 가능성) - MANUAL_EVENTS 로 추가 가능")
    elif IPO_STATS["ai"] == 0:
        warn(f"IPO 캘린더 {IPO_STATS['rows']}건 중 AI 관련 0건 (정상일 수 있음. 키워드는 IPO_AI_KEYWORDS)")
except Exception as _e:
    warn(f"IPO 일정 자동 수집 실패 (MANUAL_EVENTS 로 직접 추가 가능): {str(_e)[:120]}")

# 날짜 미정 일정 (MANUAL_EVENTS 에 date 없이 note 만 쓴 것) - EVENTS 맨 뒤에 '예정'으로 표시
tentative = []

for e in MANUAL_EVENTS:
    try:
        if not e.get("date"):
            tentative.append({"name": e["name"], "date": None, "ts": None, "d_day": None, "note": e.get("note", "미정")})
            continue
        found.setdefault(e["name"], []).append(date.fromisoformat(e["date"]))
    except Exception as ex:
        warn(f"MANUAL_EVENTS 형식 오류 {e}: {ex}")

# 발표 시각 (미국 동부시간, 시:분) → 화면에서 한국시간·남은 시간으로 변환됨
EVENT_TIMES = {"FOMC": (14, 0), "Fed Press": (14, 30), "CPI": (8, 30), "NFP": (8, 30), "PCE": (8, 30)}

try:
    from zoneinfo import ZoneInfo
    NY = ZoneInfo("America/New_York")
except Exception:
    NY = None


def event_ts(name, d):
    t = EVENT_TIMES.get(name)
    if not t or NY is None:
        return None
    return int(datetime(d.year, d.month, d.day, t[0], t[1], tzinfo=NY).timestamp())


def is_upcoming(name, d):
    ts = event_ts(name, d)
    return ts > NOW.timestamp() if ts else d >= TODAY


events = []
for name, days in found.items():
    upcoming = sorted(d for d in days if is_upcoming(name, d))
    if upcoming:
        events.append({
            "name": name,
            "date": upcoming[0].isoformat(),
            "ts": event_ts(name, upcoming[0]),
            "d_day": (upcoming[0] - TODAY).days,
        })
events.sort(key=lambda e: (e["ts"] or 0) if e["ts"] else e["d_day"] * 86400 + NOW.timestamp())
# 같은 회사의 날짜 확정 일정이 이미 있으면 미정 항목은 생략
_have = {e["name"].lower() for e in events}
events += [t for t in tentative if not any(h.startswith(t["name"].lower()) for h in _have)]


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
    cands = sorted(
        (d["fmt"], d.get("raw")) for d in ce.get("earningsDate", [])
        if d.get("fmt") and d["fmt"] >= TODAY.isoformat()
    )
    dates = [c[0] for c in cands]

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
        "ts": cands[0][1] if cands else None,   # 발표 예정 시각(UTC 초) → 남은 시간 계산용
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
    warn(f"EARNINGS 세션 실패: {e}")

for symbol, company in EARNINGS.items():
    row = {"symbol": symbol, "name": company, "date": None, "ts": None, "d_day": None,
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

        row.update({"date": got["date"], "ts": got["ts"], "eps_est": rnd(got["eps_est"]),
                    "rev_est": got["rev_est"], "quarters": quarters[-3:]})
    except Exception as e:
        warn(f"EARNINGS {symbol} 실패: {e}")
        prev = old_earn.get(symbol)
        if prev:  # 실패하면 직전 값 유지
            row.update({k: prev.get(k) for k in ("eps_est", "rev_est")})
            row["quarters"] = prev.get("quarters", [])
            if prev.get("date") and prev["date"] >= TODAY.isoformat():
                row["date"] = prev["date"]
                row["ts"] = prev.get("ts")

    if row["date"]:
        row["d_day"] = (date.fromisoformat(row["date"]) - TODAY).days
    earnings.append(row)

earnings.sort(key=lambda r: (r["d_day"] is None, r["d_day"] if r["d_day"] is not None else 0))


# =========================================================
# Market Growth (Yahoo 25년 주봉)
# =========================================================

def fetch_long(ticker):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=25y&interval=1wk"
    last_err = None
    for _ in range(2):
        try:
            res = requests.get(url, headers=UA, timeout=25).json()["chart"]["result"][0]
            break
        except Exception as e:
            last_err = e
    else:
        raise last_err
    series = [(datetime.fromtimestamp(t, timezone.utc).date(), c)
              for t, c in zip(res["timestamp"], res["indicators"]["quote"][0]["close"]) if c]
    return series, res["meta"].get("regularMarketPrice") or series[-1][1]


growth = {}
for gname, gtk in GROWTH.items():
    try:
        series, price = fetch_long(gtk)
        row = {"ticker": gtk, "price": price}
        for n in GROWTH_YEARS:
            target = date(TODAY.year - n, TODAY.month, min(TODAY.day, 28))
            older = [v for d, v in series if d <= target]
            # 데이터가 부족하면(상장 전 등) 값 없음. 시작일이 목표일보다 2주 넘게 늦으면 부족한 것으로 봄
            ok = older and (target - [d for d, v in series if d <= target][-1]).days <= 14
            row[f"{n}Y"] = rnd((price / older[-1] - 1) * 100 / n, 2) if ok else None
        growth[gname] = row
        print(f"[ok] GROWTH {gname}: " + ", ".join(f"{n}Y {row[f'{n}Y']}" for n in GROWTH_YEARS))
    except Exception as e:
        warn(f"Market Growth {gname}({gtk}) 수집 실패: {str(e)[:100]}")
        if OLD.get("growth", {}).get(gname):
            growth[gname] = OLD["growth"][gname]


# =========================================================
# 저장
# =========================================================

output = {
    "updated_at": NOW.strftime("%Y-%m-%d %H:%M KST"),
    "warnings": WARNINGS,
    "macro": macro,
    "events": events,
    "earnings": earnings,
    "market": market,
    "growth": growth,
    "history": history,  # 화면에는 안 쓰임. 지표 히스토리 누적용
}

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=1)

n_market = sum(len(v) for v in market.values())
n_macro = sum(len(v) for v in macro.values())
print(f"saved data.json | market {n_market} | macro {n_macro} | "
      f"events {len(events)} | earnings {sum(1 for e in earnings if e['date'])}/{len(earnings)} "
      f"(지난분기 있음 {sum(1 for e in earnings if e['quarters'])})")

