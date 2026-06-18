# FEATURES_SPEC — 기능 명세 (Functional Spec)

> 이 도구가 **무엇을 하는가**(기능)만 정리한 문서. 알고리즘은 `SCORING_SPEC.md`, 구조/빌드는 `PLAN.md`, **UX/UI·색·상태·데모 플로우는 `DESIGN_SPEC.md`**.
> 우선순위: **P0** = MVP 데모 필수 / **P1** = 있으면 강함 / **P2** = 스트레치.
> 각 기능은 ID·설명·입력·출력·수용기준(AC)으로 기술.
> **횡단 원칙(정답 없음 → 승자 없음)**: 모든 비교 카피·지표는 "정확도"가 아니라 **"agreement(일치도)"**. "AI가 더 정확/낫다" 표현 금지(DESIGN_SPEC §11).

---

## A. 데이터 수집 (Ingestion)

### F-A1 — 폴더 스캔 & capture 그룹핑 · **P0**
- 설명: `data/` 트리를 재귀 스캔해 파일명을 파싱하고, 동일 `(device, meat, cut, date, posIdx)` 프레임을 **1 capture**로 묶는다.
- 입력: `data/<backup>/<deviceId>/<meat>/<cut>/<YYMMDD>/*.png|jpeg`
- 출력: `CaptureGroup` 목록(메타: device/meat/cut/menu/date/index/band_count/frame_dir)
- AC: capture = `(device,meat,cut,date,posIdx)` 그룹; 각 capture **8–16 band 가변**(beef striploin도 날짜별 8~16, 일부 620 포함), `band_count`는 capture별 **동적 산출**. 고정 "beef=10"/"44/11" **금지**. `" (copy)"` 접미사 정상 처리 + 복사트리 collapse. fixture=`260612_office_backup/206/beef/striploin/251016`(10파일=1pos, all-JPEG).

### F-A2 — 스펙트럼 큐브 로딩 · **P0**
- 설명: capture의 파장 프레임을 `(min,max,peak)` 키 dict로 lazy 로드(grayscale uint8). `bandByLed(ledId)` 접근 제공.
- AC: PNG/JPEG 동일 band 충돌 시 **PNG 우선**(244건); `720`(led10 peak740 vs led9 peak730) **peak로 구분**; `999_999_999` 센티넬·희귀 band 드롭(band_count 미오염). `capture_id`=device/meat/cut/date/posIdx **결정적**, **동일 복사 트리(726파일) collapse**. 실제 **~2.8k–3.0k capture 그룹**(스캔 시 결정적 계산 — 그루핑 정의에 따라 2,817~2,961 관측; **고정값 박제 금지**).

### F-A3 — 메뉴/날짜 인벤토리 · **P1**
- 설명: 스캔 결과로 사용 가능한 **메뉴 목록**과 **날짜 범위**, capture 수를 집계해 대시보드 필터에 공급.
- AC: 메뉴별/날짜별 capture 수가 대시보드 사이드바에 표시됨.

---

## B. 점수 산출 (Scoring) — 두 방식

### F-B1 — Rule ROI(조건문) 점수 · **P0**
- 설명: 순수 numpy 스펙트럼 임계 cascade로 ROI 산출 + 픽셀 도넨스 분류(번트/슬라이틀리/프로퍼) → `ScoreResult`.
- 출력: `pct_proper/pct_slightly_burnt/pct_burnt(+raw)`, `cooking_score`, `maillard_score`, `grade`.
- AC: beef striploin capture에서 클래스별 %(proper/slightly/burnt **+ not_done**, 합=100) 및 grade 산출; ROI=0 가드; **게이트 밴드(410/440) 누락 시 0 대체 금지(스킵/에러)** — 0이면 라이브 게이트가 전 픽셀 통과해 점수 폭증.

### F-B2 — ONNX ROI(AI) 점수 · **P0**
- 설명: meatSegNet(5채널)로 고기 인스턴스/ROI 분할 → 인스턴스별 도넨스 → `ScoreResult`(+per-instance).
- AC: 실제 meatSegNet 추론으로 label_map 생성, `>=500px` 인스턴스만 채택, **정수↔클래스 인코딩은 Phase-0에서 실제 마스크로 확정**(beef-only 글로벌이 의존), beef capture에서 점수 산출.

### F-B3 — 공유 출력 계약 보장 · **P0**
- 설명: 두 방식 모두 동일 `ScoreResult` 필드/후처리(`DonenessKernel`)를 거쳐 **사과 대 사과** 비교 가능.
- AC: 동일 capture를 두 방식에 넣으면 동일 스키마 행 2개(method='ai'|'conditional') 생성.

### F-B4 — 등급 사다리 · **P1**
- 설명: 메뉴별 `{score_field, ladder}` 데이터구동 등급(grade 0=완료) 부여.
- AC: 시드된 메뉴(beef/chicken/pork)에서 grade·grade_label 출력; 미정의 메뉴는 기본 사다리 + "근사" 표기.

### F-B5 — 학습형 AI 도넨스 분류기 · ~~P1~~ **컷 (OUT OF SCOPE)**
- **컷 사유**: 사용자 제약 — AI는 ROI/세그멘테이션 전용, 도넨스 컴포넌트는 규칙(그대로 포팅). 학습형 분류기 = AI 컴포넌트 분석이라 제약 위반. 또한 라벨/마스크 **0개**라 학습 자체 불가.
- near-tie 회피는 **세그멘테이션 오버레이 + ROI-diff 가시화 hero**(F-C1)로 대체.

---

## C. 비교 (AI ↔ 조건문)

### F-C1 — ROI-diff hero + 3분할 시각 비교 · **P0**
- 설명: **[HERO]** mono(ch3/led10) 배경 + **ONNX-ROI 윤곽 vs Rule-ROI 윤곽 + 대칭차(한쪽에만 포함된 픽셀) 음영** — 두 방식 차이는 ROI 경계뿐이므로 경계를 직접 가시화. 그 아래 **원본 | AI 오버레이 | Rule 오버레이** 3분할.
- AC: **hero = 단일 PRIMARY** overlap-map (mono 배경 + Both-agree 그레이 α0.18 / ONNX-only cyan #56B4E9 실선윤곽 / Rule-only magenta #D55E00 점선·해치) — **ROI_DIFF 팔레트 전용, doneness 램프 사용 금지**(시청자가 "번트"와 "Rule-only"를 혼동 방지). 3칩 inline 범례 + 평문 IoU 캡션. **3분할은 hero 아님 → fold 아래 `st.expander("Per-panel detail", expanded=False)`**(`st.columns(3)` 동일 해상도 + 공유 범례 1개). 오버레이는 (roi_mask, class_map, mono)의 **순수 함수**(방식별 분기 금지). **3분할 오버레이만 MASK 정본 hex**(평면 hex, 라이브 `makeHueOfHSV` 휴-램프 대신 가독성용 — "as-is" 아님 명기). 상세 DESIGN_SPEC §7.

### F-C2 — ROI 면적 델타 + 클래스별 % 델타 · **P0**
- 설명: 같은 capture의 **각 방식 ROI px / 면적·IoU 델타**(주축) + `pct_not_done/proper/slightly/burnt`(4-way, 합=100) 차이.
- AC: **KPI 행**(`st.metric`, JetBrains Mono): **IoU(헤드라인 + 평문 캡션 "IoU 0.93 — 두 방식이 거의 같은 영역; >0.90=강한 일치") · Dice(보조) · signed ROI-area delta px(near-tie에서도 비0)**. 모든 델타 **sign-only + 중립색**(green=good 금지, 정답 없음=승자 없음). 차트는 `chartCategoricalColors=DONENESS_RAMP` 상속(per-figure color 0), **NOT_DONE=그레이 후퇴**, `pattern_shape` + ND/P/S/B 칩, per-class % 옆 **절대 픽셀카운트**("+40% burnt"가 12px이면 작게 읽힘). `maillard_score` 공동플롯 **금지**(스케일 상이). 패널별 동일 **4-way 누적바**(not_done 포함). **MAE(pts)는 Explore 탭으로 강등**. agreement 수식·zero-union 가드 = `SCORING_SPEC §7`.

### F-C3 — AI vs Rule 산점도 · **P1 (보조, fold 아래)**
- 설명: beef striploin capture들을 (ONNX-ROI %, Rule-ROI %) 산점도로. **near-tie라 y=x에 붙음** → hero 아님, 보조 증거.
- AC: 축 = 선택 클래스 %(라디오, 기본 burnt), y=x 기준선 + MAE(pts) 캡션, **점 색/크기 = ROI-IoU**(퍼짐이 분할 불일치에서 옴을 가시). `maillard_score` 금지. fold 아래 배치.

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

### F-D5 — Demo Mode (가이드 골든패스) · **P1**
- 설명: 사이드바 `st.radio('Demo'|'Explore')`. **Demo**: 큐레이션 capture_id(`260612_office_backup/206/beef/striploin/250903`, Phase-0 게이트 확정) 하드코딩·자동선택(2.8k행 테이블 헌트 skip), Compare hero 사전렌더(detail expander 접힘), 6-beat `DEMO_SCRIPT`를 번호 `st.status`/`st.info` 캡션으로 구동. **Explore**: 전체 필터 + capture 테이블.
- AC: Demo 모드가 큐레이션 capture로 **테이블 인터랙션 0회**로 열린다. Phase-2 스모크가 해당 capture의 **비자명·서사일관 ROI 불일치**(near-perfect overlap 아님)를 검증. 애니메이션/온보딩 플로우 없음(스코프 가드). 상세 DESIGN_SPEC §10.

---

## E. 영속/실행 (Persistence & CLI)

### F-E1 — DuckDB 영속 · **P0**
- 설명: `captures`/`scores` 테이블에 capture×method 행 기록(단일 writer), 오버레이 PNG 캐시.
- AC: 재실행 시 `read_only`로 재오픈; 집계 쿼리(by_date/by_menu/diff/paired) 100ms 이하.

### F-E2 — 파이프라인 CLI · **P0**
- 설명: `run_pipeline.py`로 scan→두 scorer→write+오버레이 캐시. `--limit`(스모크), `--methods`(ai|conditional|both).
- AC: `--limit N`이 N capture만 처리해 DB를 채움; 전수 실행 시 ~2.8k–3.0k capture 처리(분 단위, 스캔 시 결정적 계산).

### F-E3 — 대시보드 기동 · **P0**
- 설명: `streamlit run app/dashboard.py`(headless)로 read_only DB를 읽어 D/C 기능 제공.
- AC: 빈/부분 DB에서도 크래시 없이 기동, 필터·차트·비교 렌더. **상태 매트릭스(DESIGN_SPEC §8)**:
  - **FIRST_RUN/no-DB** (P0): `scores.duckdb` 없음/`count==0` → read_only open **전에** 파일존재+count 가드, `st.info("아직 점수 없음 — bash run.sh, 또는 Demo Mode")`.
  - **NO-ROI** (P0 가드): Rule 모폴로지가 못 찾음 → `st.warning("Rule-ROI 영역 없음 — IoU 미정의")` + §SCORING_SPEC §7 zero-union 가드(NaN 금지).
  - **PARTIAL** (P1): 메뉴에 AI 행 없음 → `st.warning("AI ROI 미산출 — Rule만 표시")` + ONNX 윤곽 숨김.
  - **LOADING** (P1): `st.status("Segmenting meat instances… / Scoring 11 wavelength bands…")` + `st.spinner`.
  - **ERROR** (P1): ONNX 로드 실패·band 누락·DuckDB 락·오버레이 경로 없음 → `st.error` + `st.expander` traceback.
  - **P0 floor** = no-DB + no-ROI 가드(크래시 방지), 나머지는 P1.

---

## F. 비기능 (Non-functional)

- **NF-1 충실도**: 모든 C++ 대비 편차(3중 offset 1회 적용, ROI 모폴로지 근사, beef-only 글로벌, 점수 스케일 차) 문서화. 가능 시 C++ 바이너리 1건 수치 대조.
- **NF-2 성능**: 세션 1회 생성·재사용, numpy 벡터화, `@st.cache_data`/`@st.cache_resource`.
- **NF-3 재현성**: `requirements.txt` 핀 고정, `.venv`, fixtures로 오프라인 테스트.
- **NF-4 안전성**: `data/`,`ai_model/`,`.venv/`,`onnxruntime-linux-x64-*/` 는 .gitignore(대용량/산출물 미추적).

---

## 우선순위 요약
- **P0(데모 필수)**: F-A1, F-A2, F-B1, F-B2, F-B3, F-C1, F-C2, F-D1, F-D2, **F-D3(최소 capture 선택 — 3분할/hero가 의존)**, F-E1, F-E2, F-E3(**no-DB·no-ROI 가드 floor**)
- **P1**: F-A3, F-B4, F-C3(Explore 탭), **F-D5(Demo Mode)**, F-E3(full 상태 매트릭스), 디자인 P1(카드·band strip·hero opacity 슬라이더)  (~~F-B5~~ **컷 — OUT OF SCOPE**: AI는 ROI 전용)
- **P2(스트레치)**: F-C4, F-D4, pixel "why this class?" inspector, PNG/CSV export, wipe-slider hero(경쟁 hero라 컷 우선)
- **디자인 P0(빌드 0분, 사전커밋)**: `.streamlit/config.toml`, `viz/palette.py`, `DEMO_SCRIPT.md`, `run.sh`/`demo.sh` (DESIGN_SPEC §12)
