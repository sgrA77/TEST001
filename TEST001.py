import requests, json, re
from datetime import datetime, timezone, timedelta

# =========================================================
# 종목/지표 설정
#
# 구조: 대분류(category) -> 테마(theme) -> 표시이름 -> 스펙
# 스펙은 두 가지 형태 가능:
#   "SPY"                                   (일반 종목)
#   {"ticker": "SPXL", "leverage_of": "SPY"} (레버리지 종목 - 원종목 표기)
#
# 항목 추가/삭제는 아래 딕셔너리 안에서만 하면 됩니다.
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
TRENDING_REGION = "US"   # US, GB, DE, FR, IN, BR 등
TRENDING_COUNT = 10      # 사이드바에 보여줄 개수 - 필요하면 이 숫자만 바꾸면 됨


# =========================================================
# 유틸
# =========================================================

def normalize_spec(spec):
    """문자열 스펙과 dict 스펙을 (ticker, leverage_of)로 통일"""
    if isinstance(spec, dict):
        return spec["ticker"], spec.get("leverage_of")
    return spec, None


def fetch_stock(ticker):

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
# Events
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


# ---- Sort Events ----

def event_datetime(e):
    return datetime.strptime(f"2026/{e['date']}", "%Y/%m/%d %H:%M")


events.sort(key=event_datetime)


# =========================================================
# Save JSON
# =========================================================

output = {
    "stocks": stock_result,
    "indicators": indicator_result,
    "trending": trending_result,
    "events": events,
}

with open("data.json", "w") as f:
    json.dump(output, f)

print(json.dumps(output, indent=2, ensure_ascii=False))
