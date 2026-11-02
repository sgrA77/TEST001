#!/usr/bin/env python3
"""ORCL_FETCH.py - Oracle SEC companyfacts(비차원 팩트) -> orcl.json"""
import json, re, requests
UA={"User-Agent":"market-dashboard research ehwa160425@gmail.com","Accept-Encoding":"gzip, deflate"}
j=requests.get("https://data.sec.gov/api/xbrl/companyfacts/CIK0001341439.json",headers=UA,timeout=90).json()
pat=re.compile(r"Revenue|Cash|Debt|Notes|Interest|PaymentsToAcquire|Capital|Lease|Equity|Assets$|Liabilities$|NetIncome|OperatingIncome|Repurchase|Dividend|Depreciation|Purchase|Borrow|Issuance|RemainingPerformance",re.I)
out={}
for tax in ("us-gaap","dei"):
    for tag,v in j["facts"].get(tax,{}).items():
        if tax=="us-gaap" and not pat.search(tag): continue
        rows=[]
        for u,arr in v["units"].items():
            for f in arr:
                if f.get("form") in ("10-K","10-Q","10-K/A","10-Q/A") and f["end"]>="2020-05-01":
                    rows.append([u,f.get("start"),f["end"],f["val"],f["form"],f["filed"],f.get("fp"),f.get("fy")])
        if rows: out[tax+":"+tag]=rows
json.dump(out,open("orcl.json","w"))
print(len(out))
