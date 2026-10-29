#!/usr/bin/env python3
"""BT_FETCH.py - SEC companyfacts에서 매출(기간별) 수집 -> bt.json"""
import json, time, requests
UA={"User-Agent":"market-dashboard research ehwa160425@gmail.com","Accept-Encoding":"gzip, deflate"}
T="NVDA AAPL MSFT GOOGL AMZN AVGO TSLA META MU AMD INTC PLTR CSCO ORCL LRCX AMAT DELL PANW TXN CRWD".split()
TAGS=["Revenues","RevenueFromContractWithCustomerExcludingAssessedTax","RevenueFromContractWithCustomerIncludingAssessedTax","SalesRevenueNet","SalesRevenueGoodsNet"]
tk=requests.get("https://www.sec.gov/files/company_tickers.json",headers=UA,timeout=60).json()
m={v["ticker"]:(v["cik_str"],v["title"]) for v in tk.values()}
out={}
for t in T:
    try:
        cik,name=m[t]
        j=requests.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json",headers=UA,timeout=90).json()
        g=j["facts"].get("us-gaap",{})
        per={}
        used=[]
        for tag in TAGS:
            if tag not in g: continue
            used.append(tag)
            for f in g[tag]["units"].get("USD",[]):
                if "start" not in f or f.get("form") not in ("10-K","10-Q","10-K/A","10-Q/A"): continue
                k=(f["start"],f["end"])
                # prefer the later-filed value; between tags keep the first tag unless missing
                if k not in per or (per[k][2]<f["filed"] and per[k][3]==tag) :
                    per[k]=[f["start"],f["end"],f["filed"],tag,f["val"]]
                elif k not in per: per[k]=[f["start"],f["end"],f["filed"],tag,f["val"]]
        out[t]={"name":name,"cik":cik,"tags":used,"p":[[a,b,c,d,e] for (a,b),(a,b,c,d,e) in [(k,(v[0],v[1],v[2],v[3],v[4])) for k,v in per.items()] if b>="2019-06-01"]}
    except Exception as e:
        out[t]={"err":repr(e)}
    time.sleep(0.4)
json.dump(out,open("bt.json","w"))
