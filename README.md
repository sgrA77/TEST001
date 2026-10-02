# Market Dashboard (TEST001) — v2

`TEST001.py → data.json → index.html → GitHub Pages`
GitHub Actions(`test.yml`, 수정 안 함)가 10분마다 `TEST001.py` 실행 → `data.json` 커밋.

## 적용 방법
1. 저장소의 `TEST001.py`, `index.html` 을 이 폴더의 파일로 교체 (test.yml·data.json 은 그대로)
2. Actions 탭에서 `Run workflow` 로 한 번 실행 → 새 형식의 data.json 생성
   - 첫 실행 전에는 data.json 형식이 달라 화면이 비어 보일 수 있음
   - 선행 이익수익률(Fwd EY)·매출 예상치 누적값은 그대로 이어받음

## 수정하는 곳
| 바꾸고 싶은 것 | 위치 |
|---|---|
| 종목·섹터·순서 | `TEST001.py` → `MARKET` |
| 처음에 접혀 있을 섹터 | `TEST001.py` → `FOLDED_SECTORS` |
| 맨 위 지표 3개 | `TEST001.py` → `TOP_BAR` |
| 거시 지표 | `TEST001.py` → `MACRO` (+ `RATE_CHANGES`, `MANUAL_MACRO`) |
| HY/BBB 스프레드가 안 들어올 때 | `TEST001.py` → `FRED_API_KEY` (무료 키) |
| 실적 추적 기업 / EVENTS 에 넣을 기간 | `EARNINGS` / `EARN_SOON_DAYS` |
| 일정 직접 추가 (IPO 포함) | `MANUAL_EVENTS` |
| AI IPO 판별 단어 | `IPO_AI_KEYWORDS` |
| 색 진하기 기준 | `index.html` → `CAP` |
| 색·카드 폭 | `index.html` 맨 위 `:root` |

## 화면 구성 (위 → 아래)
- **상단 고정 바**: VIX · USD/KRW · US 10Y 현재값, 업데이트 시각 (40분 넘게 갱신 없으면 빨간 "지연")
- **EVENTS**: FOMC / Fed Press / CPI / NFP / PCE + 3일 내 실적(보라) + AI IPO(청록), 한국시간·남은 시간
- **MARKET**: 섹터별 카드 (모바일 한 줄 2개). 카드 = 이름·가격 / 테마·거래대금·당일% / 1M·1Y·2Y 변동률
- **MACRO** (접힘): 현재값(전일 대비 값 증감) / 1M·1Y·2Y 칸 = 그 시점 실제 값, 색 = 현재 대비 변동
- **EARNINGS** (접힘): 기업별 카드, 지난 3분기 + 다음 예상 (EPS·매출, 전분기 대비 색, 예상 대비 ▲▼)
- **데이터 수집 경고**: 실패 사유 (실패 항목은 직전 값 + "지연" 표시)

1M / 1Y / 2Y 기준 = 전월 말 / 전년 말 / 재작년 말 종가. 상승 = 빨강, 하락 = 파랑.
접기 상태는 브라우저에 기억됨.
