import requests, json
from datetime import datetime, timezone, timedelta
import re

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
# Fed FOMC 일정
# =========================

fed_url = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"

fed_html = requests.get(
    fed_url,
    headers={"User-Agent": "Mozilla/5.0"}
).text


# HTML 태그 제거
fed_text = re.sub(r"<[^>]+>", " ", fed_html)

# 공백 정리
fed_text = re.sub(r"\s+", " ", fed_text)


# 2026 FOMC 일정 찾기
fomc_dates = re.findall(
    r"(January|March|April|June|July|September|October|December)\s+(\d{1,2})-(\d{1,2})",
    fed_text
)


month_map = {
    "January": 1,
    "March": 3,
    "April": 4,
    "June": 6,
    "July": 7,
    "September": 9,
    "October": 10,
    "December": 12
}


today = datetime.now().date()

next_fomc = None


for month, day1, day2 in fomc_dates:

    date = datetime(
        2026,
        month_map[month],
        int(day2)
    ).date()

    if date > today:
        next_fomc = date
        break


# =========================
# 이벤트
# =========================

events = []

if next_fomc:

    events.append({
        "name": "FOMC",
        "date": f"{next_fomc.month:02d}/{next_fomc.day:02d} 03:00"
    })

    events.append({
        "name": "Fed Press",
        "date": f"{next_fomc.month:02d}/{next_fomc.day:02d} 03:30"
    })


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
