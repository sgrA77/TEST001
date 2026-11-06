import json, re, requests
from html import unescape
UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://kind.krx.co.kr/listinvstg/listingcompany.do?method=searchListingTypeMain", "X-Requested-With": "XMLHttpRequest"}
out = {}
def q(page, size, frm="2000-01-01", to="2026-11-06"):
    data = {"method": "searchListingTypeSub", "currentPageSize": str(size), "pageIndex": str(page), "orderMode": "1", "orderStat": "D", "forward": "listingtype_sub",
            "searchCodeType": "", "searchCorpName": "", "repIsuSrtCd": "", "isurCd": "", "listTypeArrStr": "01|02|03|04|05|", "choicTypeArrStr": "02|",
            "secuGrpArrStr": "0|ST|FS|MF|SC|RT|IF|DR|", "marketType": "", "country": "", "fromDate": frm, "toDate": to, "menuUrl": "/listinvstg/listingcompany.do?method=searchListingTypeMain"}
    r = requests.post("https://kind.krx.co.kr/listinvstg/listingcompany.do", data=data, headers=UA, timeout=60)
    return r.content.decode("utf-8", "ignore")
t = q(1, 100); out["p1"] = t; print(len(t))
print(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))[:1500])
json.dump(out, open("hj_probe.json", "w"), ensure_ascii=False)
