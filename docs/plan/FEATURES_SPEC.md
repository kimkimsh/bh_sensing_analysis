# FEATURES_SPEC — 기능 명세 (Functional Spec)

> 이 도구가 **무엇을 하는가**(기능)만 정리한 문서. 알고리즘은 `SCORING_SPEC.md`, 구조/빌드는 `PLAN.md`.
> 우선순위: **P0** = MVP 데모 필수 / **P1** = 있으면 강함 / **P2** = 스트레치.
> 각 기능은 ID·설명·입력·출력·수용기준(AC)으로 기술.

---

## A. 데이터 수집 (Ingestion)

### F-A1 — 폴더 스캔 & capture 그룹핑 · **P0**
- 설명: `data/` 트리를 재귀 스캔해 파일명을 파싱하고, 동일 `(device, meat, cut, date, posIdx)` 프레임을 **1 capture**로 묶는다.
- 입력: `data/<backup>/<deviceId>/<meat>/<cut>/<YYMMDD>/*.png|jpeg`
- 출력: `CaptureGroup` 목록(메타: device/meat/cut/menu/date/index/band_count/frame_dir)
- AC: capture = `(meat,cut,date,posIdx)` 그룹; 각 capture **8–11 band**(beef=10), N capture = 파일수/band수. 고정 "44/11" 금지. `" (copy)"` 접미사 정상 처리. fixture=`260612_office_backup/206/beef/striploin/251016`(10파일=1pos).

### F-A2 — 스펙트럼 큐브 로딩 · **P0**
- 설명: capture의 파장 프레임을 `(min,max,peak)` 키 dict로 lazy 로드(grayscale uint8). `bandByLed(ledId)` 접근 제공.
- AC: PNG/JPEG 동일 band 충돌 시 **PNG 우선**(244건); `720`(led10 peak740 vs led9 peak730) **peak로 구분**; `999_999_999` 센티넬·희귀 band 드롭(band_count 미오염). `capture_id`=device/meat/cut/date/posIdx **결정적**, **동일 복사 트리(726파일) collapse**. 실제 ~**3,044 capture 그룹**.

### F-A3 — 메뉴/날짜 인벤토리 · **P1**
- 설명: 스캔 결과로 사용 가능한 **메뉴 목록**과 **날짜 범위**, capture 수를 집계해 대시보드 필터에 공급.
- AC: 메뉴별/날짜별 capture 수가 대시보드 사이드바에 표시됨.

---

## B. 점수 산출 (Scoring) — 두 방식

### F-B1 — Rule ROI(조건문) 점수 · **P0**
- 설명: 순수 numpy 스펙트럼 임계 cascade로 ROI 산출 + 픽셀 도넨스 분류(번트/슬라이틀리/프로퍼) → `ScoreResult`.
- 출력: `pct_proper/pct_slightly_burnt/pct_burnt(+raw)`, `cooking_score`, `maillard_score`, `grade`.
- AC: beef striploin capture에서 0~100% 범위의 클래스별 % 및 grade 산출, ROI=0 가드 동작.

### F-B2 — ONNX ROI(AI) 점수 · **P0**
- 설명: meatSegNet(5채널)로 고기 인스턴스/ROI 분할 → 인스턴스별 도넨스 → `ScoreResult`(+per-instance).
- AC: 실제 meatSegNet 추론으로 label_map(0..4) 생성, `>=500px` 인스턴스만 채택, beef capture에서 점수 산출.

### F-B3 — 공유 출력 계약 보장 · **P0**
- 설명: 두 방식 모두 동일 `ScoreResult` 필드/후처리(`DonenessKernel`)를 거쳐 **사과 대 사과** 비교 가능.
- AC: 동일 capture를 두 방식에 넣으면 동일 스키마 행 2개(method='ai'|'conditional') 생성.

### F-B4 — 등급 사다리 · **P1**
- 설명: 메뉴별 `{score_field, ladder}` 데이터구동 등급(grade 0=완료) 부여.
- AC: 시드된 메뉴(beef/chicken/pork)에서 grade·grade_label 출력; 미정의 메뉴는 기본 사다리 + "근사" 표기.

### F-B5 — 학습형 AI 도넨스 분류기 · **P1 (near-tie 회피 권고 승격, 사용자 확인)**
- 설명: 9 파장 특징으로 소형 픽셀 분류기 학습 → 규칙 임계 대체 "AI 도넨스". 도넨스 자체가 다른 진짜 ML-vs-규칙 비교.
- AC: 토글로 활성화 시 조건문과 **시각적으로 다른** 도넨스 오버레이/점수 생성.

---

## C. 비교 (AI ↔ 조건문)

### F-C1 — 3분할 시각 비교 · **P0**
- 설명: 한 capture에 대해 **원본(ch3/led10 모노) | AI 오버레이 | 조건문 오버레이**를 나란히 표시.
- AC: `st.columns(3)`로 동일 해상도 3 이미지 + 캡션. 도넨스 색(번트>슬라이틀리>프로퍼) 일관.

### F-C2 — 클래스별 % 델타 · **P0**
- 설명: 같은 capture의 두 방식 `pct_proper/slightly/burnt` 차이를 metric(델타)로 표시.
- AC: 비교축은 **항상 per-class %**, `maillard_score` 공동플롯 **금지**(스케일 상이). 각 클래스 % + (AI−조건문) 델타 + agreement(MAE pts). 3분할은 공유 범례 1개 + 패널별 동일 100% 누적바.

### F-C3 — AI vs 조건문 산점도 · **P1**
- 설명: beef striploin capture들을 (AI 점수, 조건문 점수) 산점도로 — 일치/불일치 한눈에.
- AC: 축 = 사용자 선택 클래스 %(라디오, 기본 burnt), y=x 기준선 + MAE(pts) 대형 캡션, 점은 signed Δ 발산색. `maillard_score` 금지.

### F-C4 — Bland-Altman 일치도(스트레치) · **P2**
- 설명: 두 방식의 평균 대비 차이 플롯으로 체계적 편향 확인(matplotlib).
- AC: 시간 남을 때만; 없으면 F-C3로 대체.

---

## D. 시각화 / 분석 (By date · By menu)

### F-D1 — 날짜별 추이 · **P0**
- 설명: 선택 메뉴/기간에 대해 날짜별 평균 점수(클래스별 %, 방식별) 라인 차트.
- AC: class=색, method=선스타일(ai 실선/cond 점선), 기본 1개 클래스(burnt) 라디오로 6계열 난잡 회피. 사이드바 날짜/메뉴 필터 반영.

### F-D2 — 메뉴별 비교 · **P0**
- 설명: 메뉴별 평균 점수(방식별) 그룹 바 차트.
- AC: 메뉴 다중선택 필터 반영, 방식별 색 구분.

### F-D3 — capture 탐색/선택 · **P0 (최소 선택은 필수 — 3분할 F-C1이 의존)**
- 설명: 필터된 capture 테이블에서 행 선택 → F-C1/F-C2 상세로 연결.
- AC: 테이블 정렬/필터, 선택 시 해당 capture 오버레이 로드.

### F-D4 — per-instance 드릴다운(옵션) · **P2**
- 설명: AI 인스턴스별(class/픽셀/bbox/점수) 표. (v1 컷 후보)

---

## E. 영속/실행 (Persistence & CLI)

### F-E1 — DuckDB 영속 · **P0**
- 설명: `captures`/`scores` 테이블에 capture×method 행 기록(단일 writer), 오버레이 PNG 캐시.
- AC: 재실행 시 `read_only`로 재오픈; 집계 쿼리(by_date/by_menu/diff/paired) 100ms 이하.

### F-E2 — 파이프라인 CLI · **P0**
- 설명: `run_pipeline.py`로 scan→두 scorer→write+오버레이 캐시. `--limit`(스모크), `--methods`(ai|conditional|both).
- AC: `--limit N`이 N capture만 처리해 DB를 채움; 전수 실행 시 ~3,060 capture 처리(분 단위).

### F-E3 — 대시보드 기동 · **P0**
- 설명: `streamlit run app/dashboard.py`(headless)로 read_only DB를 읽어 D/C 기능 제공.
- AC: 빈/부분 DB에서도 크래시 없이 기동, 필터·차트·비교 렌더.

---

## F. 비기능 (Non-functional)

- **NF-1 충실도**: 모든 C++ 대비 편차(3중 offset 1회 적용, ROI 모폴로지 근사, beef-only 글로벌, 점수 스케일 차) 문서화. 가능 시 C++ 바이너리 1건 수치 대조.
- **NF-2 성능**: 세션 1회 생성·재사용, numpy 벡터화, `@st.cache_data`/`@st.cache_resource`.
- **NF-3 재현성**: `requirements.txt` 핀 고정, `.venv`, fixtures로 오프라인 테스트.
- **NF-4 안전성**: `data/`,`ai_model/`,`.venv/`,`onnxruntime-linux-x64-*/` 는 .gitignore(대용량/산출물 미추적).

---

## 우선순위 요약
- **P0(데모 필수)**: F-A1, F-A2, F-B1, F-B2, F-B3, F-C1, F-C2, F-D1, F-D2, F-E1, F-E2, F-E3
- **P1**: F-A3, F-B4, **F-B5(near-tie 회피 권고)**, F-C3, F-D3
- **P2(스트레치)**: F-C4, F-D4
