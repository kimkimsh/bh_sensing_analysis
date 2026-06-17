# bh_sensing_analysis — 기획안 (Hackathon Plan)

> 숯불 조리(charBroiler) 멀티스펙트럼 센싱 이미지에서 고기 굽기 점수(마이야르/슬라이틀리 번트/번트)를
> **AI(ONNX) 방식**과 **조건문(규칙) 방식** 두 가지로 산출하고, **날짜별·메뉴별 시각화**와
> **두 방식의 시각·수치 비교**를 제공하는 로컬 분석 도구.
>
> 구현은 **dynamic workflow 병렬 실행**을 가정한 90분 해커톤 플랜.
> 본 문서는 의사결정·아키텍처·빌드플랜을, `SOURCE_ANALYSIS.md`는 검증된 원본 사실을,
> `SCORING_SPEC.md`는 포팅할 정확한 알고리즘을 담는다.

---

## 1. 목표와 범위

### 만들 것
- `data/` 폴더(스펙트럼 이미지)를 넣으면 → 각 capture의 굽기 점수를 **두 방식**으로 산출 → **DuckDB**에 저장
  → **Streamlit** 대시보드에서 **날짜별/메뉴별 차트** + **원본 | AI 오버레이 | 조건문 오버레이 3분할 비교** + **AI vs 조건문 수치 비교**.

### 두 가지 "센싱 방식"의 정의 (확정)
원본 소스에는 픽셀단위 도넨스 ONNX 모델(`Merge_Main_Model_241105.onnx`)이 있으나 **우리 `ai_model/`에는 없음**
(보유: `meatSegNet_best.onnx` + 외부가중치 `.onnx.data`, `exlight_remover_e32_int8.onnx`, 그리고 ORT 네이티브 런타임 `onnxruntime-linux-x64-1.23.2`).
사용자가 지목한 `onnxruntime-linux-x64-1.23.2`는 **모델이 아니라 ONNX Runtime 엔진**(`libonnxruntime.so`)이다.

**확정**: 도넨스 cascade를 **양쪽 통일**(라이브 beef 규칙, `SCORING_SPEC §3`)하고 정직하게 **"ONNX ROI vs Rule ROI"** 로 명명(차이 = **ROI 분할 품질뿐**). AI는 ROI/세그멘테이션 전용·도넨스는 규칙 → **학습형 도넨스(구 F-B5)는 사용자 제약상 컷**(라벨 0개라 학습 불가이기도). **세그멘테이션 오버레이 + ROI 불일치 가시화가 hero**(near-tie라 점수 델타는 보조).

| 방식 | 파이프라인 | ONNX 사용 |
|------|-----------|-----------|
| **ONNX ROI** (AI) | meatSegNet(ONNX, 5채널) → 고기 인스턴스/ROI 분할 → ROI 내부 도넨스(**통일 cascade**) → 점수 | ✅ meatSegNet |
| **Rule ROI** (조건문) | 규칙기반 ROI(모폴로지 근사) → **동일 cascade** → 점수 | ❌ 순수 numpy |

- 두 방식은 **동일한 출력 계약(`ScoreResult`)** 을 생성한다. 차이는 **ROI 산출 주체뿐**(ONNX 분할 vs 규칙 근사) — 도넨스 cascade는 동일. → **사과 대 사과 비교**가 성립.
- **비교 데모는 beef striploin에 집중**한다(이유: §8 리스크). 다른 메뉴는 조건문 위주 + 클래스별 % 표시.

### 비범위 (v1 컷 — §8)
exlight 복원, 전 메뉴 충실 포팅, 픽셀정확 ROI 패리티(GridBasedAlgorithm), per-instance 드릴다운, 오버레이 장식(범례/박스/그리드).

---

## 2. 추천 스택 (사용자 위임 → 결정)

| 레이어 | 선택 | 한 줄 근거 |
|--------|------|-----------|
| 언어 | **Python 3.12** (`.venv`) | 단일 언어, 빌드툴체인 불필요, 라이브러리 즉시 |
| 추론 | **onnxruntime 1.26 (CPU)** | meatSegNet 외부 `.onnx.data` 경로 자동 해석 — **검증됨(0.36s 로드)** |
| 영상 | **opencv-python-headless 4.13** | grayscale IO·morphology·connectedComponents·resize·GaussianBlur |
| 수치 | **numpy 2.4** | 벡터화된 스펙트럼 규칙 / YOLO-seg 후처리 (int32/float로 uint8 오버플로 회피) |
| DB | **DuckDB** | GROUP BY date/menu 분석 워크로드에 SQLite 대비 10–200x; pandas/Arrow 호환 |
| UI | **Streamlit** | `st.columns(3)` 3분할 비교·`@st.cache_data` 메모이즈·사이드바 필터가 공짜 |
| 차트 | **Plotly Express** | 라인(날짜)·그룹바(메뉴)·산점도(AI vs 조건문) — matplotlib/Bland-Altman 컷(§8) |
| 디자인 | **config.toml 테마(CSS 금지)** | 다크 "Spectral Lab" + Ember 액센트 + CVD-safe 차트 팔레트 → `DESIGN_SPEC.md`(Phase-0 동결) |

검증된 환경(직접 확인): **uv 관리 `.venv`(Python 3.12, `pyproject.toml` + `uv.lock`)**. 8개 deps 전부 핀 설치(numpy/onnx/onnxruntime/cv2/duckdb/pandas/streamlit 1.58/plotly), statsmodels·matplotlib 제외(§8). meatSegNet 로드 **0.36s 재검증**.

---

## 3. 데이터 & 모델 사실 (직접 검증, 상세는 SOURCE_ANALYSIS.md)

- **데이터셋**: `data/<backup>/<deviceId 206|250>/<meat>/<cut>/<YYMMDD>/<frame>.png|jpeg`.
  총 **~33,700 프레임**, grayscale 480×640 uint8. **라벨/마스크/정답 파일 0개**(정답 없음 → §8 충실도 게이트 필요).
- **1 capture = 동일 `(device,meat,cut,date,posIdx)` 그룹**의 파장 스택. **band 수 capture별 가변(8–16)** — beef striploin도 날짜별 8~16밴드(일부 capture는 620_630_625 포함). `band_count`는 **capture별 동적 산출**(고정값/메뉴별 고정 금지). 전체 ~33.7k 프레임 ≈ **~2.8k–3.0k capture**(스캔 시 결정적 계산; copy-tree collapse·cross-format 244 dedup 반영).
- **파일명 문법**: `ver2_charbroiler_calibrated_<meat>_<cut>_<YYMMDD>_<posIdx>_<wMin>_<wMax>_<wPeak>.<ext>`.
  band 키는 **(min,max,peak) 튜플**(peak 충돌: `720_740_740`=led10 vs `720_750_730`=led9).
- **파장↔LED**: 410=led0, 440=led1, 460=led2, 520=led4, 585=led5, 650=led8, 720=led10, 800=led11, 930=led14 (+pork 620, +840=led12).
- **meatSegNet (검증)**: input `('input',[batch,5,480,640],float)` = led 2,4,8,10,12(=460/520/650/720/840) /255, 누락 시 0.
  output `preds[batch,6300,41]` + `protos[batch,32,120,160]` → YOLOv8-seg(인스턴스 분할, **고기 종류** 4클래스). **도넨스 아님.**
- **점수 계약**(두 방식 공유): `pct_proper(Deep Maillard) / pct_slightly_burnt(Slightly Charred) / pct_burnt(Carbonized)` = ROI 내 클래스 픽셀 % ,
  보정 offset `burnt-3 / slightly-1.5 / proper-5`(0 floor), 합성 점수 `maillard_score`.

> ⚠️ **충실도 함정 2개**: (a) AI 글로벌 점수는 **BEEF 인스턴스만** 합산(`OnnxInferenceOutput.h:67`) → 비-beef는 0.
> (b) 합성 점수 가중치가 다름 — AI `proper*0.7+slightly*1.5+burnt*3.0` vs 조건문 `proper*0.5+slightly*1.0+burnt*4.0`.
> → **대시보드 기본 비교는 클래스별 %로**, 합성 점수는 방식별 라벨을 분명히 표기.

---

## 4. 아키텍처

```
ingest ─▶ score(ai | conditional) ─▶ persist(DuckDB) ─▶ aggregate ─▶ visualize/compare
```

`bh_score/` (src 레이아웃), 1 클래스 = 1 책임, 컨트롤러는 오케스트레이션만.

```
bh_sensing_analysis/
├─ bh_score/
│  ├─ bands.py            # LedBandMap: ledId ↔ (min,max,peak) 정본 + 메뉴 규칙테이블 스켈레톤  [FROZEN]
│  ├─ ingest/
│  │  ├─ types.py         # CaptureGroup, SpectralCube 인터페이스 (band()/bandByLed()/has())  [FROZEN]
│  │  ├─ scanner.py       # DatasetScanner: FNAME_RE 파싱, " (copy)" strip, capture 그룹핑
│  │  └─ cube.py          # SpectralCube: lazy cv2 grayscale 로드, PNG-우선 dedup
│  ├─ scoring/
│  │  ├─ result.py        # ScoreResult / InstanceResult dataclass (공유 출력 계약)            [FROZEN]
│  │  ├─ base.py          # Scorer(ABC): score(cube, menu) -> ScoreResult                      [FROZEN]
│  │  ├─ kernel.py        # DonenessKernel: 두 방식 공유 (퍼센트·offset·maillard)
│  │  ├─ conditional.py   # ConditionalScorer: 규칙 ROI + 스펙트럼 cascade
│  │  ├─ ai.py            # AiScorer: meatSegNet label_map → kernel(인스턴스) → ScoreResult
│  │  └─ grades.py        # GradeLadder: {menu: (score_field, ladder)} 데이터구동
│  ├─ segment/
│  │  ├─ meatsegnet.py    # MeatSegNet: 5ch 전처리 + YOLO-seg 후처리 → label_map(0..4)
│  │  └─ exlight.py       # (옵션, 기본 off)
│  ├─ persist/
│  │  ├─ schema.sql       # captures / scores / instances
│  │  ├─ repository.py    # ScoreRepository: DuckDB writer (단일 writer)
│  │  └─ queries.py       # AggregationQueries: by_date / by_menu / ai_vs_cond / paired
│  └─ viz/
│     ├─ palette.py       # [FROZEN] MASK(C++정본)/CHART(CVD-safe)/ROI_DIFF 3색공간 상수 — DESIGN_SPEC §3
│     ├─ overlay.py       # OverlayRenderer: MASK 팔레트 포팅 + ROI-diff overlap-map hero(3영역+윤곽)
│     └─ charts.py        # Plotly 라인·바·산점도 (chartCategoricalColors 상속, per-figure color 0)
├─ pyproject.toml         # [FROZEN] uv 프로젝트(deps 핀, package=false) — uv.lock이 재현 source of truth
├─ uv.lock / .python-version # uv 잠금파일 + Python 3.12 핀
├─ .streamlit/config.toml # [FROZEN] 다크 Ember 테마 + CVD chartCategoricalColors + toolbarMode (DESIGN_SPEC §5)
├─ cli/run_pipeline.py    # 오케스트레이터: scan → 두 scorer → write + 오버레이 캐시 (--limit/--methods)
├─ app/dashboard.py       # Streamlit reader (read_only DuckDB) — 단일-hero Compare/Trends/Explore 3탭
├─ run.sh / demo.sh       # [FROZEN] 골든패스 1-커맨드(파이프라인→대시보드) / 데모 capture 전용
├─ docs/plan/DEMO_SCRIPT.md # [FROZEN] 6-beat 60초 골든패스 (Phase-2 버그수정은 이 경로만)
├─ tests/fixtures/        # beef 1 + pork 1 capture (오프라인 테스트용)
└─ artifacts/overlays/    # 캐시된 오버레이 PNG
```

핵심 설계: **두 scorer 모두 `DonenessKernel`을 거쳐 퍼센트/offset/점수를 계산** → 변하는 건 *픽셀 클래스 판정 + ROI 소스*뿐 → 비교 공정성 보장.

---

## 5. DB 스키마 (DuckDB, `scores.duckdb`)

```sql
-- 물리 capture 1행
CREATE TABLE captures (
  capture_id BIGINT PRIMARY KEY,   -- 그룹키 해시
  device_id INTEGER, meat VARCHAR, cut VARCHAR,
  menu VARCHAR,                    -- meat || '/' || cut
  capture_date DATE,               -- 2000+YY
  capture_index INTEGER, band_count INTEGER, frame_dir VARCHAR
);
-- capture × method 1행 (대시보드 집계의 주테이블)
CREATE TABLE scores (
  capture_id BIGINT, method VARCHAR,        -- 'ai' | 'conditional'
  menu VARCHAR, capture_date DATE,          -- GROUP BY 가속용 비정규화
  pixels_roi INTEGER,
  pct_proper DOUBLE, pct_slightly_burnt DOUBLE, pct_burnt DOUBLE, pct_burnt_raw DOUBLE,
  cooking_score DOUBLE, maillard_score DOUBLE,
  grade INTEGER, grade_label VARCHAR,       -- grade 0 = 완료(COMPLETE)
  instance_count INTEGER,
  overlay_path VARCHAR, mono_path VARCHAR,  -- 캐시된 오버레이 / 원본(ch3=led10) PNG
  scored_at TIMESTAMP DEFAULT now(),
  PRIMARY KEY (capture_id, method)
);
-- (옵션) AI per-instance 드릴다운 — v1 컷 후보
CREATE TABLE instances ( capture_id BIGINT, method VARCHAR, instance_id INTEGER,
  class_id INTEGER, class_name VARCHAR, pixel_count INTEGER,
  bbox_x INTEGER, bbox_y INTEGER, bbox_w INTEGER, bbox_h INTEGER,
  pct_proper DOUBLE, pct_slightly_burnt DOUBLE, pct_burnt DOUBLE, maillard_score DOUBLE );
```
대표 쿼리(모두 100ms 이하): `BY DATE`/`BY MENU` 평균, `FILTER(WHERE method=...)` 차분, `JOIN USING(capture_id)` paired(산점도/Bland-Altman). writer는 파이프라인 1프로세스, reader는 Streamlit `read_only`(`@st.cache_resource`).

---

## 6. 90분 빌드 플랜 — dynamic workflow 매핑

> 구현은 dynamic **Workflow**로: **Phase 0**(1 agent, 계약 동결) → **Phase 1**(`parallel()`로 4 stream 동시) → **Phase 2**(1 agent, 통합+데모).
> 모든 stream은 Phase 0의 **동결 인터페이스 + 커밋된 stub/fixture**에만 의존 → 진짜 병렬(서로 대기 없음).

### PHASE 0 — 계약 동결 (0–10분, BLOCKING, 1 agent)
산출(동결): `scoring/result.py`(ScoreResult **+pct_not_done**), `scoring/base.py`(Scorer ABC), `ingest/types.py`(CaptureGroup/SpectralCube), `bands.py`(LedBandMap **16행** + 메뉴 규칙·**offset 채널** 스켈레톤), `persist/schema.sql` + repo stub, `tests/fixtures/`(beef 1 + **dedup-seam 합성 1**), 핀 고정 `requirements.txt`(**statsmodels 제외**), **`viz/palette.py`(MASK/CHART/ROI_DIFF 3색공간 — DESIGN_SPEC §3, Stream B/D 공유)**, **렌더 계약 동결(`roi_mask`/`class_map`/`overlay_path`/`mono_path` + paired-score 쿼리 셰이프)** — Stream D가 A/B 미동결 산출물 대기 차단(Codex+Claude 수렴). `.streamlit/config.toml`·`DEMO_SCRIPT.md`·`run.sh`/`demo.sh`는 §7 **사전커밋(빌드 0분)**.
**BLOCKING 추가(코딩 전 차단)**:
1. **DonenessKernel을 라이브 `.h`에서 직접 전사** — `beef_strip_loin/ComponentRecognizer_BeefStripLoin_CharBroiler.h:112-158`의 5분기 cascade(게이트 + 살코기/지방 2 proper분기)와 **NOT_DONE 버킷**을 **실제 함수로 동결**(stub 아님; §3가 아니라 `.h`에서). 합성 (roi_mask,class_map) 골든 단위테스트(NOT_DONE 포함) 통과가 게이트.
2. **label_map 클래스 인코딩 확정**: beef fixture 1장 실제 meatSegNet 추론 → 정수↔클래스 맵 read → `result.py` 상수 동결(beef-only 글로벌이 의존). 로드 ~0.36s, 2분.
3. **동일 입력 대칭성 테스트**: 동일 (roi_mask,class_map)를 두 scorer 글로벌 경로에 넣어 pct가 **bit-동일** assert(가짜 델타 차단).
4. **agreement 빈-ROI 가드 테스트**: 빈 rule-ROI vs 비어있지않은 ONNX-ROI → IoU/Dice가 `"No overlapping ROI"` 센티넬 반환(**NaN/inf 금지**, 무대 크래시 차단). 수식·상수는 `SCORING_SPEC §7`(`STRONG_AGREEMENT_IOU=0.90`).

### PHASE 1 — 4 독립 스트림 (8–70분, 병렬 subagent burst)
디스패치 모드: **단일턴 병렬 subagent**(교차턴 상태/실시간 가시성 불필요 → 팀원보다 저렴). `worktree` 격리로 파일 충돌 방지.

| Stream | 범위 | 산출 | 노출 계약 |
|--------|------|------|-----------|
| **A** 수집+커널+조건문 (~55m) | 스캐너/큐브/공유커널/조건문scorer/등급 | `ingest/scanner.py`, `ingest/cube.py`, `scoring/kernel.py`, `scoring/conditional.py`, `scoring/grades.py` | `DonenessKernel`, `ConditionalScorer` |
| **B** AI 분할+AI scorer (~55m) | meatSegNet 래퍼 + YOLO-seg 후처리 + AI scorer | `segment/meatsegnet.py`, `scoring/ai.py` | `AiScorer`, label_map+도넨스맵 |
| **C** 영속+집계 (~35m, 조기완료) | DuckDB writer + 집계쿼리 | `persist/repository.py`, `persist/queries.py` | `ScoreRepository`, `AggregationQueries` |
| **D** 시각화+Streamlit (~55m, **숨은 2차 임계경로·실슬랙 ~7m**) | overlap-map hero + agreement scorecard + 단일-hero 3탭 IA + 사이드바 + missing/no-ROI 가드 (**P0 ~50m**); 카드·full state matrix·demo mode·band strip은 P1 | `viz/overlay.py`, `viz/charts.py`, `app/dashboard.py` (`viz/palette.py`·`config.toml`은 Phase-0 동결) | `roi_diff_hero`, `agreement_scorecard`, `build_charts`, dashboard |

각 stream은 fixture/synthetic으로 **오프라인 테스트**(A·B는 실제 fixture, C·D는 합성 행). B의 커널 호출은 Phase 0의 **실제 DonenessKernel**로 충족.
> **재배분(F-B5 컷 반영)**: Stream A 과중(스캐너+큐브+커널+조건문+rule-ROI+등급), B는 경량화(세그멘테이션 후처리 + 동일 커널 호출)되어 **A가 임계경로**. `grades.py`(F-B4,P1)·rule-ROI 모폴로지는 조기완료 C/B 후미로 이동. A의 **커널+라이브 cascade는 Phase-0.5 마이크로게이트**(B·smoke·C 핸드오프가 모두 의존).
> **Stream D 예산 규율(DESIGN_SPEC §12)**: D는 ~55m 작업이 ~62분 창에서 55분 시작 → **실슬랙 ~7m**. 따라서 최고 레버리지(config.toml·palette.py·DEMO_SCRIPT)는 **Phase-0 사전커밋(0분)**, 나머지는 이미 계획된 위젯의 기계적 재배치. **P0 순-신규 ~50m**(hero 20m가 binding). **60분 cut-line**: 60분에 D 미완 → hero를 `st.image` 3분할 + IoU 캡션으로 강등(overlap-map 합성·슬라이더·pixel-probe drop) → 90분 보장.

### PHASE 2 — 통합 + 데모 (70–90분, 1 agent)
`cli/run_pipeline.py` 배선(scan→두 scorer→write+오버레이 캐시, `--limit/--methods`) → **`--limit` beef/striploin+pork/belly 스모크**로 `scores.duckdb` 채우고 오버레이 1쌍 육안 확인 → seam 버그(커널 경계 dtype, band 누락 fallback) 수정 → 대시보드 headless 기동, 차트/3분할/비교 확인 → README.
**정규 실행 순서(문서화·DESIGN_SPEC §8/§12)**: `bash run.sh` = `python cli/run_pipeline.py --limit 20 --methods both` **THEN** `streamlit run app/dashboard.py --server.headless true`. **Phase-2 버그수정은 `DEMO_SCRIPT` 골든패스만**(전체가 아님). 대시보드는 빈/없는 DB에서도 크래시 없이(missing-DB 가드) 기동해야 함.

> ⚠️ Phase 2 리스크(크리틱): 통합자 1명·20분·미검증 seam. **완화**: Phase 0 트레이서불릿(실제 beef fixture→두 scorer **실제 커널**→DuckDB write→read_only→by_menu→오버레이 PNG)을 8분차에; **추가로 정확성 스모크**(실제 커널이 meatSegNet ROI와 rule ROI 양쪽에서 pct_burnt가 **다르고** NaN/0 아님 assert)를 **Stream A 종료조건**으로. Phase 1 각 stream이 자기 fixture 테스트 통과를 종료조건으로.

---

## 7. 사전 설정 (지금 미리 가능 — 사용자 승인됨)

**이미 검증(직접 확인, 재실행 불필요)**
- **uv 관리 `.venv`(Python 3.12, uv-managed CPython)** — `pyproject.toml`+`uv.lock`, 8 deps 핀 설치(onnxruntime 1.26 / onnx 1.21 / numpy 2.4.6 / cv2 4.13 / duckdb 1.5 / pandas 3.0 / streamlit 1.58 / plotly 6.8). 클린 env(무관 패키지 0).
- meatSegNet 로드 0.36s, IO=`input[ ,5,480,640]`→`preds[ ,6300,41]`,`protos[ ,32,120,160]`(외부 `.onnx.data` 자동 해석).

**남은 단계**
1. **uv 환경 구성**: `pyproject.toml`(deps 핀, `[tool.uv] package=false`) → `uv sync`로 클린 `.venv`(Python 3.12) 생성. **검증됨**: 8 deps 설치 + meatSegNet 로드 **0.36s 재검증**(`input[,5,480,640]`→`preds[,6300,41]`,`protos[,32,120,160]`). (**statsmodels·matplotlib 제외** — §8)
2. `uv.lock` 커밋(재현 source of truth) + `requirements.txt`는 pip-fallback 미러로 유지. 의존성 추가 시 `uv add <pkg>` → `uv.lock` 갱신.
3. 디렉토리 스캐폴드(위 트리) + 각 패키지 `__init__.py`. (`data/`,`ai_model/`,`.venv/`는 .gitignore — 유지)
4. fixtures: beef 1 capture(`260612_office_backup/206/beef/striploin/251016`, 10밴드 JPEG=AI 5ch 게이트 가능) **+ dedup-seam 합성 capture**(PNG+JPEG 동일밴드 쌍 · `999_999_999` 센티넬 · ` (copy)` 트리)를 경로 구조 유지로 `tests/fixtures/`에 → PNG우선/센티넬드롭/복사트리 collapse를 8분 스모크가 **실제로** 커버(beef fixture 단독은 all-JPEG·단일pos라 이 seam 미검증).
5. DB init 스모크: `scores.duckdb` 생성 → `schema.sql` 적용 → 합성 1행 insert/select → `read_only` 재오픈 확인.
6. **LED↔band 정본표 확정**: `src/model/PropertiesDatabase.h:113-128`에서 ledId↔(min,max,peak) **16행 전수**를 `bands.py`에 박제. 라이브 cascade가 읽는 9밴드(410/440/520=led4/585/650/720=led10/930 + 로드되나 미사용 460/800) 명시 — 440은 원본 OOB 슬롯이므로 키 접근으로 정상 포함.
7. **충실도 대조(P2로 강등)**: C++ 바이너리는 Qt/하드웨어 의존 UI라 90분 내 헤드리스 채점 덤프 비현실적 → **소스 정적 추출**(스코어 상수·LED표, 이미 확보; `PropertiesDatabase.h:113-125`)로 대조하고 편차 문서화. 시간 남으면 바이너리 1건 시도.
8. `onnxruntime-linux-x64-1.23.2/`는 .gitignore에 추가(22MB 다운로드 산출물, Python은 pip 휠 사용).
9. **`.streamlit/config.toml` 작성**(DESIGN_SPEC §5): `base=dark, primaryColor=#E8602C, backgroundColor=#0B0E14, secondaryBackgroundColor=#151A23, borderColor=#2A313D, showWidgetBorder=true, baseRadius=0.5rem, font=Inter, headingFont=Space Grotesk, codeFont=JetBrains Mono, chartCategoricalColors=[#9AA0AC,#1B9E77,#E69F00,#7A2200], [client] toolbarMode=minimal`. **CSS/unsafe_allow_html·자가호스팅 fontFaces 금지**(restart 트랩). 빌드 0분.
10. **`viz/palette.py` 작성**(DESIGN_SPEC §3): MASK(C++ 정본 BGR·α0.45/0.30) / CHART(CVD-safe 명도순 DONENESS_RAMP + 글자칩 + pattern_shape) / ROI_DIFF(Both 그레이 / ONNX-only cyan #56B4E9 / Rule-only magenta #D55E00 해치) 3색공간 상수. Stream B/D 단일소스. 빌드 0분.
11. **`DEMO_SCRIPT.md`(6-beat) + `run.sh`/`demo.sh` 커밋**. ⚠️ **큐레이션 capture 육안검증(인간 필수)**: fixture(`260612_office_backup/206/beef/striploin/251016`)가 **비자명·서사일관 ROI 불일치**(Rule-only=모폴로지/트레이존 아티팩트, ONNX-only=AI 회복)를 실제 오버레이로 보이는지 확인 → near-perfect overlap이면 hero가 비므로 다른 capture로 교체(DESIGN_SPEC §10).

---

## 8. 리스크 & MVP 컷 (크리틱 기반)

**핵심 리스크**
- **정답 없음** → 수치 정확성 게이트 불가. **완화**: §7-7 C++ 오라클 1–2 capture.
- **AI 글로벌=BEEF만** → 비-beef AI 점수 0. **완화**: 비교 데모를 **beef striploin**으로, 또는 메뉴별 글로벌 재계산/주석.
- **조건문 충실도는 beef striploin만** 보장(pork는 파장/deadband 상이). → 메뉴별 규칙테이블 외부화, 미정의 메뉴는 "근사" 라벨.
- **합성점수 스케일 상이**(라이브 AI 0.7/1.5/3.0 · 라이브 beef 1.0/1.0/3.0 · _america 0.5/1.0/4.0, 셋 상이) → 비교축은 **클래스별 %**, maillard는 단일방식 뷰 한정, 양 방식 동일식 사용.
- **near-tie(최상위 데모 리스크)**: cascade 통일 + F-B5 컷 → 차이는 ROI뿐. 게이트 탈락 픽셀이 NOT_DONE으로 대량 잔류해 per-class % 델타가 **거의 0**일 수 있음. **완화**: hero를 per-class %가 아니라 **ROI 면적/IoU 델타 + ROI-diff 시각화**(ONNX윤곽 vs Rule윤곽 + 대칭차 음영)로. 점수는 "같은 규칙·더 깨끗한 ROI = 무튜닝 AI 도입" 보조 서사.
- **NOT_DONE 버킷**: proper+slightly+burnt 합 < 100(게이트 탈락). 커널·ScoreResult·스택바는 **4-way**(not_done 포함). 미반영 시 분모/스택바 왜곡.
- **누락밴드→0 게이트 함정**: 410/440 누락을 0으로 채우면 rule 게이트 `v410<=7|v440<=7`가 전 픽셀 통과 → 점수 폭증. 게이트 밴드 누락 시 스킵/에러(0 대체 금지).
- **PNG/JPEG 동일 band 충돌**, **720nm(led10 peak740 vs led9 peak730) 모호**, **999_999_999 센티넬/희귀 band** → 큐브 그룹핑에서 **PNG 우선 + (min,max,peak) 키 + 센티넬 드롭**.
- **offset 적용**(C++ -3/-1.5/-5; 단 최종 글로벌 출력은 픽셀카운트 재계산으로 **1회**, `OnnxInferenceOutput.h:88-90`) → 커널도 1회. `faithful_triple_offset` 플래그는 **MVP 제거**(Codex). per-menu 채널 정책(beef 3채널/pork burnt만)은 §SCORING_SPEC §4.
- **YOLO-seg 앵커 순서 = y-major**(stride 8→16→32, 각 stride 내 for y: for x; =6300). 순서 틀리면 마스크 무성 깨짐 → Stream B는 "실행됨"이 아닌 **실제추론 비어있지않은 mask**로 게이트.
- **ROI 패리티**(GridBasedAlgorithm region-grow를 모폴로지로 근사) → 조건문을 "규칙 근사"로 표기.
- **정규화 함정**: 입력은 grayscale uint8 → **/255만**(ImageNet mean/std 금지).
- **label 인코딩 모순**(CLASS_NAMES vs 라우팅 주석) → 실제 샘플 마스크로 `palette[label-1]` 순서 확인.
- **빈 ROI / NaN(데모 크래시)**: Rule 모폴로지가 아무것도 못 찾으면 union==0 → IoU NaN/inf. **완화**: §SCORING_SPEC §7 zero-union 가드 + "Rule-ROI 영역 없음" 경고 상태(DESIGN_SPEC §8). Phase-0 BLOCKING 테스트 4.
- **두 hero 모순 / 3분할 프로젝터 cramped**(Claude+Codex 수렴): §9 item2/3가 둘 다 "최상단" 요구 → 두 hero=hero 없음. **완화**: 단일 ROI-diff hero lock, 3분할은 fold 아래 expander 강등(DESIGN_SPEC §6).
- **green/red doneness 색맹/프로젝터 위험**(~남성 8% 적록색약): 색만으로 의미 전달은 WCAG 1.4.1 위반. **완화**: 차트/범례는 CVD-safe 명도순 램프 + 글자칩 + pattern_shape(DESIGN_SPEC §3.2); MASK 오버레이만 C++ 정본 유지.
- **정확도 과장(정답 없음)**: 라벨 0개라 "AI가 더 정확/낫다"는 방어 불가. **완화**: 모든 카피·지표를 "agreement(일치도)"로, 델타는 sign-only 중립색, 승자 표기 금지(DESIGN_SPEC §11).

**v1 컷 (시간 부족 시 순서대로 버림)**
0. **학습형 AI 도넨스(구 F-B5) — OUT OF SCOPE**: AI는 ROI 전용이라는 사용자 제약 위반 + 라벨/마스크 0개라 애초에 학습 불가.
1. exlight_remover (데이터는 calibrated — 빌드 자체 제외)
2. 비-beef AI 점수 (조건문만), 비교 데모는 beef
3. Bland-Altman (산점도로 대체)
4. instances 테이블/드릴다운
5. 픽셀정확 ROI 패리티 (모폴로지 근사 유지, "충실" 주장 철회)
6. lamb·롱테일 메뉴(t_bone/l_bone/Combo/galbi/ddeokgalbi/data) 스모크 제외
7. 오버레이 장식(범례/박스/그리드)
8. ~~3중 offset 플래그~~ → MVP 비범위(단일 offset 고정, `faithful_triple_offset` 제거 — Codex)

---

## 9. 성공 기준 (데모 정의)

1. `cli/run_pipeline.py --limit N`이 beef를 스캔해 `scores.duckdb`에 ai·conditional 양쪽 행을 기록한다.
2. **[HERO·PRIMARY] ROI-diff overlap-map**: mono 배경 + **Both-agree(그레이)/ONNX-only(cyan 실선)/Rule-only(magenta 점선 해치)** 3영역 + 바로 아래 **IoU/Dice/signed area-delta KPI strip**(agreement, sign-only 중립색) + 평문 IoU 캡션("두 방식이 거의 같은 영역"). 단일 hero — 스크롤 없이 최상단(DESIGN_SPEC §7). doneness 램프는 hero에 등장 금지.
3. **[TERTIARY] 원본 | AI 오버레이 | Rule 오버레이** 3분할은 **fold 아래 `st.expander`(기본 접힘)** — 공유 범례 1개 · 동일 **4-way 누적바**(NOT_DONE 그레이 후퇴 · pattern_shape · ND/P/S/B 칩) · per-class % + **절대 픽셀카운트**. hero 아님(3분할만 MASK 정본 hex).
4. (보조) AI vs Rule 산점도(beef striploin, 점 색/크기 = ROI-IoU) — near-tie라 fold 아래.
5. 대시보드 **날짜별/메뉴별** 추이(맥락, Trends/Explore 탭) + 모든 충실도 편차 문서화(§8); C++ 오라클은 소스 정적 대조로 대체(§7-7).
6. **(P1) Demo Mode**가 큐레이션 beef capture로 **테이블 헌트 0회**로 열리고, 모든 카피·지표가 **"agreement(일치도)"**(정확도/우열 표기 금지)로 표시(DESIGN_SPEC §10-11).

---

## 10. 다음 단계
- [x] 본 플랜 리뷰: Claude 5-lens(eng/ceo/devex/design/code) + Codex(xhigh) 교차검증 — **완전 수렴**(ROI-only 제약 반영, F-B5 컷, 라이브 cascade 직접 read 확정).
- [x] **UX/UI/디자인 3차 리뷰**: Claude 6-lens 동적 워크플로(웹 리서치 + IA·visual·states/a11y·comparison-trust·features·devex) + Codex(gpt-5.5 xhigh) **독립 교차검증 → 집합 완전수렴**. 산출: **`DESIGN_SPEC.md` 신설(Phase-0 동결)**. 확정: **Ember 액센트 · 3영역 overlap-map hero · 규율 P0 + 60분 cut-line**. 핵심 수정: 단일-hero(2-hero 모순 해소) · agreement(정확도 아님) 리프레임 · CVD-safe 차트 팔레트 · 상태 매트릭스. 상세 `REVIEW_NOTES §10`.
- [ ] 사전 설정 §7 잔여 실행(statsmodels 제외, dedup-seam fixture 추가, LED 16행).
- [ ] dynamic Workflow(Phase 0→1→2)로 구현 착수. **Phase 0 BLOCKING**: 라이브 `.h` cascade 전사 + label 인코딩 확정 + 대칭성 테스트.
