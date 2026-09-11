import requests
import json
from datetime import datetime, timezone, timedelta

url = "https://query1.finance.yahoo.com/v8/finance/chart/SPY?range=2y&interval=1d"

data = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}).json()["chart"]["result"][0]

prices = {
    datetime.fromtimestamp(t, timezone.utc).date(): c
    for t, c in zip(data["timestamp"], data["indicators"]["quote"][0]["close"])
    if c is not None
}

today = max(prices)
current = data["meta"]["regularMarketPrice"]

# 전일
previous_day = prices.get(today - timedelta(days=1))

# 전주: 지난주 금요일
last_friday = today - timedelta(days=today.weekday() + 3)
previous_week = prices.get(last_friday)

# 전월: 지난달 마지막 거래일
first_day = today.replace(day=1)
last_month = first_day - timedelta(days=1)
previous_month = prices[max(d for d in prices if d.year == last_month.year and d.month == last_month.month)]

# 전년: 작년 12/31 또는 그 직전 거래일
previous_year = prices[max(d for d in prices if d.year == today.year - 1)]

result = {
    "SPY": {
        "price": current,
        "previous_day": previous_day,
        "previous_week": previous_week,
        "previous_month": previous_month,
        "previous_year": previous_year
    }
}

with open("data.json", "w") as f:
    json.dump(result, f)

print(result)
