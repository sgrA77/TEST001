#!/usr/bin/env python3
"""KQ_FETCH.py - 코스닥 지수/ETF/주요 종목 일봉(종가·수정종가·거래량) -> kq.json (GitHub Actions)"""
import json, time, requests
UA = {"User-Agent": "Mozilla/5.0"}
CODES = """068270 셀트리온|091990 셀트리온헬스케어|068760 셀트리온제약|196170 알테오젠|028300 HLB|067630 HLB생명과학|141080 리가켐바이오|298380 에이비엘바이오|000250 삼천당제약|086900 메디톡스|145020 휴젤|214450 파마리서치|214150 클래시스|237690 에스티팜|086450 동국제약|
247540 에코프로비엠|086520 에코프로|066970 엘앤에프|278280 천보|348370 엔켐|058470 리노공업|240810 원익IPS|039030 이오테크닉스|036930 주성엔지니어링|357780 솔브레인|005290 동진쎄미켐|095340 ISC|064760 티씨케이|084370 유진테크|042700 한미반도체|183300 코미코|222800 심텍|033640 네패스|131290 티에스이|036540 SFA반도체|056190 에스에프에이|036830 솔브레인홀딩스|108320 LX세미콘|
263750 펄어비스|293490 카카오게임즈|112040 위메이드|078340 컴투스|041510 에스엠|035900 JYP|122870 와이지엔터|035760 CJ ENM|192080 더블유게임즈|035720 카카오|053800 안랩|067160 SOOP|
096530 씨젠|048260 오스템임플란트|214370 케어젠|145720 덴티움|277810 레인보우로보틱스|091700 파트론|009520 포스코엠텍|046890 서울반도체|035080 인터파크|023590 다우기술|060310 3S|
053030 바이넥스|060720 KH바텍|032500 케이엠더블유|038540 상상인|084110 휴온스글로벌|950130 엑세스바이오|041960 코미팜|215600 신라젠|083450 GST|101490 에스앤에스텍|049950 미래컴퍼니|045390 대아티아이|
122900 아이마켓코리아|041190 우리기술투자|950160 코오롱티슈진|003670 포스코퓨처엠|005070 코스모신소재|030190 엔에스엔|032190 다우데이타|950210 프레스티지바이오|226950 올릭스|310210 보로노이|328130 루닛|
025980 아난티|093370 후성|137310 에스디바이오센서|039200 오스코텍|085660 차바이오텍|000660 SK하이닉스|091120 이엠텍|079160 CJ CGV|005250? |
064350 현대로템|058610 에스피지|099190 아이센스|086520 에코프로|065350 신성델타테크|051500 CJ프레시웨이|020150 롯데에너지머티리얼즈|039490 키움증권|086390 유니테스트|
053280 예스24|020000 한섬|052690 한전기술|006730 서부T&D|007390 네이처셀|045100 한양이엔지|049070 인탑스|099320 쎄트렉아이|033500 동성화인텍|"""
syms = []
for tok in CODES.replace("\n", "").split("|"):
    tok = tok.strip()
    if not tok or "?" in tok: continue
    syms.append(tok.split()[0])
syms = list(dict.fromkeys(syms))
out = {}
def fetch(q):
    for host in ("query1", "query2"):
        try:
            r = requests.get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{q}?period1=946684800&period2=1900000000&interval=1d&events=div,split", headers=UA, timeout=60)
            j = r.json()["chart"]["result"][0]
            ts = j["timestamp"]; ind = j["indicators"]
            adj = ind["adjclose"][0]["adjclose"] if "adjclose" in ind else ind["quote"][0]["close"]
            c = ind["quote"][0]["close"]; v = ind["quote"][0]["volume"]
            rows = [[t, round(a, 4), round(cc, 2) if cc is not None else None, vv] for t, a, cc, vv in zip(ts, adj, c, v) if a is not None]
            return rows
        except Exception as e:
            time.sleep(1)
    return None
for q, name in (("%5EKQ11", "KOSDAQ"), ("%5EKS11", "KOSPI"), ("229200.KS", "KODEX코스닥150"), ("232080.KS", "TIGER코스닥150")):
    r = fetch(q)
    if r: out[name] = r; print(name, len(r))
for c in syms:
    for suf in (".KQ", ".KS"):
        r = fetch(c + suf)
        if r and len(r) > 100:
            out[c + suf] = r; print(c + suf, len(r), r[0][0]); break
json.dump(out, open("kq.json", "w"))
print("total", len(out))
