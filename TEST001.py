import requests, json, re, xml.etree.ElementTree as ET
from urllib.parse import quote_plus
from datetime import datetime, timezone, timedelta, date

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

    # QQQ(Nasdaq-100) 시총 상위 10개는 아래에서 자동 구성
}

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
# AI 트렌드 / 이벤트
# 키워드와 관련 종목 매핑은 고정하고, 뉴스 언급량/이벤트는 자동 수집
# =========================================================

AI_TRENDS = {
    "AI 데이터센터 / CapEx": {
        "query": '"AI data center" OR "AI infrastructure" OR "data center capex"',
        "description": "AI 데이터센터 및 하이퍼스케일러 투자",
        "tickers": ["NVDA", "MSFT", "AMZN", "GOOGL", "ORCL"],
    },
    "AI 전력 / 인프라": {
        "query": '"AI power" OR "data center power" OR "data center cooling"',
        "description": "AI 데이터센터 전력·냉각·전력설비",
        "tickers": ["GEV", "ETN", "VRT", "CEG", "VST"],
    },
    "AI 추론 / Inference": {
        "query": '"AI inference" OR "inference demand"',
        "description": "AI 서비스 추론 수요 확대",
        "tickers": ["NVDA", "AVGO", "MSFT", "AMZN", "GOOGL"],
    },
    "커스텀 AI 칩 / ASIC": {
        "query": '"custom AI chip" OR AI ASIC OR "custom silicon"',
        "description": "GPU 외 커스텀 AI 칩·ASIC",
        "tickers": ["AVGO", "NVDA", "AMD"],
    },
    "AI 네트워킹": {
        "query": '"AI networking" OR "AI network" OR "AI interconnect"',
        "description": "AI 서버간 고속 네트워크·인터커넥트",
        "tickers": ["AVGO", "ANET", "NVDA"],
    },
    "HBM / AI 메모리": {
        "query": 'HBM OR "AI memory" OR "high bandwidth memory"',
        "description": "AI용 HBM 및 메모리 수요",
        "tickers": ["MU", "NVDA"],
    },
    "엔터프라이즈 / 에이전틱 AI": {
        "query": '"enterprise AI" OR "AI agents" OR "agentic AI"',
        "description": "기업용 AI·AI Agent 도입",
        "tickers": ["MSFT", "AMZN", "GOOGL", "META", "PLTR"],
    },
    "AI 인프라 파이낸싱 / IPO": {
        "query": '"AI infrastructure" IPO OR "AI data center" IPO OR "AI financing"',
        "description": "AI 인프라 자금조달·IPO",
        "tickers": ["CRWV", "VRT", "GEV"],
    },
}

AI_EVENT_QUERY = '"AI" (IPO OR "initial public offering" OR listing OR acquisition)'

# Nasdaq-100 API 실패 시 사용할 최소 fallback
QQQ_FALLBACK = [
    "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "GOOG", "AVGO",
    "TSLA", "NFLX", "AMD", "COST", "ADBE", "QCOM", "INTC", "CSCO",
    "PEP", "TMUS", "AMGN", "INTU", "TXN", "AMAT", "ISRG", "BKNG",
    "HON", "LRCX", "MU", "ADI", "PANW", "GILD"
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


def fetch_market_cap(ticker):
    """대략적인 시가총액 (순위 계산은 무료 API로는 불가능해서 값만 제공)"""

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


def fetch_news(query, days=7):
    """Google News RSS에서 최근 기사 제목/발행일을 가져옴."""
    url = (
        "https://news.google.com/rss/search?q="
        + quote_plus(query)
        + f"+when:{days}d&hl=en-US&gl=US&ceid=US:en"
    )
    root = ET.fromstring(requests.get(
        url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15
    ).content)

    items = []
    for item in root.findall(".//item"):
        title = item.findtext("title") or ""
        pub = item.findtext("pubDate") or ""
        source = item.findtext("source") or ""
        try:
            dt = datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %Z")
        except Exception:
            dt = None
        items.append({"title": title, "date": dt, "source": source})
    return items


def fetch_qqq_symbols():
    """Nasdaq-100(=QQQ의 기초지수) 구성종목을 Nasdaq API에서 자동 수집."""
    try:
        url = "https://api.nasdaq.com/api/quote/list-type/nasdaq100"
        data = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json, text/plain, */*"
            },
            timeout=15
        ).json()
        rows = data["data"]["data"]["rows"]
        symbols = [r["symbol"] for r in rows if r.get("symbol")]
        return symbols or QQQ_FALLBACK
    except Exception as e:
        print(f"[warn] Nasdaq-100 구성종목 수집 실패: {e}")
        return QQQ_FALLBACK


def build_qqq_top10():
    """QQQ 구성종목 중 현재 시가총액 상위 10개."""
    caps = []

    for symbol in fetch_qqq_symbols():
        try:
            cap = fetch_market_cap(symbol)
            if cap:
                caps.append((symbol, cap))
        except Exception as e:
            print(f"[warn] QQQ 시총 수집 실패 {symbol}: {e}")

    caps.sort(key=lambda x: x[1], reverse=True)
    return [symbol for symbol, _ in caps[:10]]


def build_ai_trends():
    """최근 7일 뉴스 언급량을 기준으로 AI 트렌드를 자동 정렬."""
    result = {}

    for keyword, info in AI_TRENDS.items():
        try:
            news = fetch_news(info["query"], 7)
            result[keyword] = {
                "description": info["description"],
                "mention_count": len(news),
                "tickers": info["tickers"],
            }
        except Exception as e:
            print(f"[warn] AI 트렌드 뉴스 수집 실패 {keyword}: {e}")
            result[keyword] = {
                "description": info["description"],
                "mention_count": 0,
                "tickers": info["tickers"],
            }

    return dict(sorted(
        result.items(),
        key=lambda x: x[1]["mention_count"],
        reverse=True
    ))


def build_ai_events():
    """최근 30일 AI IPO/상장/M&A 관련 뉴스를 자동 수집."""
    events = []

    try:
        news = fetch_news(AI_EVENT_QUERY, 30)
        seen = set()

        for item in news:
            title = item["title"].replace(" - Google News", "").strip()
            key = re.sub(r"\W+", "", title.lower())

            if not title or key in seen:
                continue

            seen.add(key)

            events.append({
                "name": title,
                "date": item["date"].strftime("%Y-%m-%d") if item["date"] else "",
                "note": item["source"],
                "related": [],
            })

            if len(events) >= 8:
                break

    except Exception as e:
        print(f"[warn] AI 이벤트 뉴스 수집 실패: {e}")

    return events


def fetch_trending_symbols(region, count):
    """Yahoo Finance 비공식 트렌딩 엔드포인트 - 지금 많이 검색되는 티커 목록"""

    url = f"https://query1.finance.yahoo.com/v1/finance/trending/{region}"

    data = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    ).json()

    quotes = data["finance"]["result"][0]["quotes"]

    return [q["symbol"] for q in quotes[:count]]


# =========================================================
# Stock Data (대분류 -> 테마 -> 종목)
# =========================================================

# QQQ 기준 시총 상위 10개를 매 실행마다 자동 구성
try:
    qqq_top10 = build_qqq_top10()
    STOCKS["QQQ Top 10 (Market Cap)"] = {
        "QQQ Top 10 (Market Cap)": {symbol: symbol for symbol in qqq_top10}
    }
except Exception as e:
    print(f"[warn] QQQ Top 10 생성 실패: {e}")

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
# AI Trends Data (최근 7일 뉴스 언급량 + 관련 종목 시세/시총)
# =========================================================

ai_trends_raw = build_ai_trends()
ai_trends_result = {}

# QQQ 내 시총순위 계산
try:
    qqq_caps = []

    for symbol in fetch_qqq_symbols():
        try:
            cap = fetch_market_cap(symbol)
            if cap:
                qqq_caps.append((symbol, cap))
        except Exception:
            pass

    qqq_caps.sort(key=lambda x: x[1], reverse=True)
    qqq_rank = {symbol: i + 1 for i, (symbol, _) in enumerate(qqq_caps)}

except Exception as e:
    print(f"[warn] QQQ 시총순위 생성 실패: {e}")
    qqq_rank = {}

for keyword, info in ai_trends_raw.items():

    related_result = []

    for ticker in info["tickers"]:
        try:
            data = fetch_stock(ticker)
            data["symbol"] = ticker
            data["market_cap"] = fetch_market_cap(ticker)
            data["market_cap_rank"] = qqq_rank.get(ticker)
            related_result.append(data)

        except Exception as e:
            print(f"[warn] AI 트렌드 관련종목 {ticker} 수집 실패: {e}")

    ai_trends_result[keyword] = {
        "description": info["description"],
        "mention_count": info["mention_count"],
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
# AI Events (최근 30일 뉴스 자동 수집)
# =========================================================

ai_events_result = build_ai_events()


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
