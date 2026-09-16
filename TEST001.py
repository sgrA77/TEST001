import requests, json
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
# JSON 저장
# =========================

output = {
    "stocks": result,
    "indicators": indicator_result
}

with open("data.json", "w") as f:
    json.dump(output, f)

print(output)
