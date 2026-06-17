# SCORING_SPEC — 포팅할 정확한 알고리즘 (구현 계약)

두 방식 모두 **동일 `ScoreResult`** 를 생성한다. **확정**: 도넨스 cascade를 통일하므로 변하는 것은 **ROI 소스뿐**(메서드명 "ONNX ROI" / "Rule ROI"). AI는 ROI/세그멘테이션 전용, 도넨스는 양쪽 모두 규칙 — 학습형 분류기(구 F-B5)는 사용자 제약상 **컷**. 통일 cascade는 **라이브 `beef_strip_loin/ComponentRecognizer_BeefStripLoin_CharBroiler.h:112-158`** 기준이며 아래 §3에 **직접 read로 확정**(Claude 5-agent + Codex xhigh 교차검증 완전 수렴).
모든 산술은 **int32/float**(uint8 오버플로 금지). band는 **(min,max,peak) 튜플**로 키.

## 0. 공유 출력 계약 `ScoreResult`
```
pixels_roi:int
pct_proper, pct_slightly_burnt, pct_burnt : float   # Deep Maillard / Slightly Charred / Carbonized (post-offset)
pct_burnt_raw : float                                # pre-offset burnt% (= burnt_score)
pct_not_done : float                                 # ROI 내 미분류 픽셀% (라이브 게이트 탈락 — 대개 최대 버킷)
cooking_score : float                                # 기본 = pct_proper
maillard_score : float                               # 양 방식 동일 가중식(§3); 비교축은 per-class %
grade:int, grade_label:str                           # grade 0 = 완료(COMPLETE)
instance_count:int                                   # AI: 채택 인스턴스(>=500px) 수, 조건문: 1
per_instance : list[InstanceResult]                  # AI 전용 (옵션)
# 오버레이 렌더용(Stream D 의존) — Phase-0 동결 필수:
roi_mask : bool[H,W];  class_map : uint8[H,W] ∈ {0..4};  mono_bg_path / overlay_path : str
```
클래스 인덱스(고정): `NOT_ROI=0, NOT_DONE=1, PROPER=2, SLIGHTLY_BURNT=3, BURNT=4`.
고기 클래스(AI): `0 BEEF, 1 CHICKEN, 2 LAMB, 3 PORK` (label_map = class_id+1; 빌드시 실제 마스크로 확정).

**COLOR SPACES (3개 분리, `viz/palette.py` Phase-0 동결 — 상세 DESIGN_SPEC §3)**:
1. **MASK** = 정본 C++ BGR hex, α 0.45(class)/0.30(doneness). 충실 오버레이 전용(green/yellow/red는 여기서만).
2. **CHART** = CVD-safe **DONENESS_RAMP** 명도순: `NOT_DONE #9AA0AC(그레이·후퇴) / PROPER #1B9E77 / SLIGHTLY #E69F00 / BURNT #7A2200` + 글자칩 ND/P/S/B + `pattern_shape`. `config.toml chartCategoricalColors`로 전 Plotly 상속.
3. **ROI_DIFF**(hero, 출처지 doneness 아님): `Both #5A5A5A α0.18 / ONNX-only #56B4E9 실선 / Rule-only #D55E00 점선·해치`. doneness 램프 hero 사용 금지.

## 1. `DonenessKernel` (두 방식 공유)
입력(동결 데이터형): `roi_mask: bool[H,W]`, `class_map: uint8[H,W] ∈ {0 NOT_ROI,1 NOT_DONE,2 PROPER,3 SLIGHTLY,4 BURNT}` — A·B가 공유 합성배열 단위테스트로 검증(**NOT_DONE 픽셀 포함 필수**). 처리:
```
roi = max(roi_mask.sum(), 1)
pct_x = count_x * 100.0 / roi             # x ∈ {not_done, proper, slightly_burnt, burnt}
# ⚠ proper+slightly+burnt 합은 보통 < 100 — 라이브 게이트 탈락 픽셀이 NOT_DONE으로 대량 잔류.
#    스택바/계약은 4-way(not_done/proper/slightly/burnt = 100)로 다룬다.
# 보정 offset (0 floor) — 최종 라이브 출력과 동일하게 **1회만** 적용.
# 채널 정책은 메뉴별(§4): beef = burnt/slightly/proper 셋 다, pork = burnt만.
pct_burnt          = max(pct_burnt - 3.0, 0.0)
pct_slightly_burnt = max(pct_slightly_burnt - 1.5, 0.0)   # beef만
pct_proper         = max(pct_proper - 5.0, 0.0)           # beef만
cooking_score = pct_proper
```
`maillard_score`는 §3(양 방식 동일 가중식). roi==0 → 점수 0/NaN 가드(빈 ROI 계약 필수).
> offset: C++ 글로벌은 픽셀카운트에서 재계산해 **1회만** 적용됨(OnnxInferenceOutput.h:81-90). 커널 글로벌 경로도 1회 적용(일치). `faithful_triple_offset` 플래그는 **MVP에서 제거**(Codex 수렴) — 최종 공개 출력은 단일 offset.

## 2. AI 방식
**Step A — meatSegNet ROI (segment/meatsegnet.py)**
```
입력 5ch = led[2,4,8,10,12] = (460,520,650,720,840), /255, 누락→0, [1,5,480,640] f32
preds[1,6300,41], protos[1,32,120,160]
anchors: stride 8→16→32 순, 각 stride 내부 **y-major(for y: for x)**, center=((x+0.5)*s,(y+0.5)*s), concat=6300 (원본 OnnxROIRecognizer.h:147-158)
per anchor: obj=sigmoid(p[4]); skip<0.30; cls=softmax(p[5:9]); final=obj*max; skip<0.30
  box: cx=ax+p[0]*s, cy=ay+p[1]*s, w=exp(clip(p[2],-10,10))*s, h=exp(clip(p[3],-10,10))*s; frame clip
  coeffs=tanh(p[9:41])
per-class NMS IoU>0.4
label_map=zeros(480,640,uint8); dets를 score 오름차순 정렬(고점이 마지막에 덮음)
  m=sigmoid(coeffs @ protos.reshape(32,120*160)).reshape(120,160)
  resize→(640,480) LINEAR; box(+10px) ROI; GaussianBlur 5x5; (m>0.35)*255; MORPH_CLOSE ellipse5x5
  label_map[roi][bin>0] = class_id+1
```
> 정렬 2종 구분(병합 금지): NMS는 score **내림차순**(OnnxROIRecognizer.h:173), label_map 페인트는 score **오름차순**(:332, 고점이 마지막에 덮음). 정규화는 grayscale uint8 **/255만**(ImageNet mean/std 금지).

**Step B — per-instance 도넨스 (scoring/ai.py + kernel)**
인스턴스: `connectedComponents(label_map==class_id+1, 8)`; `<500px` 제거. 각 인스턴스 ROI에 §4 규칙 cascade 적용.
**Step C — 글로벌**: BEEF(class 0) 인스턴스만 합산해 퍼센트 재계산 + offset. `maillard_score = proper*0.7 + slightly*1.5 + burnt*3.0`.

## 3. 조건문 방식 — 라이브 beef 인식기 **그대로** (확정, 직접 read 검증)

> 양쪽 방식이 공유하는 도넨스 cascade는 **라이브** `beef_strip_loin/ComponentRecognizer_BeefStripLoin_CharBroiler.h:112-158`를 **그대로** 포팅한다.
> (이전 버전 문서는 `_america` 변형을 옮겨 적은 **오류** — 라이브와 게이트/임계/사용밴드가 다름: 라이브는 **410/440 게이트, 460·800 미사용**; _america는 460/800 사용·410 게이트 없음.)

**ROI mask (Rule ROI = 근사, 충실 아님)**
라이브 rule-ROI(`ROIRecognizer_BeefStripLoin_CharBroiler.h`)는 **12단계 GridBasedAlgorithm 파이프라인**(BackgroundFilter→Smoothing×3→fillingHole×3→regionGrowing×4)이며 90분 내 충실 포팅 불가 → **모폴로지 근사**로 대체, NF-1에 편차 명기("rule ROI 근사", 충실 주장 금지). 근사 seed는 라이브 `recognizeROI`(:192-206):
```
gate = (v410<=30)&(v440<=30)&(v930>40)&(v930<140)
b1 = (v520>=60)&(v440*2<v520)&(v520*1.8<v720)&(v930>100)
b2 = (v650<80)&(v520*2.0<v720)&(40<=v520<60)&(v520*2.2<v930)&(v520>=v650-20)
b3 = (v650<80)&(v520*2.5<v720)&(v520<40)&(v520*2<v930)
roi_seed = gate & (b1|b2|b3)  →  morphology CLOSE/OPEN + (권장) BackgroundFilter 트레이존 크롭(우측 ~80열) + connectedComponents
```
> ⚠ 트레이존 크롭을 빼면 rule-ROI가 실제 제품보다 더 지저분해져 "AI 정밀 vs 규칙 뭉갬" 서사가 **역전** 가능 → 우측 ~80열 numpy 슬라이스(~10줄)만이라도 포팅 권장.

**픽셀 분류 (라이브 그대로, 우선순위 burnt>slightly>proper, roi 한정)**
```
gate     = (v410<=10 & v440<=15) | (v410<=7) | (v440<=7)
burnt    = gate & (v650<=30) & (v720<=40) & (v930>=50)
slightly = gate & (v585<=20) & (v650<=40) & (v720<=60) & (v930>=50)
proper   = gate & (v585<=25) & (v650<=50) & (v720<=80) & (v930>=50)   # 살코기
         | gate & (v520<=30) & (v650>50)  & (v930>=70) & (v720>70)    # 지방(둘 다 PROPER)
# 위 어디에도 안 맞는 roi 픽셀 = NOT_DONE (proper/slightly/burnt 합 < 100)
```
사용 밴드 9개(ledId): 410(led0),440(led1),520(**led4**·peak567),585(led5),650(led8),720(**led10**·peak740),930(led14) + 로드되나 라이브 cascade 미사용: 460(led2),800(led11).
> ⚠ 원본 C++ 버그: `tImagingArray` 크기 8인데 `case 1`(440)이 index 8 기입(OOB·UB). 포팅은 440을 **정상 슬롯으로 포함**(키 기반 `bandByLed` 접근)하면 해결.
> ⚠ 누락밴드→0 함정: 410/440 누락 시 0으로 채우면 게이트 `v410<=7|v440<=7`가 **전 픽셀 통과** → 점수 폭증. 게이트 밴드(410/440) 누락 시 0 대체 금지(스킵/에러).

**점수**: `pct_x=count*100/max(roi,1)`; offset **1회**(§1); `cooking_score=pct_proper`; `burnt_score=pre-offset burnt%`.
**maillard_score(=Grill Index)**: 비교 공정성 위해 **양 방식 동일 가중식** — 라이브 AI 글로벌 출력과 동일 `proper*0.7 + slightly*1.5 + burnt*3.0`(OnnxInferenceOutput.h:93-95). (참고: 라이브 beef 단일메뉴 출력은 `1.0/1.0/3.0`, _america는 `0.5/1.0/4.0` — 셋이 상이 → 비교축은 항상 **per-class %**, maillard는 단일방식 뷰 한정. `_america 0.5/1.0/4.0`은 비교 comparator로 쓰지 말 것 — Codex.)

## 4. 메뉴별 규칙 테이블 (외부화, 전역상수 금지)
deadband: beef -3.0, pork_nape -2.0, pork_belly_herb -1.5.
**offset 채널 정책(메뉴별, 빌드시 라이브 확정)**: beef = burnt/slightly/proper **셋 다**; **pork = burnt만**(`ComponentRecognizer_PorkBelly_Charcoal_CharBroiler.h:408-415` 검증). 커널은 메뉴별 채널 정책을 읽어 적용(획일적 3채널 금지).
pork 도넨스는 라이브 **`recognizeComponent_new`** 사용(파장 410/460/520/585/620/650/740/840/930).
> ⚠ pork v2 "조금 탄 지방" 분기는 count는 올리나 render map(slightly) 미기록(소스 quirk). pork는 데모 비범위지만 포팅 시 의식적 결정·문서화.
미정의 메뉴(t_bone/l_bone/Combo/galbi/ddeokgalbi/data)는 "근사" 라벨 + 기본 규칙.

## 5. 등급 사다리 (데이터 구동, `{menu:(score_field, ladder)}`, grade 0=완료)
- Charcoalroom beef / `maillard_score`: >50→5, >30→**0**, >12→4, >8→3, >5→2, else 1
- Office chicken-thigh / `maillard_score`: >=27→4, >=20→**0**, >14→3, >7→2, else 1
- Kiyoung chicken / `slightly_burnt`: >=9→**0**, >6→2, >3→2, else 1
- Jungsooksung pork(복합): maillard>=35→**0**; elif burnt_score>10→**0**; elif maillard<10→1,<15→2,<20→3, else 4

## 6. band↔LED 정본 (`src/model/PropertiesDatabase.h:113-128` 직접 검증 — 16개 전수)
led0=410/420/415, led1=440/460/450, led2=460/480/470, led3=515/540/527, led4=520/610/567, led5=585/595/590, led6=610/620/615, led7=620/630/625, led8=650/670/660, led9=720/750/**730**, led10=720/740/**740**, led11=800/830/810, led12=840/870/850, led13=870/910/890, led14=930/970/940, led15=999/999/999(센티넬).
meatSegNet 5ch = led 2,4,8,10,12 = 460/520/650/720(led10·peak740)/840. 도넨스 규칙 720 = **led10**, 520 = **led4**(peak567, NOT led3=527).
**720nm 모호 → (min,max,peak)로 led9(730) vs led10(740) 구분**. PNG/JPEG 동일 band → **PNG 우선**. `999_999_999`(led15) 센티넬 드롭. **bands.py는 16행 전부 박제**(led3/6/7/13 누락 시 해당 band 파일 미매핑).

## 7. Agreement 지표 (두 ROI 비교 — 정답 없음 ⇒ "일치도"이지 "정확도" 아님)
hero scorecard와 F-C2가 소비. ONNX-ROI mask `A`, Rule-ROI mask `B`(둘 다 bool[H,W]):
```
inter = (A & B).sum();  union = (A | B).sum()
IoU       = inter / union
Dice      = 2*inter / (A.sum() + B.sum())          # full agreement 부근 IoU보다 민감
area_delta = int(A.sum()) - int(B.sum())           # signed px (near-tie에서도 비0)
```
**GUARD(Phase-0 BLOCKING 테스트 4)**: `union == 0` 또는 `(A.sum()+B.sum()) == 0` → `IoU/Dice = "No overlapping ROI"` **센티넬 문자열 반환(NaN/inf 절대 금지** — 무대 크래시 차단).
**임계 상수(named, 매직넘버 금지)**: `STRONG_AGREEMENT_IOU = 0.90` ("IoU 0.93 — 두 방식이 거의 같은 영역" 평문 캡션 트리거). per-class % 비교에서 `|delta| < AGREEMENT_NOISE_EPS_PTS`는 "within noise" 처리.
**표기 규칙(DESIGN_SPEC §11)**: 모든 델타 **sign-only + 중립색**, "더 정확/낫다" 금지. NOT_DONE은 분모에서 제거 금지(그레이 후퇴만). `NOT_DONE > NOT_DONE_DOMINANT_PCT(=60)`면 배너 표시. `maillard_score` 공동플롯 금지(스케일 3변형 상이).
