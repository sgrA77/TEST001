#!/usr/bin/env python3
"""LEVW_UPDATE.py - 레버리지 저점 후보 모니터링 자동 갱신
 - Yahoo 일봉(2y)으로 단일종목 2x ETF 상태 계산(분할 복원) + SEC XBRL TTM 펀더멘털
 - levwatch/levwatch-candidates.json(템플릿)의 자동 섹션만 교체 -> out/ (levw-data 브랜치로 게시)
"""
import json, os, time, bisect, requests, datetime as dt
from datetime import date, timedelta
UA={"User-Agent":"Mozilla/5.0"}
SEC={"User-Agent":"market-dashboard research ehwa160425@gmail.com","Accept-Encoding":"gzip, deflate"}
M={'NVDL':'NVDA','NVDU':'NVDA','NVDX':'NVDA','TSLL':'TSLA','TSLT':'TSLA','TSLR':'TSLA','CONL':'COIN','MSTU':'MSTR','MSTX':'MSTR','AAPU':'AAPL','MSFU':'MSFT','AMZU':'AMZN','GGLL':'GOOGL','FBL':'META','METU':'META','AMDL':'AMD','AVL':'AVGO','MUU':'MU','SMCX':'SMCI','SMCL':'SMCI','PTIR':'PLTR','PLTU':'PLTR','PLTG':'PLTR','ARMG':'ARM','QBTX':'QBTS','RGTX':'RGTI','IONX':'IONQ','HOOX':'HOOD','HOOG':'HOOD','CRWU':'CRWV','NFLU':'NFLX','UBRL':'UBER','BABX':'BABA','INTW':'INTC','LINT':'INTC','CRCG':'CRCL','ORCX':'ORCL','ORCU':'ORCL'}
KR={'ORCL':'오라클','NFLX':'넷플릭스','UBER':'우버','COIN':'코인베이스','CRWV':'코어위브','INTC':'인텔','SMCI':'SMCI','CRCL':'서클','HOOD':'로빈후드','AVGO':'브로드컴','GOOGL':'알파벳','RGTI':'리게티','QBTS':'디웨이브','IONQ':'아이온큐','NVDA':'엔비디아','TSLA':'테슬라','AAPL':'애플','MSFT':'MS','AMZN':'아마존','META':'메타','AMD':'AMD','MU':'마이크론','PLTR':'팔란티어','ARM':'ARM','BABA':'알리바바','MSTR':'MSTR'}
MANUAL=['ORCU','NFLU','UBRL','CONL','CRWU','INTW','SMCX','CRCG','HOOG','AVL','GGLL','RGTX','QBTX','IONX']
FUND_T="ORCL COIN RGTI QBTS NFLX UBER INTC SMCI CRCL IONQ CRWV HOOD GOOGL META AVGO MU TSLA PLTR AMD MSTR NVDA AAPL MSFT AMZN".split()
PRICE_MAX=12.0; DD_MAX=-0.75; NEAR_MAX=0.20

def yget(q):
    for host in ("query1","query2"):
        for _ in range(2):
            try:
                r=requests.get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{q}?range=2y&interval=1d&events=split",headers=UA,timeout=40)
                j=r.json()["chart"]["result"][0]
                rows=[(t,c) for t,c in zip(j["timestamp"],j["indicators"]["quote"][0]["close"]) if c is not None]
                sp=[(v["date"],v["numerator"],v["denominator"]) for v in j.get("events",{}).get("splits",{}).values()]
                return rows,sp
            except Exception: time.sleep(1.5)
    return None,None
def stats(rows,sp):
    t=[r[0] for r in rows];c=[r[1] for r in rows];last=t[-1];n=c[-1]
    i52=bisect.bisect_left(t,last-365*86400);w=c[i52:]
    def ret(days):
        i=bisect.bisect_left(t,last-days*86400);return n/c[i]-1
    # 당시 거래가 = 보정가 x 이후 분할(현재가는 곱할 분할 없음)
    return dict(price=n,dd=n/max(w)-1,fl=n/min(w)-1,r1=ret(30),r3=ret(91),asof=dt.date.fromtimestamp(last).isoformat(),n52=len(w))

# ---- SEC TTM
def d(s):return date.fromisoformat(s)
def dur(f):return (d(f["end"])-d(f["start"])).days
def ttm1(arr):
    fy=[f for f in arr if f["form"].startswith("10-K") and 350<=dur(f)<=380]
    if not fy:return None
    fe=max(f["end"] for f in fy);fyv={f["end"]:f["val"] for f in sorted(fy,key=lambda f:f["filed"])};fyval=fyv[fe]
    ytd=[f for f in arr if f["form"].startswith("10-Q") and 0<dur(f)<350 and f["end"]>fe and abs((d(f["start"])-(d(fe)+timedelta(days=1))).days)<=5]
    if not ytd:return {"ttm":fyval,"end":fe}
    y=max(ytd,key=lambda f:(f["end"],f["filed"]))
    ps=d(y["start"])-timedelta(days=365);pe=d(y["end"])-timedelta(days=365)
    pr=[f for f in arr if f["form"].startswith("10-Q") and abs((d(f["start"])-ps).days)<=6 and abs((d(f["end"])-pe).days)<=6]
    if not pr:return {"ttm":None,"end":y["end"],"ytd":y["val"]}
    p=max(pr,key=lambda f:f["filed"])
    return {"ttm":fyval+y["val"]-p["val"],"end":y["end"],"ytd":y["val"],"ytd_prior":p["val"]}
def ttm(g,tags):
    best=None
    for tg in tags:
        if tg not in g:continue
        arr=[f for f in g[tg]["units"].get("USD",[]) if "start" in f and f.get("form") in("10-K","10-Q","10-K/A","10-Q/A")]
        if not arr:continue
        r=ttm1(arr)
        if not r:continue
        key=(r["end"],r["ttm"] is not None)
        if best is None or key>best[0]:best=(key,r)
    return best[1] if best else None
TAGS={"rev":["Revenues","RevenueFromContractWithCustomerExcludingAssessedTax","RevenueFromContractWithCustomerIncludingAssessedTax","SalesRevenueNet","RevenuesNetOfInterestExpense"],"oi":["OperatingIncomeLoss"],"ocf":["NetCashProvidedByUsedInOperatingActivities"],"capex":["PaymentsToAcquirePropertyPlantAndEquipment","PaymentsToAcquireProductiveAssets","PaymentsToAcquirePropertyPlantAndEquipmentAndIntangibleAssets"]}
def fund():
    tk=requests.get("https://www.sec.gov/files/company_tickers.json",headers=SEC,timeout=60).json()
    cik={v["ticker"]:v["cik_str"] for v in tk.values()};out={}
    for t in FUND_T:
        try:
            j=requests.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik[t]):010d}.json",headers=SEC,timeout=90).json()
            g=j["facts"].get("us-gaap",{});out[t]={k:ttm(g,v) for k,v in TAGS.items()}
        except Exception as e: out[t]={"err":repr(e)[:80]}
        time.sleep(0.4)
    return out

pc=lambda v:("−" if v<0 else "+")+f"{abs(v)*100:.0f}%"
b=lambda x:f"{x/1e8:,.0f}".replace('-','−')
def main():
    data={}
    for q in list(M)+sorted(set(M.values())-{"BABA"}):
        rows,sp=yget(q)
        if rows:data[q]=(rows,sp)
        time.sleep(0.25)
    st={L:stats(*data[L]) for L in M if L in data}
    asof=max(s["asof"] for s in st.values())
    hits=[L for L,s in st.items() if (s["price"]<=PRICE_MAX or s["dd"]<=DD_MAX) and s["fl"]<=NEAR_MAX and s["n52"]>=60]
    F=fund()
    def good(t):
        o=F.get(t) or {};g=lambda k:((o.get(k) or {}).get("ttm"))
        oi,ocf=g("oi"),g("ocf");cx=g("capex") or 0
        if ocf is None:return None
        return dict(oi=oi,ocf=ocf,fcf=ocf-cx,rev=g("rev"),pos=(oi is None or oi>0) and ocf>0)
    prev=json.load(open("prev_state.json")) if os.path.exists("prev_state.json") else {}
    pset=set(prev.get("hits",[]));new=[h for h in hits if h not in pset] if pset else [];gone=[h for h in pset if h not in hits]
    order=MANUAL+[h for h in sorted(hits,key=lambda x:st[x]["dd"]) if h not in MANUAL]
    order=[x for x in order if x in st]
    def row(L):
        s=st[L];u=M[L];nm=KR.get(u,u);mark=f"**{L}**" if L in hits else L
        return [f"{mark}\n~{nm}~",f"${s['price']:.2f}",pc(s['dd']),pc(s['fl']),pc(s['r1'])]
    unders=[]
    for L in order:
        u=M[L]
        if u in FUND_T and u not in unders:unders.append(u)
    def frow(t):
        o=F.get(t) or {};x=good(t)
        if not x:return [KR.get(t,t),'—','—','—','수집 못함']
        r=o["rev"] or {};gr=""
        if r.get("ytd") and r.get("ytd_prior"):gr=f"\n~누적 {(r['ytd']/r['ytd_prior']-1)*100:+.0f}%~".replace('-','−')
        if x["oi"] is not None and x["oi"]<=0:lab="영업적자"+("\nFCF 적자" if x["fcf"]<0 else "")
        elif x["ocf"]<=0:lab="현금 소진"
        elif x["fcf"]<0:lab="흑자\nFCF 적자"
        else:lab="**양호**" if x["rev"] and r.get("ytd") and r.get("ytd_prior") and r["ytd"]>r["ytd_prior"] else "흑자"
        return [KR.get(t,t).replace('코인베이스','코인베\n이스'),(b(x["rev"]) if x["rev"] else '—')+gr,'—' if x["oi"] is None else b(x["oi"]),b(x["fcf"]),lab]
    T=json.load(open("levwatch/levwatch-candidates.json",encoding="utf-8"))
    now=dt.datetime.utcnow()+dt.timedelta(hours=9)
    for s in T["sections"]:
        if s["title"].startswith("2. ETF 상태"):
            s["title"]=f"2. ETF 상태 ({asof}, 자동 갱신)"
            s["intro"]="**굵은 글씨**는 자동 조건(가격 $12 이하 또는 52주 −75% 이하, 그리고 52주 저점 대비 +20% 이내)에 부합한 ETF이고, 나머지는 수동 관찰 목록입니다."
            s["table"]["rows"]=[row(L) for L in order]
            s["bullets"]=[f"**자동 조건 부합 {len(hits)}개**: {', '.join(sorted(hits,key=lambda x:st[x]['dd']))}.",
              (f"**전일 대비 신규 {', '.join(new) if new else '없음'} / 이탈 {', '.join(gone) if gone else '없음'}**." if pset else "첫 실행이라 신규·이탈 비교는 다음 실행부터 표시됩니다."),
              "**5달러 아래 ETF**: "+(', '.join(f"{L}(${st[L]['price']:.2f})" for L in sorted(st,key=lambda x:st[x]['price']) if st[L]['price']<5) or '없음')+". 5달러 아래는 역분할이 잦아 가격이 리셋될 수 있습니다."]
        elif s["title"].startswith("3. 기초 기업"):
            s["title"]="3. 기초 기업 펀더멘털 (TTM, 억 달러, 자동 갱신)"
            s["table"]["rows"]=[frow(t) for t in unders]
    # 요약: 자동 줄 추가
    T["summary"]=[x for x in T["summary"] if not x.startswith("**자동 선별")]
    T["summary"].insert(1,f"**자동 선별(기준 {asof})**: 조건 부합 ETF {len(hits)}개"+(f", 신규 {', '.join(new)}" if new else "")+(f", 이탈 {', '.join(gone)}" if gone else "")+". 아래 2·3번 표는 매일 자동 갱신됩니다.")
    T["updated"]=now.strftime("%Y-%m-%d %H:%M")
    os.makedirs("out",exist_ok=True)
    json.dump(T,open("out/levwatch-candidates.json","w"),ensure_ascii=False,indent=1)
    json.dump([{"id":T["id"],"title":T["title"],"date":T["date"],"updated":T["updated"],"summary":T["summary"][0]}],open("out/index.json","w"),ensure_ascii=False,indent=1)
    json.dump({"asof":asof,"hits":hits,"updated":T["updated"]},open("out/state.json","w"))
    print("asof",asof,"hits",hits,"new",new,"gone",gone,"n_etf",len(st))
if __name__=="__main__":main()
