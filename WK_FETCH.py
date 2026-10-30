#!/usr/bin/env python3
import json, requests
UA={"User-Agent":"Mozilla/5.0"}
out={}
for q in ["SPY","QQQ","SMH","SOXX","GLD"]:
    for host in ("query1","query2"):
        try:
            r=requests.get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{q}?period1=0&period2=1900000000&interval=1d&events=split",headers=UA,timeout=60)
            j=r.json()["chart"]["result"][0];ts=j["timestamp"];qt=j["indicators"]["quote"][0]
            rows=[[t,qt["open"][i],qt["high"][i],qt["low"][i],qt["close"][i]] for i,t in enumerate(ts) if qt["close"][i] is not None and qt["high"][i] is not None and qt["low"][i] is not None]
            out[q]={"rows":rows};break
        except Exception as e:
            out[q]={"err":repr(e)}
json.dump(out,open("wk.json","w"))
