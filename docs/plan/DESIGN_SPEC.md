# DESIGN_SPEC — 디자인 시스템 & 화면 계약 (Phase-0 FROZEN)

> 이 도구가 **어떻게 보이고 어떻게 읽히는가**를 정의한다. 기능은 `FEATURES_SPEC.md`, 알고리즘은 `SCORING_SPEC.md`, 구조/빌드는 `PLAN.md`.
> **Phase-0 동결 계약**: 여기 정의된 `.streamlit/config.toml` + `viz/palette.py` + `DEMO_SCRIPT`는 **사전 설정(pre-setup)에서 작성**되어 90분 빌드 시간에 포함되지 않는다. Stream B(AI 오버레이)와 Stream D(Rule 오버레이·차트·hero)가 **동일 팔레트 상수**를 import → 후반 범례 seam 차단.
>
> 검토 출처: Claude 6-lens 워크플로(IA·visual·states/a11y·comparison-trust·features·devex) + Codex(gpt-5.5, xhigh) 독립 교차검증 — **집합 완전수렴**. 확정 결정: 액센트 = **Ember**, hero = **3영역 overlap-map**, 스코프 = **규율 P0 + 60분 cut-line**.

---

## 1. 목적 & 범위

DESIGN_SPEC가 지배하는 것: **미학(aesthetic) · 정보구조(IA) · 인터랙션 상태 · 접근성(a11y) · 데모 플로우**.
지배하지 않는 것: 점수 알고리즘(`SCORING_SPEC`), 데이터 수집/영속(`PLAN §4-5`).

**근본 원칙 (정답 없음 → 승자 없음)**: 라벨/마스크 0개라 수치 정확성을 증명할 수 없다. 따라서 UI의 모든 카피·색·지표는 **"정확도(accuracy)"가 아니라 "일치도(agreement)"**를 말한다. "AI가 더 정확/더 낫다"는 어떤 표현도 데모에서 방어 불가 → 금지(§11). 두 방식의 차이는 **"같은 굽기 규칙, 다른 ROI(고기) 마스크"**일 뿐.

---

## 2. 디자인 방향 — "Spectral Lab Instrument"

**다크 과학계측기 미학.** Streamlit 스크립트가 아니라 **보정된 센싱 도구**로 읽혀야 한다.

- **Streamlit 유지 + config.toml로만 강하게 테마**(CSS 금지). 근거: 스택 전체(DuckDB·Plotly·image_comparison·image_coordinates)가 Streamlit-native, 90분 천장이 SPA 재작성을 금지, modern Streamlit(>=1.50) 테마는 config-file 구동이라 "premium 룩 ~80% + 색맹 fix"가 **사전커밋 ~40줄 1파일·빌드 0분**. 프레임워크 교체는 예산 전체를 태우고 단발 로컬 데모엔 이득 0.
- **액센트 = Ember `#E8602C`** (숯불 heat 메타포 · 그릴 브랜드 직관). 단일 액센트 — 절제가 premium.
- **순흑(`#000`) 금지**: 순흑은 grayscale 이미징 대비 서사를 죽인다. 캔버스는 `#0B0E14`(near-black).
- **장식 금지**: drop-shadow/glow/gradient 없음. 깊이는 1px 보더 + secondaryBackground 대비로만. (Rams "as little design as possible".)
- 참고 관용: 실제 NIRS/분광 SW(Avantes, SpectroWorks)는 다크 베이스 + cyan/teal 액센트 + 모노스페이스 숫자를 신뢰성 코드로 표준화 → 본 도구도 동일 문법.

---

## 3. 색 시스템 — 3개의 분리된 색 공간 (Phase-0 동결: `viz/palette.py`)

⚠️ **3개 공간은 절대 섞이지 않는다.** doneness 램프가 hero diff에 나타나면 시청자가 "번트(빨강)"와 "Rule-only ROI"를 혼동한다.

### 3.1 MASK 팔레트 — 라이브 C++ 정본 (충실 포팅, 불변)
오버레이 마스크 전용. `OnnxVisualization` BGR hex 그대로, **class α=0.45 / doneness α=0.30**. green/yellow/red가 살아남는 **유일한** 곳 — 라이브 "as-is" 오버레이라서. (정본 hex는 `SOURCE_ANALYSIS §6` / `[[sensing-live-beef-cascade]]`.)
- 도넨스: proper `(11,238,34)` / slightly `(0,200,255)` / burnt `(0,5,255)` (BGR).
- 클래스: BEEF `(173,72,0)` / CHICKEN `(34,120,236)` / LAMB `(220,220,220)` / PORK `(220,160,230)` (BGR).
- mono 배경 = ch3/led10.

### 3.2 CHART/LEGEND 팔레트 — CVD-safe (config.toml `chartCategoricalColors`로 앱 전역 상속)
모든 Plotly 차트(4-way 누적바·추이·산점도)가 **per-figure color 인자 없이** 상속. **단조 명도(monotonic lightness) 순서** → grayscale 프로젝터 + 적록색약(deuteranopia ~남성 8%) 양쪽에서 순서 보존.

| 클래스 | hex | 글자칩 | pattern_shape | 의도 |
|--------|-----|:----:|:----:|------|
| NOT_DONE | `#9AA0AC` 중립 그레이 | `ND` | `.` | **지배 픽셀이지만 시각적으로 후퇴**(게이트 탈락 버킷이 시선을 뺏지 않게) |
| PROPER (Deep Maillard) | `#1B9E77` | `P` | (solid) | |
| SLIGHTLY_BURNT | `#E69F00` 앰버 | `S` | `/` | |
| BURNT (Carbonized) | `#7A2200` 다크 레드브라운 | `B` | `x` | char 시맨틱 유지 + 최저 명도 |

**중복 인코딩 필수**: 색만으로 의미 전달 금지(WCAG 1.4.1). 글자칩 + pattern_shape + 직접 라벨을 항상 동반.
> 빌드 시 대조 검증: Codex가 Python으로 WCAG 대비를 계산한 대안(NOT_DONE `#0072B2`/PROPER `#006C4F`/SLIGHTLY `#A65E00`/BURNT `#8E3B78`, 전부 흰 배경 3:1+)도 유효. 본 램프(명도 순서 + NOT_DONE 그레이 후퇴)를 채택하되, Phase-0에서 캔버스 `#0B0E14`/카드 `#151A23` 대비 3:1을 1회 확인.

### 3.3 ROI_DIFF 팔레트 — hero 전용 (제3의 색 공간: 출처지 doneness 아님)
| 영역 | 채움 | 윤곽 |
|------|------|------|
| Both-agree (onnx & rule) | 중립 그레이 `#5A5A5A` α≈0.18 (고기 텍스처 비침) | — |
| ONNX-only (onnx & ~rule) | cyan `#56B4E9` 채움 | **실선** 2px |
| Rule-only (rule & ~onnx) | magenta/vermilion `#D55E00` **해치** 채움 | **점선** 2px |

cyan/magenta는 Okabe-Ito 색맹안전쌍. 윤곽은 저알파 채움 위에 `cv2.drawContours`로 얹어 경계가 항상 또렷. **doneness 램프는 hero에 절대 등장 안 함.**

---

## 4. 타이포그래피

- body `font = "Inter, sans-serif"` · heading `headingFont = "Space Grotesk, sans-serif"` · **모든 숫자** `codeFont = "JetBrains Mono, monospace"`.
- **모노스페이스 숫자 = 센싱 계측기 신뢰성의 가장 싼 단서**: IoU·Dice·ROI px·per-class %·band-provenance strip 전부 JetBrains Mono.
- **named Google 폰트 인라인만** 사용. 자가호스팅 `[[theme.fontFaces]]`는 **server-restart 트랩 + static/ 디렉토리** 필요 → 본 빌드 비범위(P2). 빌드 시 named 폰트 미번들이면 안전 패밀리(`sans-serif`/`monospace`) 폴백.

---

## 5. `.streamlit/config.toml` — 동결 아티팩트 (사전커밋, 빌드 0분)

CSS/`unsafe_allow_html` 테마 금지. live-reload는 색/보더는 rerun 반영, **font/baseFontSize만 server restart** 필요.

```toml
[theme]
base = "dark"
primaryColor = "#E8602C"            # charbroiler ember (흰 버튼 텍스트 대비 OK)
backgroundColor = "#0B0E14"         # near-black (순흑 금지)
secondaryBackgroundColor = "#151A23" # card surface
textColor = "#E6EAF0"
linkColor = "#F2A07A"               # 밝은 ember (액센트 일관)
borderColor = "#2A313D"
showWidgetBorder = true
baseRadius = "0.5rem"
font = "Inter, sans-serif"
headingFont = "Space Grotesk, sans-serif"
codeFont = "JetBrains Mono, monospace"
# CVD-safe doneness 램프 — 모든 Plotly 차트가 상속 (per-figure 인자 0)
chartCategoricalColors = ["#9AA0AC", "#1B9E77", "#E69F00", "#7A2200"]

[client]
toolbarMode = "minimal"             # dev 메뉴 strip (CSS #MainMenu 핵 금지)
```

> `chartCategoricalColors` 순서 = NOT_DONE/PROPER/SLIGHTLY/BURNT. 4-way 누적바는 이 순서로 시리즈를 추가하면 색 인자 없이 정합.

---

## 6. 레이아웃 & 정보구조 (IA)

**`st.set_page_config(layout="wide", page_title="BH Sensing", page_icon=":material/sensors:", initial_sidebar_state="expanded")` 를 최초 st 호출로** (layout='wide'는 3분할이 노트북/프로젝터에서 좁아지는 함정을 직접 해소).

### 사이드바 (지속 nav rail · 위→아래 고정)
1. 앱 타이틀 + `st.logo`
2. **Mode 라디오: `Demo` | `Explore`**
3. 메뉴 multiselect + 날짜 range (F-A3)
4. capture picker (**Explore 모드에서만**)
5. band-provenance / 범례 글자칩 키

### 메인 = 3개 탭 (`st.tabs`)
- **`Compare` (기본)** — **단일 hero 화면**:
  - **PRIMARY**: ROI-diff overlap-map hero 이미지, content 폭 가득(§7).
  - **SECONDARY**: 바로 아래 1행 KPI strip — `st.metric` 3개(IoU/Dice/signed area-delta), `st.container(border=True)` 안.
  - **TERTIARY**: 원본|AI|Rule **3분할** + 4-way 누적바 + per-class % 델타는 **`st.expander("Per-panel detail", expanded=False)` 안(기본 접힘, fold 아래)**. → 3분할은 hero 아님.
- **`Trends`** — 날짜별 추이(F-D1). 맥락용.
- **`Explore`** — AI vs Rule 산점도(F-C3) + 메뉴별 바(F-D2) + capture 테이블(F-D3) + (P1) per-class MAE.

> ⚠️ **해결된 모순**: 기존 `PLAN §9 item2(ROI-diff hero)`와 `item3(3분할)`이 둘 다 "스크롤 없이 최상단"을 요구했고 `REVIEW_NOTES §6`은 3분할을 "first-screen hero"라 명명 — 두 hero = hero 없음 + 3초 스캔 실패. **단일 hero로 lock, 3분할은 expander로 강등.**

### 표면 처리
native `st.container(border=True)` 카드 + `st.subheader` 타이틀. 깊이는 1px 보더 + secondaryBackground 대비. **drop-shadow/glow 금지.** KPI 행은 `st.container(horizontal=True)` 권장(작은 화면 wrap).

### 모션
`st.status` 도메인 카피 전환만('Segmenting meat instances… / Scoring 11 wavelength bands…'). 그 외 애니메이션 0.

---

## 7. The Hero — ROI-diff overlap-map + agreement scorecard

### 7.1 overlap-map 합성 (Stream D, ~20m, P0 — 전체 pivot이 의존)
순수 numpy boolean 영역을 mono ch3/led10 위에 합성:
```
both     = onnx_roi & rule_roi          # 그레이 #5A5A5A  α0.18
onnx_only = onnx_roi & ~rule_roi        # cyan  #56B4E9  채움 + 실선 2px 윤곽
rule_only = rule_roi & ~onnx_roi        # magenta #D55E00 해치 채움 + 점선 2px 윤곽
```
윤곽은 `cv2.drawContours`로 저알파 채움 위에 ~2px(ONNX 실선/Rule 점선). 3칩 inline 범례를 다크 scrim strip으로 burn. 캡션 칩: **"Same doneness rules. Different ROI mask."**

### 7.2 agreement scorecard (Stream D, ~8m, P0)
`st.container(horizontal=True, border=True)` + `st.metric` 3개 (JetBrains Mono):
- **IoU** (헤드라인) + 평문 캡션 `"IoU 0.93 — 두 방식이 거의 같은 영역 선택; >0.90 = 강한 일치"`.
- **Dice** (보조 — full agreement 부근에서 IoU보다 민감).
- **signed ROI-area delta px** (near-tie에서도 비0 → "지루한 단일 숫자" 방지).
- 모든 델타는 **sign-only + 중립색**(green=good 금지, 정답 없음=승자 없음).
- 수식·가드·threshold는 `SCORING_SPEC §7`(`STRONG_AGREEMENT_IOU=0.90`, `union==0 → "No overlapping ROI" 센티넬, NaN 금지`).

### 7.3 (P1) hero 컨트롤
- 전역 fill-opacity 슬라이더(0.0–0.6, 기본 0.30) + `Contour only` 체크박스 — 채움이 이미지를 가린다는 #1 실사용 불만 해소. boolean 마스크는 `@st.cache_data`(capture_id 키), 슬라이더는 알파 블렌드만 재계산.

---

## 8. 인터랙션 상태 매트릭스 (F-E3 AC)

Streamlit 데모는 first-run 데이터 가정에서 가장 잘 죽는다 → 모든 상태를 1급 화면으로 명세.

| 상태 | 트리거 | Streamlit 프리미티브 | 도메인 카피 / 복구 |
|------|--------|---------------------|-------------------|
| **FIRST_RUN/no-DB** (P0) | `scores.duckdb` 없음 또는 `count(*)==0` | read_only open **전에** 파일 존재 + `SELECT count(*)` 가드; `st.info` | "아직 점수 없음 — `bash run.sh`(또는 `python cli/run_pipeline.py --limit 20`), 또는 Demo Mode" |
| **PARTIAL** (P1) | 특정 메뉴 AI 행 없음(비-beef) | `st.warning` + ONNX 윤곽 숨김 | "이 메뉴는 AI ROI 미산출 — Rule ROI만 표시" |
| **LOADING** (P1) | 파이프라인/데모 진행 | `st.status` 단계 + `st.spinner` 쿼리/이미지 | "Segmenting meat instances… / Scoring 11 wavelength bands…" |
| **NO-ROI** (P0 가드) | Rule 모폴로지가 아무것도 못 찾음 | `st.warning` + §7 zero-union 가드 | "Rule-ROI 영역 없음 — IoU 미정의" (NaN 금지) |
| **ERROR** (P1) | ONNX 로드 실패·band 누락·DuckDB 락·오버레이 경로 없음 | `st.error` + `st.expander` traceback | 복구 액션 1줄 + 상세는 expander |

**P0 floor** = `FIRST_RUN/no-DB` 가드 + `NO-ROI` 가드(크래시 방지·~6m). 나머지(full matrix)는 P1.

---

## 9. 접근성 (a11y)

- **색만으로 의미 금지**(WCAG 1.4.1): §3.2 CVD 램프 + 글자칩 + pattern_shape + 직접 라벨.
- **이미지 위 텍스트**: 모든 OpenCV burn 캡션은 반투명 다크 scrim 칩(`rgba(0,0,0,~0.55)`) 또는 2px halo(WCAG G145)로 가변 mono 고기 배경 위 ≥3:1 유지. 1차 IoU/Dice는 **이미지 위 burn뿐 아니라 그 위 `st.metric`으로도** 표기.
- **WCAG 대비**: 의미 그래픽 비텍스트 3:1, 텍스트 4.5:1(대형 텍스트 예외). (출처: WCAG 2.2 1.4.3/1.4.11.)
- **프로젝터 가독**: 라이트 아닌 다크여도 고대비, 이미지 위 raw 텍스트 금지, **KPI 카드 28–36px, 범례 ≥18px, 윤곽 4px+halo**, hero는 단일 대형 이미지 기본.
- 참고: Color Universal Design(jfly.uni-koeln.de/color) — 중복 코딩·굵은 선·직접 라벨·적록 의존 회피.

---

## 10. 데모 플로우

### 10.1 DEMO_SCRIPT — 6 beat 60초 골든패스 (Phase-0 아티팩트)
Stream D 빌드 전 작성. **Phase-2 통합자는 이 경로만 버그수정.**
1. **Hook** — 핏마스터가 숯불 위 굽기를 눈으로 판정한다.
2. 실제 BEEF striploin mono frame 표시.
3. **ROI-diff hero reveal** (wow).
4. **ONE 캡션** — `IoU 0.93, area delta +X px` — "같은 규칙 · 더 깨끗한 AI ROI · 무튜닝".
5. "11 wavelengths — AI가 분할(segments), 규칙이 판정(decide)."
6. close.

### 10.2 Demo Mode UI (F-D5 · P1)
사이드바 `st.radio('Demo'|'Explore')`. **Demo**: 큐레이션된 capture_id(`260612_office_backup/206/beef/striploin/251016`) 하드코딩·자동선택(2.8k행 테이블 헌트 skip), Compare hero 사전렌더(detail expander 접힘), 6-beat를 번호 `st.status`/`st.info` 캡션으로. **Explore**: 전체 필터 + capture 테이블.
> ⚠️ **Phase-0 큐레이션 게이트(인간 육안 필수)**: fixture가 **비자명·서사일관 ROI 불일치**(Rule-only magenta = 모폴로지/트레이존 아티팩트, ONNX-only cyan = AI가 실제 고기 회복)를 보이는지 실제 오버레이로 확인. near-perfect overlap이면 hero가 비므로 다른 capture를 Phase-0에서 손으로 교체.

---

## 11. 정직성 가드레일 (Honesty Guardrails)

정답 없음 ⇒ **승자 없음**. 따라서:
- "정확도/더 나음/맞음(accuracy/better/correct)" 카피 **금지**. 항상 "일치도(agreement)".
- "AI doneness" 표현 금지 — AI는 ROI 전용.
- **모든 델타 sign-only + 중립색** (diverging green/red 금지).
- **per-class % 옆에 절대 픽셀카운트** 항상 표기 → "+40% burnt"가 실제 12px이면 작게 읽힘(증폭 거짓말 방지).
- **NOT_DONE은 분모에서 절대 제거 안 함**; 그레이로 후퇴시키되 4-way 누적바에 항상 표시; `NOT_DONE > 60%`면 "NOT_DONE-dominant" 배너(Codex).
- `maillard_score` 비교 hero 금지(스케일 3변형 상이) — 단일방식 뷰 한정, 라벨 `(AI weights)`/`(rule weights)`.

---

## 12. 빌드 예산 & cut-line

**확정 스코프: 규율 P0 + 60분 cut-line.** Stream A(~55m)가 binding 임계경로, **Stream D는 숨은 2차 임계경로(~62분 창에서 55분 시작 → 실 슬랙 ~7m)**.

| # | 항목 | 우선 | 비용 | 담당 |
|---|------|:---:|:---:|------|
| 1 | `.streamlit/config.toml`(다크 ember + CVD 램프 + 폰트 + minimal) | P0 | **0m** | Phase0(사전커밋) |
| 2 | `viz/palette.py` 동결(MASK/CHART/ROI_DIFF 3공간) | P0 | **0m** | Phase0 |
| 3 | DEMO_SCRIPT 6-beat + run.sh/demo.sh | P0 | **0m** | Phase0 |
| 4 | overlap-map hero(3영역 + 윤곽 + scrim 범례) | P0 | 20m | D |
| 5 | IoU/Dice/area-delta scorecard + zero-union 가드 + 평문 IoU | P0 | 8m | D |
| 6 | 단일-hero 3탭 IA(wide, Compare/Trends/Explore, expander) | P0 | 7m | D |
| 7 | 사이드바 IA(타이틀·Mode·필터·picker·범례) | P0 | 5m | D |
| 8 | missing-DB / no-ROI 가드 (P0 floor) | P0 | 6m | D |
| 9 | per-class 절대 픽셀카운트 | P0 | 4m | D |
| — | **P0 Stream-D 소계** | | **~50m** | D |
| 10 | full State Matrix + error states | P1 | 12m | D |
| 11 | Demo Mode(라디오 + 자동선택 + st.status 단계) | P1 | 12m | D |
| 12 | bordered 카드 컴포지션 + 4-way 바 중복인코딩 | P1 | 10m | D |
| 13 | hero opacity 슬라이더 + Contour-only | P1 | 6m | D |
| 14 | 11-band provenance strip | P1 | 5m | D |
| 15 | differences-only / foreground-only 토글 + within-noise 배지 | P1 | 14m | D |
| 16 | pixel "why this class?" inspector (image-coordinates + gate trace) | P2 | 18m | D |
| 17 | PNG/CSV export | P2 | 8m | D |
| 18 | wipe-slider hero (streamlit-image-comparison) | P2(컷) | 12m | D |

**90분 보장 메커니즘**:
- 1–3은 사전커밋 0분. P0 Stream-D 순-신규 = **~50m** (hero 20m가 binding 리스크).
- **60분 cut-line**: 60분 시점 Stream D 미완 → hero를 **`st.image` 3분할 + IoU 캡션**으로 강등(overlap-map 합성·슬라이더·pixel-probe drop).
- **명시적 defer**: wipe-slider(#18 컷, 경쟁 2nd hero), pixel inspector(#16 P2), export(#17 P2), 토글(#15 P1) — Stream D 여유 있을 때만.
- **deps 동결**: matplotlib/Bland-Altman/statsmodels 컷 유지(신규 설치 0). image_comparison/image_coordinates는 P1/P2 진입 시에만 사전설치.
- **Phase-0 렌더 계약 동결**(Codex+Claude 수렴 핵심): `roi_mask` / `class_map` / `overlay_path`·`mono_path` / paired-score 쿼리 셰이프를 Phase-0에 동결 → Stream D가 A/B 미동결 산출물 대기 안 함.
