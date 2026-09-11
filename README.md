## 관리

* 수정할 곳: TEST001.py

1. 관심 항목 추가/삭제
   stocks = ["SPY", "SPXL", "QLD"]

2. Yahoo Finance URL
   url = f"https://query1.finance.yahoo.com/v8/finance/chart/{stock}?range=2y&interval=1d"

   `{stock}` 부분에 stocks의 종목명이 자동으로 들어감.
   → 종목 추가 시 URL을 따로 수정할 필요 없음.

3. index.html
   종목명을 직접 입력하지 않음.
   data.json에 있는 종목을 자동으로 화면에 표시.

4. test.yml
   10분마다 자동 실행. 종목 추가/삭제 때문에 수정하지 않음.

5. data.json
   Python이 자동 생성. 직접 수정하지 않음.

### 요약
종목 추가/삭제 → TEST001.py의 `stocks`만 수정 → Commit → 끝.
