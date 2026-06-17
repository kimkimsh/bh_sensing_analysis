# REVIEW_NOTES — 플랜 리뷰 통합 (4 lens + Codex)

계획 단계 교차검증. **Claude 4 lens**(eng / CEO / devex / design) 완료 + **Codex(최신 GPT, xhigh)** 교차검증.
아래는 통합 findings → 적용한 수정 → 미해결 결정. (원 docs는 본 노트 반영해 수정함.)

## 0. 수렴 판정
4 lens가 **강하게 수렴**: (a) 비교가 구조상 near-tie 위험, (b) 충실도 함정 다수, (c) 비교축은 per-class %여야, (d) 사실 오류 2건(앵커 순서·band 수).
**Codex(최신 GPT, xhigh) 완료 → 집합 수렴**: 동일 대형 리스크 재확인(약한 비교, 앵커 y-major, 후기통합·실질 직렬, deps 미설치, 오라클 비현실, dedup, 클래스 인코딩). **처방 1건 발산**=약한 비교 해결책(§8). Codex 신규 must-fix 3건도 §8.

---

## 1. 즉시 적용한 사실 수정 (verified errors)

1. **YOLO-seg 앵커 순서 = y-major** (`OnnxROIRecognizer.h:147-158`의 `for stride{ for y{ for x }}`). 기존 docs "x-major" → **수정**. Stream B는 "실행됨"이 아니라 **실제 추론 → 비어있지 않은 BEEF label_map**을 종료 게이트로.
2. **band 수는 가변** — 날짜 폴더 파일수 10/20/30/90/160(=position수×band수). 기존 "44=4 pos×11 band, ~3,060 captures" → **수정**(capture별 band 수 상이, capture = `(device,meat,cut,date,posIdx)` 그룹). **[§9 정정: beef striploin도 8–16 가변·일부 620 포함, capture ~2.8k–3.0k 동적]**
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

- **near-tie 위험**: 두 방식이 동일 cascade를 공유하면 차이가 ROI에서만 발생 → 산점도가 y=x에 붙음. (게이트 탈락 NOT_DONE 대량 → per-class % 델타가 거의 0일 수 있음.)
  - ~~F-B5 승격~~ → **REJECTED**(2차 리뷰): 사용자 제약(AI=ROI 전용, 도넨스=규칙) 위반 + 라벨 0개라 학습 불가.
  - **확정**: AI **세그멘테이션 오버레이 + ROI-diff 가시화 hero**(ONNX 윤곽 vs Rule 윤곽 + 대칭차 + ROI 면적/IoU 델타). per-class % 점수는 보조("같은 규칙·더 깨끗한 ROI = 무튜닝 AI 도입"). 정직·충실·즉시 실행.
- **데모 내러티브(60초)**: "11파장 → AI 세그멘테이션이 스테이크를 인식 → 픽셀 도넨스 채점 → 같은 스테이크를 규칙으로 채점 → **불일치 지점**(델타/산점도) → C++ 엔진 대비 beef striploin 검증". → **C++ 오라클 대신 소스 정적 대조로 '검증' 주장**(아래 5).
- **차트 우선순위 하향**: 날짜별/메뉴별 추이는 정답 없어 검증 불가·임팩트 약 → "맥락"으로, 절약분을 단일 capture 비교/오버레이 폴리시에 투자.

## 5. DevEx — 사전설정 정정

- **현 상태(검증)**: `requirements.txt` 없음, `duckdb/pandas/streamlit/plotly/statsmodels` 미설치, `onnxruntime-linux-x64-*/` 미ignore(→ 본 노트로 .gitignore 보강 완료). model 로드 ~0.46s.
- **C++ 오라클(§7-7) 강등 P0→P2**: `../bh_chef...`는 Qt/CMake UI 바이너리(serial/camera 의존) — 90분 내 헤드리스 채점 덤프 비현실적. **대체**: 스코어링 상수·LED표를 **소스에서 정적 추출**(이미 LED표 확보), 편차 문서화(NF-1).
- **대시보드 read 가드**: DB 없음/락 시 "파이프라인 먼저 실행" 빈 상태. 실행 순서 = 파이프라인 → 대시보드(문서화).
- **고정 사전설정 명령**(devex 제공): `.venv/bin/pip install duckdb pandas streamlit plotly` (**§9: statsmodels 제외**) → `pip freeze > requirements.txt` → .gitignore 보강 → scaffold → 실제 fixture 복사(`260612_office_backup/206/beef/striploin/251016` 10파일=1pos) + dedup-seam 합성 fixture → LED표 **16행** 박제 → DB init 라운드트립 → model 로드 확인.

## 6. 디자인/UX — 비교 가독성 (적용 지침)

- **3분할 = 공유 범례 1개 + 각 패널 동일 100% 누적바**(픽셀 아닌 막대길이로 비교). 팔레트는 `SOURCE_ANALYSIS §6` 정본 hex 단일소스.
- **비교축은 항상 per-class %**(공유 계약). `maillard_score`는 **단일방식 뷰에서만**, 라벨 `Maillard(AI weights)`/`(rule weights)`, **동일축 공동플롯 금지**.
- 날짜/메뉴: **class=색, method=선스타일(ai 실선/cond 점선)**, 기본 1개 클래스(burnt) 라디오로 6계열 난잡 회피. method 색은 전역 고정.
- **agreement 정량화**: 산점도에 MAE(pts) 대형 캡션 + 점을 signed Δ 발산색으로(체계적 편향 가시). Bland-Altman은 P2 유지.
- **first-screen hero = 단일 ROI-diff overlap-map(PRIMARY) + IoU/Dice/area-delta KPI strip(SECONDARY)**. **3분할은 hero 아님 → fold 아래 expander(TERTIARY)**. [§10 3차 리뷰에서 정정 — 기존 "3분할이 first-screen hero"는 2-hero 모순이라 폐기. 상세 `DESIGN_SPEC §6`.]
- hero 비주얼: **3영역 overlap-map(Both 그레이/ONNX-only cyan 실선/Rule-only magenta 점선 해치) + 평문 IoU 캡션** — "어디서 두 ROI가 갈리는가"를 직접 가시. (DESIGN_SPEC §7.)

## 7. 결정 (확정)
- [x] **하이브리드 채택** — 도넨스 cascade 통일(**라이브 beef, 직접 read 확정**) + **"ONNX ROI vs Rule ROI"** 정직 개명(P0), 세그멘테이션 오버레이 + ROI-diff hero. **F-B5 컷**(사용자 제약: AI=ROI 전용). [2차 리뷰 §9]
- [x] Codex 교차검증 = 집합 수렴(§0, §8).
- [ ] C++ 오라클: 정적 추출로 대체 확정(권고) vs 시간 남으면 1건 시도.

---

## 8. Codex 교차검증 reconcile (최신 GPT, xhigh)

**수렴(양측 동일)**: 약한 비교/오버스테이트, 앵커 y-major, Phase-2 과소·실질 직렬→Phase-0 end-to-end 1건 먼저, deps 미설치, C++ 오라클 비현실(Qt GUI·capture CLI 없음 `main.cc:21`)→정적추출, dedup, 클래스 인코딩 Phase-0 확정.

**발산 1건 — 약한 비교의 해결책 (해소됨: 사용자 제약, 2차 리뷰)**:
- **CEO(A)**: F-B5 학습형 도넨스 → **REJECTED**(AI=ROI 전용 제약 위반 + 라벨 0개).
- **Codex(B) 채택**: 도넨스 동일 cascade 통일 + **"ONNX ROI vs Rule ROI"** 개명 → 차이는 ROI 분할 품질, 오버레이·ROI-diff로 가시. **P0 출하**.

**Codex 신규 must-fix (문서 반영)**:
1. **ScoreResult에 오버레이 맵 부재** — Stream D는 roi_mask/class_map/도넨스맵 필요 → ScoreResult(또는 형제)에 렌더용 맵/경로 포함, Phase-0 동결(아니면 D가 A/B에 직렬 의존).
2. **726-파일 동일 복사 트리 + 244 cross-format 충돌**, 실제 capture **~2.8k–3.0k 그룹**(§9 정정: 3,044는 한 그루핑 추정치, 디스크 재검증 2,817~2,961 → 스캔 시 동적 계산) → `capture_id`=device/meat/cut/date/posIdx 결정적, 복사 트리 collapse, band당 PNG 우선.
3. **cascade 변형 불일치** — 라이브 AI는 `beef_strip_loin/ComponentRecognizer_BeefStripLoin_CharBroiler`, 조건문 SPEC은 `_america` 포팅. **옵션 B면 양쪽 동일(라이브 beef) cascade**. 빌드 전 라이브 파일 직접 read 필수.
4. **3분할(P0)인데 capture 선택(F-D3) P1** 모순 → 최소 선택 **P0** 승격.
- 참고: 라이브 recognizer가 8-slot 배열에 index 8 기입(`live recognizer:31`) — 소스 버그, 포팅 시 방어.

**판정**: 집합 수렴, 처방 1건 발산(A/B) → **2차 리뷰에서 사용자 제약으로 해소**(B 출하, A 컷). 정직 개명 유지.

---

## 9. 2차 리뷰 — ROI-only 제약 재검증 (Claude 5-lens + Codex xhigh, 완전 수렴)

사용자 제약 재확인: **AI = ROI/세그멘테이션 전용, 도넨스 컴포넌트 = 규칙(그대로), `Merge_Main` 없음**. 라이브 sensing 흐름 `getOnnxInferenceOutput`(`BaseRobotTaskSensing.h:93`, `mainwindow.cpp:1747`) 직접 검증. Claude 5-agent 소스 검증 + 5-lens(eng/ceo/devex/design/code) + Codex(xhigh)가 **블로커 집합·랭킹·제품전략·실현가능성에 완전 수렴**(Codex가 라이브 cascade 임계를 **독립적으로 문자 단위 동일** 도출 — 포팅 리스크 사실상 소거).

**확정 수정(소스 직접 read, 본 docs 반영 완료)**:
1. **F-B5 컷** — 제약 위반 + 라벨 0개. near-tie는 세그멘테이션 + ROI-diff hero로.
2. **도넨스 cascade = 라이브 beef 그대로**(`ComponentRecognizer_BeefStripLoin_CharBroiler.h:112-158`). 기존 `SCORING_SPEC §3`은 `_america` 오포팅 → 교체(게이트 410/440, 살코기+지방 2 proper분기, 460·800 미사용).
3. **rule-ROI = 라이브 `recognizeROI` seed + 모폴로지 근사**(실 12-stage GridBasedAlgorithm은 비범위). "근사" 라벨 필수, 트레이존 크롭만이라도 포팅(서사 역전 방지).
4. **band_count 가변(8–16)** — "beef=10" 반증. capture 수 ~2.8k–3.0k 동적 계산.
5. **LED 16행 전수** 박제(`src/model/PropertiesDatabase.h:113-128`).

**신규 발견(Phase 0/구현 반영 대상)**:
- **NOT_DONE 버킷**: proper+slightly+burnt < 100 → 커널/ScoreResult/스택바 4-way(+`pct_not_done`).
- **누락밴드→0 게이트 함정**: 410/440 누락 0대체 시 게이트 전 픽셀 통과 → 점수 폭증. 스킵/에러.
- **per-class % 델타 ≈ 0 위험**: hero = ROI 면적/IoU 델타 + ROI-diff 시각화(점수 델타 보조).
- **per-menu offset 채널**: beef 3채널 vs **pork burnt만**(`...PorkBelly_Charcoal...:408-415`). 커널이 정책 read.
- **maillard 3변형 상이**(AI 0.7/1.5/3.0 · 라이브beef 1.0/1.0/3.0 · _america 0.5/1.0/4.0) → 비교축 per-class %, 단일 동일식(0.7/1.5/3.0).
- **faithful_triple_offset 제거**(MVP 단일 offset).
- **HSV 휴램프 vs 평면 hex**: 라이브 `makeHueOfHSV`는 휴램프, OnnxVisualization은 평면 → 가독성용 평면 hex 채택(표현 선택 명기).
- **DevEx**: statsmodels 드롭(소비자 없음), all-JPEG fixture 보강(dedup seam), Phase-0 정확성 스모크, Stream A 임계경로 재배분.

**실현가능성(양측 수렴)**: 90분 **viable**, 단 Phase 0 필수 — (a) 라이브 `.h` cascade 전사, (b) label 인코딩 확정, (c) end-to-end beef 정확성 스모크.

---

## 10. 3차 리뷰 — UX/UI/디자인 (Claude 6-lens 동적 워크플로 + Codex xhigh, 집합 완전수렴)

사용자 요청으로 **디자인 차원** 집중 리뷰. **Claude**: 동적 Workflow가 웹 리서치 6주제(Streamlit 테마/이미지비교 컴포넌트/세그멘테이션 오버레이 UX/CVD 팔레트/모델비교 UX/데모 스토리텔링) → 6 렌즈(IA·visual·states/a11y·comparison-trust·features·devex) → 90분 타당성 검증 → 종합(14 agents). **Codex(gpt-5.5, xhigh)**: 동일 5 docs 독립 리뷰(WCAG 대비 Python 계산 + 실 URL 인용). **두 엔진은 결과를 못 보고 작업** → 수렴이 신뢰 신호.

**렌즈 평점(Claude)**: IA 5/10 · **visual 3/10** · **states/a11y 3/10** · comparison-trust 6/10 · features 6/10 · devex 6/10. **Codex 종합 8/10.** → 정확성은 탄탄, **visual craft + 상태/접근성이 구멍**(양측 동일 진단).

**집합 완전수렴(양측 독립 동일 도출)**:
1. **ROI-diff가 옳은 hero** + 첫 화면은 **단일 hero + KPI scorecard**, 3분할은 fold 아래.
2. **정확도→일치도(agreement) 리프레임**: 정답 0개라 "더 정확/낫다"는 방어 불가. 델타는 sign-only 중립색.
3. **green/red doneness 색맹 위험** → CVD-safe 명도순 램프 + 글자칩 + pattern_shape(MASK 오버레이만 C++ 정본).
4. **NOT_DONE 정직 처리**: 분모 유지, 그레이 후퇴, `>60%` 배너.
5. **90분은 규율 P0에서만 성립**(polish 추가가 아니라 교체). **Stream D가 숨은 2차 임계경로**(실슬랙 ~7m); Phase-0가 렌더 계약(roi_mask/class_map/경로/paired-쿼리) 동결 필수.
6. 누락 상태(no-DB/empty/loading/error/partial) → 상태 매트릭스.

**발산(랭킹/취향 only — judge 라운드 불필요)**:
- **정확 팔레트 hex**: Codex(NOT_DONE #0072B2 등, WCAG 대비 검증) vs Claude(명도순 + NOT_DONE 그레이 후퇴). → **Claude 구조 채택**(순서형 데이터는 명도순이 더 강한 원칙), Codex hex는 빌드 시 대비 대조용.
- **Demo Mode / 상태 매트릭스 P0 vs P1**: Codex P0 / Claude feasibility P1. → **Claude 채택**(feasibility agent가 Stream D ~7m 슬랙을 명시 모델링, maximal set은 `ninetyMinHolds:false`). crash-방지 subset(no-DB·no-ROI 가드)만 P0.

**확정 결정(사용자)**: 액센트 **Ember #E8602C** · hero **3영역 overlap-map**(wipe-slider 컷) · 스코프 **규율 P0 + 60분 cut-line**.

**산출**: `DESIGN_SPEC.md` 신설(12절, Phase-0 동결) + PLAN/FEATURES_SPEC/SCORING_SPEC 정합 수정 + 본 §10. hero 목업 1장 생성(gstack 디자이너, Ember).

**판정**: 집합 완전수렴, 발산은 취향/랭킹뿐 → **고신뢰 커밋 가능**.
