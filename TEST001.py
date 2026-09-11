import truststore
truststore.inject_into_ssl()

import requests

url = "https://query1.finance.yahoo.com/v8/finance/chart/SPY"

r = requests.get(
    url,
    headers={"User-Agent": "Mozilla/5.0"}
)

print("Status:", r.status_code)
print(r.text[:300])