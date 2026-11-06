import json, requests
UA = {"User-Agent": "Mozilla/5.0"}
out = {}
def get(u, key, enc="euc-kr", **kw):
    r = requests.get(u, headers=UA, timeout=60, **kw)
    try: t = r.content.decode(enc)
    except Exception: t = r.content.decode("utf-8", "ignore")
    out[key] = t; print(key, r.status_code, len(t))
get("https://kind.krx.co.kr/listinvstg/listingcompany.do?method=searchListingTypeMain", "kind_main", "utf-8")
# POST 시도
data = {"method": "searchListingTypeSub", "currentPageSize": "3000", "pageIndex": "1", "orderMode": "1", "orderStat": "D", "forward": "listingtype_sub",
        "searchCodeType": "", "searchCorpName": "", "repIsuSrtCd": "", "marketType": "", "listingType": "", "country": "", "industry": "",
        "fromDate": "1974-01-01", "toDate": "2026-11-06", "choicTypeCd": "", "searchType": ""}
try:
    r = requests.post("https://kind.krx.co.kr/listinvstg/listingcompany.do", data=data, headers={**UA, "Referer": "https://kind.krx.co.kr/listinvstg/listingcompany.do?method=searchListingTypeMain"}, timeout=60)
    t = r.content.decode("utf-8", "ignore"); out["kind_post"] = t; print("post", r.status_code, len(t))
except Exception as e:
    print("post err", e)
get("http://www.38.co.kr/html/fund/index.htm?o=nw", "p38_fund")
get("http://www.38.co.kr/html/ipo/ipo.htm", "p38_ipo")
json.dump(out, open("hj_probe.json", "w"), ensure_ascii=False)
