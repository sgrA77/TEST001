import json, re, requests, time
from html import unescape
UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://kind.krx.co.kr/listinvstg/listingcompany.do?method=searchListingTypeMain", "X-Requested-With": "XMLHttpRequest"}
def q(page, size=100, frm="1960-01-01", to="2026-11-06"):
    data = {"method": "searchListingTypeSub", "currentPageSize": str(size), "pageIndex": str(page), "orderMode": "1", "orderStat": "D", "forward": "listingtype_sub",
            "searchCodeType": "", "searchCorpName": "", "repIsuSrtCd": "", "isurCd": "", "listTypeArrStr": "01|02|03|04|05|", "choicTypeArrStr": "02|",
            "secuGrpArrStr": "0|ST|FS|MF|SC|RT|IF|DR|", "marketType": "", "country": "", "fromDate": frm, "toDate": to, "menuUrl": "/listinvstg/listingcompany.do?method=searchListingTypeMain"}
    for _ in range(3):
        try:
            r = requests.post("https://kind.krx.co.kr/listinvstg/listingcompany.do", data=data, headers=UA, timeout=60)
            return r.content.decode("utf-8", "ignore")
        except Exception as e:
            time.sleep(2)
    return ""
rows = []
for p in range(1, 120):
    t = q(p)
    trs = re.findall(r"<tr\s[^>]*onclick=\"fnDetailView\('([^']*)'[^)]*\)\">(.*?)</tr>", t, re.S)
    if not trs:
        print("stop at", p, len(t)); break
    for code, tr in trs:
        tds = [unescape(re.sub(r"<[^>]+>", "", x)).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        rows.append([code] + tds)
    print(p, len(trs), rows[-1][:4])
json.dump({"rows": rows}, open("hj_probe.json", "w"), ensure_ascii=False)
print("total", len(rows))
