import requests
import json

url = "https://query1.finance.yahoo.com/v8/finance/chart/SPY"

r = requests.get(
    url,
    headers={"User-Agent": "Mozilla/5.0"}
)

data = r.json()

price = data["chart"]["result"][0]["meta"]["regularMarketPrice"]

result = {
    "SPY": price
}

with open("data.json", "w") as f:
    json.dump(result, f)

print("SPY:", price)

