#!/usr/bin/env python3
"""HJ_LIST.py - 이름에 현대/SK/삼성/한화 가 들어간 상장 종목 목록(+상장일) 수집 -> hj_list.json (GitHub Actions)"""
import re, json, requests, io, time
from html import unescape
UA = {"User-Agent": "Mozilla/5.0"}
KEYS = ("현대", "SK", "삼성", "한화")
out = {"naver": [], "kind": []}
# 1) 네이버 시가총액 목록
for sosok, mkt in ((0, "KOSPI"), (1, "KOSDAQ")):
    for page in range(1, 60):
        try:
            r = requests.get(f"https://finance.naver.com/sise/sise_market_sum.naver?sosok={sosok}&page={page}", headers=UA, timeout=30)
            t = r.content.decode("euc-kr", "ignore")
        except Exception as e:
            print("naver err", sosok, page, e); break
        rows = re.findall(r'<a href="/item/main\.naver\?code=(\w{6})" class="tltle">([^<]+)</a>', t)
        if not rows: break
        for code, name in rows:
            out["naver"].append([mkt, code, unescape(name)])
print("naver total", len(out["naver"]))
# 2) KIND 상장법인목록 (상장일 포함)
try:
    r = requests.get("https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13", headers=UA, timeout=60)
    t = r.content.decode("euc-kr", "ignore")
    trs = re.findall(r"<tr>(.*?)</tr>", t, re.S)
    for tr in trs[1:]:
        tds = [unescape(re.sub(r"<[^>]+>", "", x)).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(tds) >= 10:
            out["kind"].append(tds)
    print("kind total", len(out["kind"]), out["kind"][:2])
except Exception as e:
    print("kind err", e)
json.dump(out, open("hj_list.json", "w"), ensure_ascii=False)
