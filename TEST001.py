import requests, json
from datetime import datetime, timezone, timedelta

stocks = ["SPY", "SPXL", "QLD", "NVDA", "NVDL", "PLTR", "KORU", "AMD", "MU", "MUU", "SNDK", "SNXX", "AMZN", "GOOG", "ORCL"]
result = {}

for stock in stocks:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{stock}?range=2y&interval=1d"
    data = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}).json()["chart"]["result"][0]

    prices = {
        datetime.fromtimestamp(t, timezone.utc).date(): c
        for t, c in zip(data["timestamp"], data["indicators"]["quote"][0]["close"])
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

    result[stock] = {
        "price": data["meta"]["regularMarketPrice"],
        "previous_day": prices.get(today - timedelta(days=1)),
        "previous_week": prices.get(last_friday),
        "previous_month": prices[max(month_dates)] if month_dates else None,
        "previous_year": prices[max(year_dates)] if year_dates else None
    }

with open("data.json", "w") as f:
    json.dump(result, f)

print(result)
