import requests, json, re
from datetime import datetime, timezone, timedelta

# =========================
# Stocks
# =========================

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

    "Samsung": "005930.KS",
    "SKHynix": "000660.KS",

    "Gold": "GC=F",
    "Crude Oil": "CL=F",
    "Bitcoin": "BTC-USD"
}


# =========================
# Indicators
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
# Stock Data
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
        if d.year == last_month.year
        and d.month == last_month.month
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
# S&P 500 Forward Earnings Yield
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
# Yahoo Indicators
# =========================

for name, ticker in indicators.items():

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

    indicator_result[name] = {
        "value": prices[-1] if prices else None
    }


# =========================
# Events
# =========================

events = []

KST = timezone(timedelta(hours=9))
now = datetime.now(KST)


# =========================
# FOMC
# =========================

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
    "January": 1,
    "March": 3,
    "April": 4,
    "June": 6,
    "July": 7,
    "September": 9,
    "October": 10,
    "December": 12
}

for month, day1, day2 in fomc_dates:

    # 2026 일정만 사용
    meeting_date = datetime(
        2026,
        month_map[month],
        int(day2),
        14,
        0,
        tzinfo=timezone(timedelta(hours=-4))
    )

    meeting_kst = meeting_date.astimezone(KST)

    press_kst = meeting_kst + timedelta(minutes=30)

    if meeting_kst > now:

        events.append({
            "name": "FOMC",
            "date": meeting_kst.strftime("%m/%d %H:%M")
        })

        events.append({
            "name": "Fed Press",
            "date": press_kst.strftime("%m/%d %H:%M")
        })

        break


# =========================
# BLS - Jobs / CPI
# =========================

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
    ("CPI", "Consumer Price Index")
]:

    for date_text, name in bls_events:

        if keyword not in name:
            continue

        # BLS 발표시간 = 미국 동부시간 08:30
        dt = datetime.strptime(
            date_text,
            "%Y%m%dT%H%M"
        ).replace(
            tzinfo=timezone(timedelta(hours=-4))
        )

        kst = dt.astimezone(KST)

        if kst > now:

            events.append({
                "name": event_name,
                "date": kst.strftime("%m/%d %H:%M")
            })

            break


# =========================
# PCE
# =========================

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
    "January": 1,
    "February": 2,
    "March": 3,
    "April": 4,
    "May": 5,
    "June": 6,
    "July": 7,
    "August": 8,
    "September": 9,
    "October": 10,
    "November": 11,
    "December": 12
}

for month, day in pce_matches:

    if month not in month_map2:
        continue

    dt = datetime(
        2026,
        month_map2[month],
        int(day),
        8,
        30,
        tzinfo=timezone(timedelta(hours=-4))
    )

    kst = dt.astimezone(KST)

    if kst > now:

        events.append({
            "name": "PCE",
            "date": kst.strftime("%m/%d %H:%M")
        })

        break


# =========================
# Sort Events
# =========================

def event_datetime(e):

    return datetime.strptime(
        f"2026/{e['date']}",
        "%Y/%m/%d %H:%M"
    )


events.sort(key=event_datetime)


# =========================
# Save JSON
# =========================

output = {
    "stocks": result,
    "indicators": indicator_result,
    "events": events
}

with open("data.json", "w") as f:
    json.dump(output, f)

print(output)
