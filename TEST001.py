import requests, json, re, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta, date
from urllib.parse import quote_plus

# =========================================================
# 종목/지표 설정
#
# 구조: 대분류(category) -> 테마(theme) -> 표시이름 -> 스펙
# 스펙: "SPY" (일반) 또는 {"ticker": "SPXL", "leverage_of": "SPY"} (레버리지)
# =========================================================

STOCKS = {
    "US Stocks": {
        "Broad Market": {
            "SPY": "SPY",
            "SPXL": {"ticker": "SPXL", "leverage_of": "SPY"},
            "QLD": {"ticker": "QLD", "leverage_of": "QQQ"},
        },
        "AI & Semiconductors": {
            "NVDA": "NVDA",
            "NVDL": {"ticker": "NVDL", "leverage_of": "NVDA"},
            "AMD": "AMD",
            "MU": "MU",
            "MUU": {"ticker": "MUU", "leverage_of": "MU"},
            "SNDK": "SNDK",
            "SNXX": {"ticker": "SNXX", "leverage_of": "SNDK"},
            "PLTR": "PLTR",
        },
        "Mega Cap / Cloud": {
            "AMZN": "AMZN",
            "GOOG": "GOOG",
            "ORCL": "ORCL",
        },
    },
    "KR Stocks": {
        "Large Cap Tech": {
            "Samsung": "005930.KS",
            "SKHynix": "000660.KS",
        },
        "Broad Market (Leveraged)": {
            "KORU": "KORU",
        },
    },
    "Commodities & Crypto": {
        "Commodities & Crypto": {
            "Gold": "GC=F",
            "Crude Oil": "CL=F",
            "Bitcoin": "BTC-USD",
        },
    },

}

# QQQ / Nasdaq-100 구성종목 (자동 수집)
QQQ_TOP_COUNT = 10

INDICATORS = {
    "Rates & FX": {
        "US 10Y Yield": "^TNX",
        "US 3M Yield": "^IRX",
        "USD/JPY": "JPY=X",
    },
    "Volatility & Valuation": {
        "VIX": "^VIX",
        # S&P500 Forward Earnings Yield는 별도 API로 아래에서 추가됨
    },
}

# 트렌딩(많이 검색되는 종목) 설정
TRENDING_REGION = "US"
TRENDING_COUNT = 10

# =========================================================
# AI 트렌드 키워드 (수동 큐레이션 - 설명/관련종목은 직접 수정)
# 가격/시총/등락은 스크립트가 매번 자동으로 갱신함
# =========================================================

AI_TRENDS = {
    "AI 데이터센터 / CapEx": {
        "description": "빅테크(하이퍼스케일러)의 AI 데이터센터 투자가 계속 확대되는 흐름",
        "tickers": ["NVDA", "MSFT", "AMZN", "GOOGL", "ORCL"],
    },
    "AI 전력 / 인프라": {
        "description": "AI 데이터센터의 전력 수요 급증으로 전력·변압기·냉각 설비가 병목으로 부각",
        "tickers": ["GEV", "ETN", "VRT", "CEG", "VST"],
    },
    "AI 추론 (Inference)": {
        "description": "학습(training) 중심에서 실제 서비스 추론 수요로 투자 축이 이동",
        "tickers": ["NVDA", "AVGO", "EQIX", "MSFT", "AMZN"],
    },
    "커스텀 AI 칩 / ASIC": {
        "description": "하이퍼스케일러들이 자체 AI 칩을 개발하며 GPU 외 AI 반도체 수요 확대",
        "tickers": ["AVGO", "NVDA", "AMD"],
    },
    "AI 네트워킹 / 인터커넥트": {
        "description": "AI 서버간 데이터 이동 증가로 고속 네트워크/광통신 중요도 상승",
        "tickers": ["AVGO", "ANET", "NVDA"],
    },
    "HBM / AI 메모리": {
        "description": "AI 연산 증가에 따른 고대역폭 메모리(HBM) 수요 지속",
        "tickers": ["MU"],
    },
    "엔터프라이즈 / 에이전틱 AI": {
        "description": "기업 실무에 AI를 실제로 배치하는 단계로 이동",
        "tickers": ["MSFT", "AMZN", "GOOGL", "META", "PLTR"],
    },
    "AI 인프라 파이낸싱": {
        "description": "데이터센터 건설 자금조달(회사채·IPO 등) 자체가 시장 이슈로 부각",
        "tickers": ["CRWV"],
    },
}

# =========================================================
# AI 주요 이벤트 (수동 관리 - 공식 자동 캘린더가 없어 직접 갱신 필요)
# date가 없고 ongoing=True인 항목은 항상 노출됨
# =========================================================

AI_EVENTS = [
    {
        "name": "Accelevation IPO",
        "date": "2026-09-28",
        "note": "AI 데이터센터용 전력분배/냉각 인프라 기업, Nasdaq 상장 예정 (시기 유동적)",
        "related": ["VRT", "ETN", "GEV"],
    },
    {
        "name": "Anthropic IPO (예상)",
        "date": "2026-10-15",
        "note": "AI 모델 기업 IPO 준비 중이라는 보도 - 확정 일정 아님",
        "related": ["AMZN", "GOOGL", "MSFT"],
    },
    {
        "name": "OpenAI IPO 보류",
        "date": None,
        "note": "2026년 중에는 IPO를 진행하지 않겠다고 발표",
        "related": ["MSFT"],
        "ongoing": True,
    },
    {
        "name": "AI 데이터센터 CapEx 확대",
        "date": None,
        "note": "빅테크의 데이터센터/전력/네트워크 투자 확대가 계속 진행 중",
        "related": ["NVDA", "AVGO", "VRT", "GEV", "ETN", "CEG"],
        "ongoing": True,
    },
]


# =========================================================
# 유틸
# =========================================================

def normalize_spec(spec):
    """문자열 스펙과 dict 스펙을 (ticker, leverage_of)로 통일"""
    if isinstance(spec, dict):
        return spec["ticker"], spec.get("leverage_of")
    return spec, None


def _fetch_stock_raw(ticker):

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=2y&interval=1d"

    data = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    ).json()["chart"]["result"][0]

    prices = {
        datetime.fromtimestamp(t, timezone.utc).date(): c
        for t, c in zip(
            data["timestamp"],
            data["indicators"]["quote"][0]["close"]
        )
        if c is not None
    }

    today = max(prices)

    first = today.replace(day=1)
    last_month = first - timedelta(days=1)

    last_friday = today - timedelta(days=today.weekday() + 3)

    month_dates = [
        d for d in prices
        if d.year == last_month.year
        and d.month == last_month.month
    ]

    year_dates = [
        d for d in prices
        if d.year == today.year - 1
    ]

    return {
        "price": data["meta"]["regularMarketPrice"],
        "previous_day": prices.get(today - timedelta(days=1)),
        "previous_week": prices.get(last_friday),
        "previous_month": prices[max(month_dates)] if month_dates else None,
        "previous_year": prices[max(year_dates)] if year_dates else None,
    }


# 같은 티커가 여러 섹션(종목/트렌딩/AI 트렌드)에 중복 등장해도
# API 요청은 한 번만 나가도록 캐싱
_STOCK_CACHE = {}

def fetch_stock(ticker):

    if ticker in _STOCK_CACHE:
        return dict(_STOCK_CACHE[ticker])

    data = _fetch_stock_raw(ticker)
    _STOCK_CACHE[ticker] = data
    return dict(data)


_MARKET_CAP_CACHE = {}

def fetch_market_cap(ticker):
    """시가총액."""

    if ticker in _MARKET_CAP_CACHE:
        return _MARKET_CAP_CACHE[ticker]

    url = (
        f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}"
        f"?modules=price"
    )

    data = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    ).json()

    price_module = data["quoteSummary"]["result"][0]["price"]
    market_cap = price_module.get("marketCap", {}).get("raw")

    _MARKET_CAP_CACHE[ticker] = market_cap
    return market_cap


def fetch_indicator(ticker):

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=5d&interval=1d"

    data = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    ).json()["chart"]["result"][0]

    prices = [
        c
        for c in data["indicators"]["quote"][0]["close"]
        if c is not None
    ]

    return {"value": prices[-1] if prices else None}


def fetch_trending_symbols(region, count):
    """Yahoo Finance 비공식 트렌딩 엔드포인트 - 지금 많이 검색되는 티커 목록"""

    url = f"https://query1.finance.yahoo.com/v1/finance/trending/{region}"

    data = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    ).json()

    quotes = data["finance"]["result"][0]["quotes"]

    return [q["symbol"] for q in quotes[:count]]


def fetch_qqq_symbols():
    """Nasdaq-100 구성종목 자동 수집."""
    url = "https://api.nasdaq.com/api/quote/list-type/nasdaq100"
    r = requests.get(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
        },
        timeout=15,
    )
    rows = r.json()["data"]["data"]["rows"]
    return [x["symbol"] for x in rows if x.get("symbol")]


def build_qqq_top10():
    """QQQ 기준 상위 종목. 시총 데이터가 있으면 시총순, 실패하면 Nasdaq 구성 순서를 사용."""
    try:
        symbols = fetch_qqq_symbols()
    except Exception as e:
        print(f"[warn] QQQ 구성종목 수집 실패: {e}")
        return {}

    result = []
    # 전체 100개에 시총 API를 호출하지 않고, 현재 대형주 후보만 먼저 확인
    candidates = [
        "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "GOOG",
        "AVGO", "TSLA", "WMT", "COST", "NFLX", "AMD", "PLTR", "MU"
    ]
    candidates = [x for x in candidates if x in symbols]

    for symbol in candidates:
        try:
            cap = fetch_market_cap(symbol)
            result.append((symbol, cap))
        except Exception as e:
            print(f"[warn] QQQ 시총 수집 실패 {symbol}: {e}")

    result.sort(key=lambda x: x[1] or 0, reverse=True)
    return {
        symbol: {"ticker": symbol, "market_cap": cap, "rank": i + 1}
        for i, (symbol, cap) in enumerate(result[:QQQ_TOP_COUNT])
    }


def fetch_news(query, days=7):
    """Google News RSS 기반 최근 뉴스 건수."""
    url = (
        "https://news.google.com/rss/search?q="
        + quote_plus(f"{query} when:{days}d")
        + "&hl=en-US&gl=US&ceid=US:en"
    )
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    root = ET.fromstring(r.text)
    return root.findall("./channel/item")



# =========================================================
# Stock Data (대분류 -> 테마 -> 종목)
# =========================================================

stock_result = {}

for category, themes in STOCKS.items():

    stock_result[category] = {}

    for theme, tickers in themes.items():

        stock_result[category][theme] = {}

        for name, spec in tickers.items():

            ticker, leverage_of = normalize_spec(spec)

            try:
                data = fetch_stock(ticker)
                if leverage_of:
                    data["leverage_of"] = leverage_of
                stock_result[category][theme][name] = data

            except Exception as e:
                print(f"[warn] {name} 시세 수집 실패: {e}")


# =========================================================
# QQQ Top 10
# =========================================================

qqq_top10 = build_qqq_top10()

if qqq_top10:
    STOCKS["QQQ Top 10 (Market Cap)"] = {
        "QQQ Top 10 (Market Cap)": {
            symbol: symbol for symbol in qqq_top10
        }
    }

    stock_result["QQQ Top 10 (Market Cap)"] = {}
    stock_result["QQQ Top 10 (Market Cap)"]["QQQ Top 10 (Market Cap)"] = {}

    for symbol, info in qqq_top10.items():
        try:
            data = fetch_stock(symbol)
            data["market_cap"] = info["market_cap"]
            data["market_cap_rank"] = info["rank"]
            stock_result["QQQ Top 10 (Market Cap)"]["QQQ Top 10 (Market Cap)"][symbol] = data
        except Exception as e:
            print(f"[warn] QQQ Top10 {symbol} 수집 실패: {e}")


# =========================================================
# Trending Data (순위 유지를 위해 리스트로 저장)
# =========================================================

trending_result = []

try:
    symbols = fetch_trending_symbols(TRENDING_REGION, TRENDING_COUNT)

    for rank, symbol in enumerate(symbols, start=1):
        try:
            data = fetch_stock(symbol)
            data["rank"] = rank
            data["symbol"] = symbol
            trending_result.append(data)
        except Exception as e:
            print(f"[warn] trending {symbol} 수집 실패: {e}")

except Exception as e:
    print(f"[warn] 트렌딩 목록 수집 실패 (Yahoo 비공식 엔드포인트 변경 가능성): {e}")


# =========================================================
# AI Trends Data (키워드 -> 설명 + 관련 종목 시세/시총)
# =========================================================

ai_trends_result = {}

for keyword, info in AI_TRENDS.items():

    related_result = []

    for ticker in info["tickers"]:
        try:
            data = fetch_stock(ticker)
            data["symbol"] = ticker

            try:
                data["market_cap"] = fetch_market_cap(ticker)
            except Exception as e:
                data["market_cap"] = None
                print(f"[warn] {ticker} 시가총액 수집 실패: {e}")

            related_result.append(data)

        except Exception as e:
            print(f"[warn] AI 트렌드 관련종목 {ticker} 수집 실패: {e}")

    try:
        news_count = len(fetch_news(keyword, 7))
    except Exception as e:
        news_count = 0
        print(f"[warn] AI 트렌드 뉴스 수집 실패 ({keyword}): {e}")

    for item in related_result:
        if item["symbol"] in qqq_top10:
            item["market_cap_rank"] = qqq_top10[item["symbol"]]["rank"]

    ai_trends_result[keyword] = {
        "description": info["description"],
        "news_count": news_count,
        "tickers": related_result,
    }


# =========================================================
# Indicator Data (카테고리별로 수집)
# =========================================================

indicator_result = {}

for category, tickers in INDICATORS.items():

    indicator_result[category] = {}

    for name, ticker in tickers.items():
        try:
            indicator_result[category][name] = fetch_indicator(ticker)
        except Exception as e:
            print(f"[warn] {name} 지표 수집 실패: {e}")


# S&P 500 Forward Earnings Yield -> "Volatility & Valuation" 카테고리에 추가

try:
    url = "https://historyofmarket.com/api/sp500/forward-pe.json"

    forward_data = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    ).json()

    forward_pe = forward_data["current"]["forward"]
    forward_ey = 100 / forward_pe

    indicator_result.setdefault("Volatility & Valuation", {})
    indicator_result["Volatility & Valuation"]["S&P500 Forward Earnings Yield"] = {
        "value": round(forward_ey, 2)
    }

except Exception as e:
    print(f"[warn] S&P500 Forward Earnings Yield 수집 실패: {e}")


# =========================================================
# Macro Events (FOMC / BLS / PCE)
# =========================================================

events = []

KST = timezone(timedelta(hours=9))
now = datetime.now(KST)


# ---- FOMC ----

try:
    fed_url = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"

    fed_html = requests.get(
        fed_url,
        headers={"User-Agent": "Mozilla/5.0"}
    ).text

    fed_text = re.sub(r"<[^>]+>", " ", fed_html)
    fed_text = re.sub(r"\s+", " ", fed_text)

    fomc_dates = re.findall(
        r"(January|March|April|June|July|September|October|December)\s+(\d{1,2})-(\d{1,2})",
        fed_text
    )

    month_map = {
        "January": 1, "March": 3, "April": 4, "June": 6,
        "July": 7, "September": 9, "October": 10, "December": 12,
    }

    for month, day1, day2 in fomc_dates:

        meeting_date = datetime(
            2026, month_map[month], int(day2), 14, 0,
            tzinfo=timezone(timedelta(hours=-4))
        )

        meeting_kst = meeting_date.astimezone(KST)
        press_kst = meeting_kst + timedelta(minutes=30)

        if meeting_kst > now:
            events.append({"name": "FOMC", "date": meeting_kst.strftime("%m/%d %H:%M")})
            events.append({"name": "Fed Press", "date": press_kst.strftime("%m/%d %H:%M")})
            break

except Exception as e:
    print(f"[warn] FOMC 일정 수집 실패: {e}")


# ---- BLS - Jobs / CPI ----

try:
    bls_url = "https://www.bls.gov/schedule/news_release/bls.ics"

    bls_text = requests.get(
        bls_url,
        headers={"User-Agent": "Mozilla/5.0"}
    ).text

    bls_events = re.findall(
        r"DTSTART[^:]*:(\d{8}T\d{4}).*?"
        r"SUMMARY:(.*?)\r?\n",
        bls_text,
        re.S
    )

    for event_name, keyword in [
        ("Jobs", "Employment Situation"),
        ("CPI", "Consumer Price Index"),
    ]:

        for date_text, name in bls_events:

            if keyword not in name:
                continue

            dt = datetime.strptime(date_text, "%Y%m%dT%H%M").replace(
                tzinfo=timezone(timedelta(hours=-4))
            )

            kst = dt.astimezone(KST)

            if kst > now:
                events.append({"name": event_name, "date": kst.strftime("%m/%d %H:%M")})
                break

except Exception as e:
    print(f"[warn] BLS 일정 수집 실패: {e}")


# ---- PCE ----

try:
    bea_url = "https://www.bea.gov/news/schedule"

    bea_html = requests.get(
        bea_url,
        headers={"User-Agent": "Mozilla/5.0"}
    ).text

    bea_text = re.sub(r"<[^>]+>", " ", bea_html)
    bea_text = re.sub(r"\s+", " ", bea_text)

    pce_matches = re.findall(
        r"([A-Z][a-z]+)\s+(\d{1,2}).{0,300}?Personal Income and Outlays",
        bea_text,
        re.S
    )

    month_map2 = {
        "January": 1, "February": 2, "March": 3, "April": 4,
        "May": 5, "June": 6, "July": 7, "August": 8,
        "September": 9, "October": 10, "November": 11, "December": 12,
    }

    for month, day in pce_matches:

        if month not in month_map2:
            continue

        dt = datetime(
            2026, month_map2[month], int(day), 8, 30,
            tzinfo=timezone(timedelta(hours=-4))
        )

        kst = dt.astimezone(KST)

        if kst > now:
            events.append({"name": "PCE", "date": kst.strftime("%m/%d %H:%M")})
            break

except Exception as e:
    print(f"[warn] PCE 일정 수집 실패: {e}")


def event_datetime(e):
    return datetime.strptime(f"2026/{e['date']}", "%Y/%m/%d %H:%M")


events.sort(key=event_datetime)


# =========================================================
# AI Events (수동 관리 리스트 - 지난 날짜/ongoing 여부로 필터링)
# =========================================================

ai_events_result = []
today = date.today()

for e in AI_EVENTS:

    if e.get("ongoing"):
        ai_events_result.append(e)
        continue

    if e.get("date"):
        try:
            event_date = datetime.strptime(e["date"], "%Y-%m-%d").date()
            if event_date >= today:
                ai_events_result.append(e)
        except Exception as ex:
            print(f"[warn] AI 이벤트 날짜 파싱 실패 ({e.get('name')}): {ex}")


# =========================================================
# AI Events / News (자동 업데이트)
# 기존 수동 이벤트 + 최근 AI 주요 뉴스
# =========================================================

try:
    ai_news = fetch_news("AI artificial intelligence IPO data center semiconductor", 7)
    for item in ai_news[:6]:
        title = item.findtext("title") or ""
        pub = item.findtext("pubDate") or ""
        try:
            dt = datetime.strptime(pub[:25], "%a, %d %b %Y %H:%M:%S")
            date_label = dt.strftime("%m/%d")
        except Exception:
            date_label = ""

        ai_events_result.append({
            "name": title.split(" - ")[0][:90],
            "date": date_label,
            "note": "자동 수집 뉴스",
            "ongoing": False,
        })
except Exception as e:
    print(f"[warn] AI 뉴스 수집 실패: {e}")


# =========================================================
# Save JSON
# =========================================================

output = {
    "stocks": stock_result,
    "indicators": indicator_result,
    "trending": trending_result,
    "ai_trends": ai_trends_result,
    "events": events,
    "ai_events": ai_events_result,
}

with open("data.json", "w") as f:
    json.dump(output, f)

print(json.dumps(output, indent=2, ensure_ascii=False))
