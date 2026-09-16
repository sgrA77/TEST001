import requests, json, re
from datetime import datetime, timezone, timedelta

stocks = {
    "SPY": "SPY",
    "SPXL": "SPXL",
    "QLD": "QLD",
    "NVDA": "NVDA",
    "NVDL": "NVDL",
    "PLTR": "PLTR",
    "KORU": "KORU",
    "AMD": "AMD",
    "MU": "MU",
    "MUU": "MUU",
    "SNDK": "SNDK",
    "SNXX": "SNXX",
    "AMZN": "AMZN",
    "GOOG": "GOOG",
    "ORCL": "ORCL",

    # 한국 주식
    "Samsung": "005930.KS",
    "SKHynix": "000660.KS",

    # 기타 자산
    "Gold": "GC=F",
    "Crude Oil": "CL=F",

    # 암호 화폐
    "Bitcoin": "BTC-USD"
}

# =========================
# Macro / Market Indicators
# =========================

indicators = {
    "US 10Y Yield": "^TNX",
    "US 3M Yield": "^IRX",
    "USD/JPY": "JPY=X",
    "VIX": "^VIX"
}

result = {}
indicator_result = {}

# =========================
# 기존 주식 / 자산 데이터
# =========================

for name, stock in stocks.items():

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{stock}?range=2y&interval=1d"

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
        if d.year == last_month.year and d.month == last_month.month
    ]

    year_dates = [
        d for d in prices
        if d.year == today.year - 1
    ]

    result[name] = {
        "price": data["meta"]["regularMarketPrice"],
        "previous_day": prices.get(today - timedelta(days=1)),
        "previous_week": prices.get(last_friday),
        "previous_month": prices[max(month_dates)] if month_dates else None,
        "previous_year": prices[max(year_dates)] if year_dates else None
    }

# =========================
# Forward Earnings Yield
# =========================

url = "https://historyofmarket.com/api/sp500/forward-pe.json"

forward_data = requests.get(
    url,
    headers={"User-Agent": "Mozilla/5.0"}
).json()

forward_pe = forward_data["current"]["forward"]

forward_ey = 100 / forward_pe

indicator_result["S&P500 Forward Earnings Yield"] = {
    "value": round(forward_ey, 2)
}

# =========================
# 지표 데이터
# =========================

for name, ticker in indicators.items():

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=5d&interval=1d"

    data = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    ).json()["chart"]["result"][0]

    indicator_prices = [
        c
        for c in data["indicators"]["quote"][0]["close"]
        if c is not None
    ]

    indicator_result[name] = {
        "value": indicator_prices[-1] if indicator_prices else None
    }

# =========================
# FOMC / Fed Press
# =========================

url = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"

fed_html = requests.get(
    url,
    headers={"User-Agent": "Mozilla/5.0"}
).text

# 2026년 FOMC 일정에서 날짜 범위 추출
matches = re.findall(
    r'(January|March|April|June|July|September|October|December)\s+(\d{1,2})-(\d{1,2})',
    fed_html
)

month_numbers = {
    "January": 1,
    "March": 3,
    "April": 4,
    "June": 6,
    "July": 7,
    "September": 9,
    "October": 10,
    "December": 12
}

events = []

today = datetime.now(timezone.utc).date()

for month, start_day, end_day in matches:

    date = datetime(
        2026,
        month_numbers[month],
        int(end_day)
    ).date()

    # 가장 가까운 미래 FOMC 하나만 사용
    if date >= today:

        events.append({
            "name": "FOMC",
            "date": date.isoformat()
        })

        events.append({
            "name": "Fed Press",
            "date": date.isoformat()
        })

        break

# =========================
# JSON 저장
# =========================

output = {
    "stocks": result,
    "indicators": indicator_result,
    "events": events
}

with open("data.json", "w") as f:
    json.dump(output, f)

print(output)
