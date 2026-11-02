#!/usr/bin/env python3
"""FUND_FETCH.py - 후보 기업 SEC XBRL: 누적/TTM 매출·영업이익·순이익·OCF·capex, 현금·부채 -> fund.json"""
import json, time, requests
from datetime import date, timedelta
UA={"User-Agent":"market-dashboard research ehwa160425@gmail.com","Accept-Encoding":"gzip, deflate"}
T="ORCL COIN RGTI QBTS NFLX UBER INTC SMCI CRCL IONQ CRWV HOOD GOOGL META AVGO MU ARM TSLA PLTR AMD MSTR NVDA BABA".split()
tk=requests.get("https://www.sec.gov/files/company_tickers.json",headers=UA,timeout=60).json()
cik={v["ticker"]:v["cik_str"] for v in tk.values()}
TAGS={"rev":["Revenues","RevenueFromContractWithCustomerExcludingAssessedTax","RevenueFromContractWithCustomerIncludingAssessedTax","SalesRevenueNet","RevenuesNetOfInterestExpense"],
"oi":["OperatingIncomeLoss"],"ni":["NetIncomeLoss"],"ocf":["NetCashProvidedByUsedInOperatingActivities"],
"capex":["PaymentsToAcquirePropertyPlantAndEquipment","PaymentsToAcquireProductiveAssets","PaymentsToAcquirePropertyPlantAndEquipmentAndIntangibleAssets"]}
INST={"cash":["CashAndCashEquivalentsAtCarryingValue","CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
"debt":["LongTermDebt","LongTermDebtNoncurrent","ConvertibleNotesPayable","LongTermNotesPayable","DebtLongtermAndShorttermCombinedAmount"],
"eq":["StockholdersEquity"]}
d=lambda s:date.fromisoformat(s)
def dur(f):return (d(f["end"])-d(f["start"])).days
def series(g,tags):
    for tg in tags:
        if tg in g:
            arr=[f for f in g[tg]["units"].get("USD",[]) if "start" in f and f.get("form") in("10-K","10-Q","10-K/A","10-Q/A")]
            if arr:return arr
    return []
def ttm(g,tags):
    arr=series(g,tags)
    fy=[f for f in arr if f["form"].startswith("10-K") and 350<=dur(f)<=380]
    if not fy:return None
    fe=max(f["end"] for f in fy);fyv={f["end"]:f["val"] for f in sorted(fy,key=lambda f:f["filed"])}
    fyval=fyv[fe]
    ytd=[f for f in arr if f["form"].startswith("10-Q") and 0<dur(f)<350 and d(f["start"])>=d(fe)-timedelta(days=3) and f["end"]>fe and abs((d(f["start"])-(d(fe)+timedelta(days=1))).days)<=5]
    if not ytd:return {"fy_end":fe,"fy":fyval,"ytd":None,"ttm":fyval}
    y=max(ytd,key=lambda f:(f["end"],f["filed"]))
    ps=d(y["start"])-timedelta(days=365);pe=d(y["end"])-timedelta(days=365)
    pr=[f for f in arr if f["form"].startswith("10-Q") and abs((d(f["start"])-ps).days)<=6 and abs((d(f["end"])-pe).days)<=6]
    if not pr:return {"fy_end":fe,"fy":fyval,"ytd":y["val"],"ytd_end":y["end"],"ytd_prior":None,"ttm":None}
    p=max(pr,key=lambda f:f["filed"])
    return {"fy_end":fe,"fy":fyval,"ytd":y["val"],"ytd_end":y["end"],"ytd_prior":p["val"],"ttm":fyval+y["val"]-p["val"]}
def inst(g,tags):
    for tg in tags:
        if tg in g:
            arr=[f for f in g[tg]["units"].get("USD",[]) if f.get("form") in("10-K","10-Q") and "start" not in f]
            if arr:
                m=max(arr,key=lambda f:(f["end"],f["filed"]));return {"v":m["val"],"end":m["end"],"tag":tg}
    return None
out={}
for t in T:
    try:
        j=requests.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik[t]):010d}.json",headers=UA,timeout=90).json()
        g=j["facts"].get("us-gaap",{})
        o={"name":j.get("entityName")}
        for k,tg in TAGS.items():o[k]=ttm(g,tg)
        for k,tg in INST.items():o[k]=inst(g,tg)
        out[t]=o
    except Exception as e:
        out[t]={"err":repr(e)[:150]}
    time.sleep(0.4)
json.dump(out,open("fund.json","w"))
