# REVIEW_NOTES — 플랜 리뷰 통합 (4 lens + Codex)

계획 단계 교차검증. **Claude 4 lens**(eng / CEO / devex / design) 완료 + **Codex(최신 GPT, xhigh)** 교차검증.
아래는 통합 findings → 적용한 수정 → 미해결 결정. (원 docs는 본 노트 반영해 수정함.)

## 0. 수렴 판정
4 lens가 **강하게 수렴**: (a) 비교가 구조상 near-tie 위험, (b) 충실도 함정 다수, (c) 비교축은 per-class %여야, (d) 사실 오류 2건(앵커 순서·band 수).
**Codex(최신 GPT, xhigh) 완료 → 집합 수렴**: 동일 대형 리스크 재확인(약한 비교, 앵커 y-major, 후기통합·실질 직렬, deps 미설치, 오라클 비현실, dedup, 클래스 인코딩). **처방 1건 발산**=약한 비교 해결책(§8). Codex 신규 must-fix 3건도 §8.

---

## 1. 즉시 적용한 사실 수정 (verified errors)

1. **YOLO-seg 앵커 순서 = y-major** (`OnnxROIRecognizer.h:147-158`의 `for stride{ for y{ for x }}`). 기존 docs "x-major" → **수정**. Stream B는 "실행됨"이 아니라 **실제 추론 → 비어있지 않은 BEEF label_map**을 종료 게이트로.
2. **band 수는 가변** — beef striploin = **10 band**(620 없음), 날짜 폴더 파일수 10/20/30/90/160(=position수×band수). 기존 "44=4 pos×11 band, ~3,060 captures" → **수정**(메뉴별 band 수 상이, capture = `(meat,cut,date,posIdx)` 그룹).
3. **LED↔band 정본표 확보**(`PropertiesDatabase.h:113-125`, devex가 정적 추출 — C++ 빌드 불필요):

   | ledId | min | max | peak | 비고 |
   |------:|----:|----:|-----:|------|
   | 0 | 410 | 420 | 415 | |
   | 1 | 440 | 460 | 450 | |
   | 2 | 460 | 480 | 470 | meatSegNet ch0 |
   | 4 | 520 | 610 | 567 | meatSegNet ch1 |
   | 5 | 585 | 595 | 590 | |
   | 8 | 650 | 670 | 660 | meatSegNet ch2 |
   | 9 | 720 | 750 | **730** | ⚠ 720nm 모호 — led9 |
   | 10 | 720 | 740 | **740** | meatSegNet ch3 — led10 |
   | 11 | 800 | ... | ... | |
   | 12 | 840 | 870 | 850 | meatSegNet ch4 |
   | 14 | 930 | ... | ... | |
   → **720nm은 (min,max,peak)로 led9(730) vs led10(740) 구분**. meatSegNet/도넨스 규칙은 **led10(peak740)** 사용.
4. **offset 적용 횟수 정정**: 글로벌은 픽셀카운트에서 재계산하므로 **글로벌엔 사실상 1회만** 적용(`OnnxInferenceOutput.h:81-90`). per-instance 요약은 2회 누적. → 커널 글로벌 경로는 1회 적용(C++ 글로벌과 일치), `faithful_triple_offset`는 **per-instance 재현 전용**으로 한정.

## 2. Phase-0로 승격 (코딩 전 차단 항목)

- **label_map 클래스 인코딩 확정**: CLASS_NAMES(BEEF,CHICKEN,LAMB,PORK)와 라우팅 주석(0=BEEF,1=LAMB,2=CHICKEN)이 **모순**. beef-only 글로벌 데모가 전적으로 의존 → fixture 1장 실제 추론으로 정수↔클래스 맵 확정해 `bands.py`/`result.py` 상수로 동결.
- **DonenessKernel 입력 데이터형 동결**: `kernel(roi_mask: bool[H,W], class_map: uint8[H,W] ∈ {0..4}) -> ScoreResult`. A·B가 **공유 합성배열 단위테스트**를 import(시그니처만 아닌 데이터 셰이프 계약).
- **Makefile/justfile + README Run stub**: `setup/fixtures/db-init/smoke/dash` 타깃을 Phase 0에 — 4 stream이 동일 엔트리포인트 공유(README는 Phase 2가 아니라 Phase 0 stub).
- **트레이서 불릿 스모크**(`make smoke`): 실제 beef fixture 1개로 scan→두 scorer(B는 stub kernel)→DuckDB write→read_only reopen→by_menu≥1행→오버레이 PNG 1장. **4개 위험 seam을 8분차에 한 번에** 검증(20분 Phase-2 위험 완화).

## 3. Phase 배분 재조정

- **Stream C가 실제 DB를 조기 인도**: C(35분, 슬랙 35분 보유)가 Stream A로 실제 capture 2개를 채운 `scores.duckdb`를 인도 → **Phase 2는 AI(B)+viz seam만 통합**.
- Stream B 종료조건 = `AiScorer.score(fixture)`가 채워진 `ScoreResult` 반환 + 오버레이 렌더(Phase 1 게이트, Phase 2 발견 금지).

## 4. 제품/데모 (CEO) — 결정 필요

- **near-tie 위험**: 두 방식이 동일 `DonenessKernel`+규칙을 공유하면 차이가 ROI에서만 발생 → 산점도가 y=x에 붙음.
  - **권고**: **F-B5(학습형 픽셀 도넨스 분류기)를 P2→P1**로 승격해 AI 도넨스 자체를 다르게. (시간 부족 시: 9밴드 로지스틱이라도 — 결정경계만 달라도 시각적 불일치 발생.)
  - **대안(F-B5 미채택 시)**: AI **세그멘테이션 오버레이를 hero**로, "AI가 고기를 정밀 분할 vs 규칙은 뭉갬"을 스토리로. (정직·충실, 즉시 실행.)
- **데모 내러티브(60초)**: "11파장 → AI 세그멘테이션이 스테이크를 인식 → 픽셀 도넨스 채점 → 같은 스테이크를 규칙으로 채점 → **불일치 지점**(델타/산점도) → C++ 엔진 대비 beef striploin 검증". → **C++ 오라클 대신 소스 정적 대조로 '검증' 주장**(아래 5).
- **차트 우선순위 하향**: 날짜별/메뉴별 추이는 정답 없어 검증 불가·임팩트 약 → "맥락"으로, 절약분을 단일 capture 비교/오버레이 폴리시에 투자.

## 5. DevEx — 사전설정 정정

- **현 상태(검증)**: `requirements.txt` 없음, `duckdb/pandas/streamlit/plotly/statsmodels` 미설치, `onnxruntime-linux-x64-*/` 미ignore(→ 본 노트로 .gitignore 보강 완료). model 로드 ~0.46s.
- **C++ 오라클(§7-7) 강등 P0→P2**: `../bh_chef...`는 Qt/CMake UI 바이너리(serial/camera 의존) — 90분 내 헤드리스 채점 덤프 비현실적. **대체**: 스코어링 상수·LED표를 **소스에서 정적 추출**(이미 LED표 확보), 편차 문서화(NF-1).
- **대시보드 read 가드**: DB 없음/락 시 "파이프라인 먼저 실행" 빈 상태. 실행 순서 = 파이프라인 → 대시보드(문서화).
- **고정 사전설정 명령**(devex 제공): `.venv/bin/pip install duckdb pandas streamlit plotly statsmodels` → `pip freeze > requirements.txt` → .gitignore 보강 → scaffold → 실제 fixture 복사(`260612_office_backup/206/beef/striploin/251016` 10파일=1pos) → LED표 박제 → DB init 라운드트립 → model 로드 확인.

## 6. 디자인/UX — 비교 가독성 (적용 지침)

- **3분할 = 공유 범례 1개 + 각 패널 동일 100% 누적바**(픽셀 아닌 막대길이로 비교). 팔레트는 `SOURCE_ANALYSIS §6` 정본 hex 단일소스.
- **비교축은 항상 per-class %**(공유 계약). `maillard_score`는 **단일방식 뷰에서만**, 라벨 `Maillard(AI weights)`/`(rule weights)`, **동일축 공동플롯 금지**.
- 날짜/메뉴: **class=색, method=선스타일(ai 실선/cond 점선)**, 기본 1개 클래스(burnt) 라디오로 6계열 난잡 회피. method 색은 전역 고정.
- **agreement 정량화**: 산점도에 MAE(pts) 대형 캡션 + 점을 signed Δ 발산색으로(체계적 편향 가시). Bland-Altman은 P2 유지.
- **first-screen hero**: 3분할 + agreement 메트릭을 스크롤 없이 최상단. (§9 수용기준에 추가.)
- hero 비주얼: **3분할 + 공유 범례 + 동일 누적바 + agreement 델타**(어디/얼마나/일치여부를 per-class %로 동시 전달).

## 7. 미해결 결정 (사용자/Codex)
- [ ] **F-B5(학습형 AI 도넨스)를 P1로 승격할지** — 비교를 진짜 다르게 만들지(시간 +α) vs 세그멘테이션-ROI 차이로만 갈지(정직·즉시). → 사용자 확인.
- [ ] Codex 교차검증 결과 수렴/발산(완료 시 §0).
- [ ] C++ 오라클: 정적 추출로 대체 확정(권고) vs 시간 남으면 1건 시도.

---

## 8. Codex 교차검증 reconcile (최신 GPT, xhigh)

**수렴(양측 동일)**: 약한 비교/오버스테이트, 앵커 y-major, Phase-2 과소·실질 직렬→Phase-0 end-to-end 1건 먼저, deps 미설치, C++ 오라클 비현실(Qt GUI·capture CLI 없음 `main.cc:21`)→정적추출, dedup, 클래스 인코딩 Phase-0 확정.

**발산 1건 — 약한 비교의 해결책 (= 사용자 A/B 결정)**:
- **CEO(A)**: F-B5 학습형 도넨스로 도넨스를 다르게 → 산점도 퍼짐, wow.
- **Codex(B)**: 도넨스를 동일 cascade로 통일하고 정직하게 **"ONNX ROI vs Rule ROI"로 개명** → 차이는 분할 품질(ROI), 오버레이로 가시.
- **권고(하이브리드)**: **B를 P0로 확실 출하**(정직·실행가능, 세그멘테이션 hero) + 시간 남으면 **F-B5(A)를 P1 스트레치**. 메서드명 정직화.

**Codex 신규 must-fix (문서 반영)**:
1. **ScoreResult에 오버레이 맵 부재** — Stream D는 roi_mask/class_map/도넨스맵 필요 → ScoreResult(또는 형제)에 렌더용 맵/경로 포함, Phase-0 동결(아니면 D가 A/B에 직렬 의존).
2. **726-파일 동일 복사 트리 + 244 cross-format 충돌**, 실제 capture **3,044 그룹** → `capture_id`=device/meat/cut/date/posIdx 결정적, 복사 트리 collapse, band당 PNG 우선.
3. **cascade 변형 불일치** — 라이브 AI는 `beef_strip_loin/ComponentRecognizer_BeefStripLoin_CharBroiler`, 조건문 SPEC은 `_america` 포팅. **옵션 B면 양쪽 동일(라이브 beef) cascade**. 빌드 전 라이브 파일 직접 read 필수.
4. **3분할(P0)인데 capture 선택(F-D3) P1** 모순 → 최소 선택 **P0** 승격.
- 참고: 라이브 recognizer가 8-slot 배열에 index 8 기입(`live recognizer:31`) — 소스 버그, 포팅 시 방어.

**판정**: 집합 수렴, 처방 1건만 발산(A/B) → 사용자 결정. 권고 = 하이브리드(B 출하 + F-B5 스트레치) & 정직 개명.
