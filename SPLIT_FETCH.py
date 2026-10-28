#!/usr/bin/env python3
import json, requests
UA={"User-Agent":"Mozilla/5.0"}
out={}
for q in ["SPY","VOO","QQQ","SMH","SOXX"]:
    for host in ("query1","query2"):
        try:
            r=requests.get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{q}?period1=0&period2=1900000000&interval=1d&events=split",headers=UA,timeout=60)
            j=r.json()["chart"]["result"][0]
            ts=j["timestamp"];c=j["indicators"]["quote"][0]["close"]
            sp=[{"t":int(v["date"]),"n":v["numerator"],"d":v["denominator"]} for v in j.get("events",{}).get("splits",{}).values()]
            sp.sort(key=lambda x:x["t"])
            rows=[(t,x) for t,x in zip(ts,c) if x is not None]
            out[q]={"first":rows[0],"last":rows[-1],"splits":sp,"rows":[r for r in rows if any(abs(r[0]-s["t"])<8*86400 for s in sp)],"meta":j["meta"].get("firstTradeDate")}
            break
        except Exception as e:
            out[q]={"err":str(e)}
json.dump(out,open("splits.json","w"))
