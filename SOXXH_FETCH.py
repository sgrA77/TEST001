#!/usr/bin/env python3
"""SMHH_FETCH.py - SOXX N-PORT 보유종목 -> soxxh.json"""
import json, re, time, requests
import xml.etree.ElementTree as ET
UA={"User-Agent":"market-dashboard research ehwa160425@gmail.com","Accept-Encoding":"gzip, deflate"}
out={"log":[],"funds":{}}
def get(u,**k):
    for i in range(3):
        try:
            r=requests.get(u,headers=UA,timeout=60,**k)
            if r.status_code==200:return r
            out["log"].append(f"{u} -> {r.status_code}")
        except Exception as e: out["log"].append(f"{u} err {e!r}")
        time.sleep(2)
    return None
mf=get("https://www.sec.gov/files/company_tickers_mf.json").json()
fields=mf["fields"];rows=mf["data"]
sel=[dict(zip(fields,r)) for r in rows if r[fields.index("symbol")] in ("SOXX",)]
out["sel"]=sel
for s in sel:
    sid=s["seriesId"];cik=s["cik"];res=[]
    feed=get(f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={sid}&type=NPORT-P&dateb=&owner=include&count=100&output=atom")
    if not feed: out["funds"][s["symbol"]]={"err":"feed"};continue
    txt=feed.text
    out["feed_len"]=len(txt)
    accs=re.findall(r"<accession-number>([\d-]+)</accession-number>",txt)
    out["n_acc"]=len(accs)
    for a in accs:
        base=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{a.replace('-','')}/primary_doc.xml"
        r=get(base)
        time.sleep(0.25)
        if not r: continue
        try:
            root=ET.fromstring(r.content)
            ns=lambda t:t.split('}')[-1]
            per=None;pos=[]
            for el in root.iter():
                n=ns(el.tag)
                if n=="repPdDate" and per is None: per=el.text
            if per is None or int(per[5:7]) not in (3,6,9,12): continue
            for inv in root.iter():
                if ns(inv.tag)=="invstOrSec":
                    d={ns(c.tag):(c.text or "").strip() for c in inv if len(list(c))==0}
                    pos.append([d.get("name"),d.get("title"),d.get("pctVal"),d.get("valUSD"),d.get("balance")])
            res.append({"acc":a,"per":per,"pos":pos})
        except Exception as e:
            out["log"].append(f"parse {a} {e!r}")
    out["funds"][s["symbol"]]={"series":sid,"cik":cik,"filings":res}
json.dump(out,open("soxxh.json","w"))
