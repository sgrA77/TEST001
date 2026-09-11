import requests, json
from datetime import datetime, timezone, timedelta

stocks = ["SPY", "SPXL", "QLD", "NVD", "AAPL", "GOOG"]
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

    result[stock] = {
        "price": data["meta"]["regularMarketPrice"],
        "previous_day": prices.get(today - timedelta(days=1)),
        "previous_week": prices.get(last_friday),
        "previous_month": prices[max(d for d in prices if d.year == last_month.year and d.month == last_month.month)],
        "previous_year": prices[max(d for d in prices if d.year == today.year - 1)]
    }

with open("data.json", "w") as f:
    json.dump(result, f)

print(result)
