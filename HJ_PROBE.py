import json, requests
UA = {"User-Agent": "Mozilla/5.0"}
urls = [
 "http://www.38.co.kr/html/fund/index.htm?o=nw",
 "http://www.38.co.kr/html/fund/index.htm?o=nw&page=2",
 "http://www.38.co.kr/html/ipo/ipo.htm",
 "https://kind.krx.co.kr/listinvstg/listingcompany.do?method=searchListingTypeMain",
 "https://kind.krx.co.kr/listinvstg/pubofrprogcom.do?method=searchPubofrProgComMain",
 "https://kind.krx.co.kr/listinvstg/listingcompany.do?method=searchListingCompanyMain",
 "https://ko.wikipedia.org/wiki/%ED%98%84%EB%8C%80%EC%9E%90%EB%8F%99%EC%B0%A8",
]
out = {}
for u in urls:
    try:
        r = requests.get(u, headers=UA, timeout=40)
        for enc in ("euc-kr", "utf-8"):
            try:
                t = r.content.decode(enc); break
            except Exception: t = r.text
        out[u] = {"status": r.status_code, "len": len(t), "head": t[:3000]}
    except Exception as e:
        out[u] = {"err": str(e)}
    print(u, out[u].get("status"), out[u].get("len"), out[u].get("err"))
json.dump(out, open("hj_probe.json", "w"), ensure_ascii=False)
