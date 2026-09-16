import requests, json, re
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo


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


indicators = {
    "US 10Y Yield": "^TNX",
    "US 3M Yield": "^IRX",
    "USD/JPY": "JPY=X",
    "VIX": "^VIX"
}


result = {}
indicator_result = {}


# =========================
# 주식 / 자산
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

indicator_result["S&P500 Forward Earnings Yield"] = {
    "value": round(100 / forward_pe, 2)
}


# =========================
# 지표
# =========================

for name, ticker in indicators.items():

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=5d&interval=1d"

    data = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    ).json()["chart"]["result"][0]

    prices = [
        c for c in data["indicators"]["quote"][0]["close"]
        if c is not None
    ]

    indicator_result[name] = {
        "value": prices[-1] if prices else None
    }


# =========================
# 이벤트
# =========================

today = datetime.now(ZoneInfo("Asia/Seoul"))
events = []


# 미국시간 → 한국시간
def kst_date(utc_time):
    return utc_time.astimezone(
        ZoneInfo("Asia/Seoul")
    ).strftime("%m/%d %H:%M")


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

    us_date = datetime(
        2026,
        month_map[month],
        int(day2),
        14,
        0,
        tzinfo=ZoneInfo("America/New_York")
    )

    if us_date.astimezone(ZoneInfo("Asia/Seoul")) >= today:

        events += [
            {
                "name": "FOMC",
                "date": kst_date(us_date)
            },
            {
                "name": "Fed Press",
                "date": kst_date(
                    us_date + timedelta(minutes=30)
                )
            }
        ]

        break


# =========================
# BLS 일정
# CPI / US Jobs
# =========================

def bls_date(url, keyword):

    html = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    ).text

    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)

    pattern = (
        r"([A-Z][a-z]+)\s+2026\s+"
        r"([A-Z][a-z]{2})\.?\s+(\d{1,2}),\s+2026\s+"
        r"08:30 AM"
    )

    dates = []

    for ref_month, month, day in re.findall(pattern, text):

        if keyword.lower() in text[
            max(0, text.find(f"{month}. {day}, 2026") - 300):
            text.find(f"{month}. {day}, 2026") + 300
        ].lower():

            try:
                dates.append(
                    datetime(
                        2026,
                        datetime.strptime(month, "%b").month,
                        int(day),
                        8,
                        30,
                        tzinfo=ZoneInfo("America/New_York")
                    )
                )
            except:
                pass

    dates = [
        d for d in dates
        if d.astimezone(ZoneInfo("Asia/Seoul")) > today
    ]

    return min(dates) if dates else None


cpi = bls_date(
    "https://www.bls.gov/schedule/news_release/cpi.htm",
    "Consumer Price Index"
)

jobs = bls_date(
    "https://www.bls.gov/schedule/news_release/empsit.htm",
    "Employment Situation"
)


if cpi:
    events.append({
        "name": "US CPI",
        "date": kst_date(cpi)
    })


if jobs:
    events.append({
        "name": "US Jobs",
        "date": kst_date(jobs)
    })


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

pce_dates = re.findall(
    r"([A-Z][a-z]+)\s+(\d{1,2})\s+8:30 AM.*?"
    r"Personal Income and Outlays",
    bea_text
)

pce_list = []

for month, day in pce_dates:

    try:
        d = datetime(
            2026,
            datetime.strptime(month, "%B").month,
            int(day),
            8,
            30,
            tzinfo=ZoneInfo("America/New_York")
        )

        if d.astimezone(ZoneInfo("Asia/Seoul")) > today:
            pce_list.append(d)

    except:
        pass


if pce_list:

    pce = min(pce_list)

    events.append({
        "name": "PCE",
        "date": kst_date(pce)
    })


# =========================
# 날짜순 정렬
# =========================

events.sort(
    key=lambda x: datetime.strptime(
        x["date"], "%m/%d %H:%M"
    )
)


# =========================
# JSON
# =========================

output = {
    "stocks": result,
    "indicators": indicator_result,
    "events": events
}


with open("data.json", "w") as f:
    json.dump(output, f)


print(output)
