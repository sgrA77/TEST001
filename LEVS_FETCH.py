#!/usr/bin/env python3
"""LEVS_FETCH.py - 단일종목/지수 레버리지 ETF와 기초자산 일봉(+분할) -> levs.json"""
import json, time, requests
UA={"User-Agent":"Mozilla/5.0"}
T="""NVDL NVDU NVDX TSLL TSLT TSLR CONL MSTU MSTX BITX AAPU MSFU AMZU GGLL FBL METU AMDL AVL MUU SMCX SMCL PTIR PLTU PLTG ARMG QBTX RGTX IONX HOOX HOOG CRWU NFLU UBRL BABX INTW INTL LINT CRCL CRCG ORCX ORCU
KORU SOXL TQQQ TECL FNGU YINN LABU BULZ NAIL DPST
INTC NVDA TSLA COIN MSTR AAPL MSFT AMZN GOOGL META AMD AVGO MU SMCI PLTR ARM QBTS RGTI IONQ HOOD CRWD NFLX UBER BABA ORCL CRCL EWY ^SOX ^NDX FXI XBI BTC-USD""".split()
out={}
def get(q):
    for host in ("query1","query2"):
        for k in range(2):
            try:
                r=requests.get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{q}?period1=0&period2=1900000000&interval=1d&events=split",headers=UA,timeout=60)
                j=r.json()["chart"]["result"][0];ts=j["timestamp"];c=j["indicators"]["quote"][0]["close"]
                sp=[[v["date"],v["numerator"],v["denominator"]] for v in j.get("events",{}).get("splits",{}).values()]
                return {"rows":[[t,x] for t,x in zip(ts,c) if x is not None],"splits":sp,"name":j["meta"].get("longName") or j["meta"].get("shortName")}
            except Exception as e:
                err=repr(e)[:120];time.sleep(1.5)
    return {"err":err}
for q in dict.fromkeys(T):
    out[q]=get(q);time.sleep(0.3)
json.dump(out,open("levs.json","w"))
print({k:(len(v["rows"]) if "rows" in v else "ERR") for k,v in out.items()})
