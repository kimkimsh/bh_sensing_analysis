# SCORING_SPEC — 포팅할 정확한 알고리즘 (구현 계약)

두 방식 모두 **동일 `ScoreResult`** 를 생성한다. 변하는 것은 *픽셀 클래스 판정 + ROI 소스*뿐.
모든 산술은 **int32/float**(uint8 오버플로 금지). band는 **(min,max,peak) 튜플**로 키.

## 0. 공유 출력 계약 `ScoreResult`
```
pixels_roi:int
pct_proper, pct_slightly_burnt, pct_burnt : float   # Deep Maillard / Slightly Charred / Carbonized (post-offset)
pct_burnt_raw : float                                # pre-offset burnt% (= burnt_score)
cooking_score : float                                # 기본 = pct_proper
maillard_score : float                               # 방식별 가중식
grade:int, grade_label:str                           # grade 0 = 완료(COMPLETE)
instance_count:int                                   # AI: 채택 인스턴스(>=500px) 수, 조건문: 1
per_instance : list[InstanceResult]                  # AI 전용 (옵션)
# 오버레이 렌더용(Stream D 의존) — Phase-0 동결 필수:
roi_mask : bool[H,W];  class_map : uint8[H,W] ∈ {0..4};  mono_bg_path / overlay_path : str
```
클래스 인덱스(고정): `NOT_ROI=0, NOT_DONE=1, PROPER=2, SLIGHTLY_BURNT=3, BURNT=4`.
고기 클래스(AI): `0 BEEF, 1 CHICKEN, 2 LAMB, 3 PORK` (label_map = class_id+1; 빌드시 실제 마스크로 확정).

## 1. `DonenessKernel` (두 방식 공유)
입력(동결 데이터형): `roi_mask: bool[H,W]`, `class_map: uint8[H,W] ∈ {0 NOT_ROI,1 NOT_DONE,2 PROPER,3 SLIGHTLY,4 BURNT}` — A·B가 공유 합성배열 단위테스트로 검증. 처리:
```
roi = max(roi_mask.sum(), 1)
pct_x = count_x * 100.0 / roi                         # x ∈ {proper, slightly_burnt, burnt}
# 보정 offset (0 floor) — v1 1회 적용, faithful_triple_offset 플래그로 3회 복원 가능
pct_burnt          = max(pct_burnt - 3.0, 0.0)
pct_slightly_burnt = max(pct_slightly_burnt - 1.5, 0.0)
pct_proper         = max(pct_proper - 5.0, 0.0)
cooking_score = pct_proper
```
`maillard_score`는 방식별(아래). roi==0 → 점수 0/NaN 가드(빈 ROI 계약 필수).
> offset 주의: C++ 글로벌은 픽셀카운트에서 재계산해 **1회만** 적용됨(OnnxInferenceOutput.h:81-90). 커널 글로벌 경로도 1회 적용(일치). `faithful_triple_offset`는 per-instance 요약 재현 전용.

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
**Step B — per-instance 도넨스 (scoring/ai.py + kernel)**
인스턴스: `connectedComponents(label_map==class_id+1, 8)`; `<500px` 제거. 각 인스턴스 ROI에 §4 규칙 cascade 적용.
**Step C — 글로벌**: BEEF(class 0) 인스턴스만 합산해 퍼센트 재계산 + offset. `maillard_score = proper*0.7 + slightly*1.5 + burnt*3.0`.

## 3. 조건문 방식 (BeefStripLoin America 충실)
**ROI mask** (v1 = GridBasedAlgorithm의 모폴로지 근사, 편차 문서화):
```
outer  = (v410<=30)&(v440<=30)&(v460<50)&(v520<85)
branchA= (v930>=30)&(v930<100)&(((v800-v650)>-30)|(v650>80))
hi = (v800>50)&(v800>=v410*4.0)
lo = (v800<=20)&(v800>=v410*5.0)&((v800-v410)>10)
mid= (~(v800>50))&(~(v800<=20))&(v800>=v410*5.0)&((v800-v410)>18)
acceptA= branchA & (hi|lo|mid)
branchB= (v930<30)&(v930>=20)&(v650<=25)&(v800>=v410*5.0)
roi = outer & (acceptA|branchB)   →  morphology CLOSE/OPEN + connectedComponents 유지
```
**픽셀 분류** (우선순위 burnt>slightly>proper, roi 한정):
```
burnt    = (v440<=10)&(v460<=10)&(v720<=20)&(v800<=30)&(v930>=20)
slightly = ~burnt & (v440<=10)&(v585<=20)&(v650<=30)&(v720<=30)&((v720*1.3)<=v930)&(v930>=35)
proper   = ~burnt & ~slightly & (v440<=10)&(v585<=20)&((v650/max(v440,0.1))>=4.0)
           &(v650>=30)&(v650<=50)&(v720>=50)&(v800>=40)&(v930>=40)
```
**점수**: `pct_x=count*100/max(roi,1)`; `pct_burnt = pct_burnt-3.0 if >3.0 else 0`; `cooking_score=pct_proper`;
`maillard_score = pct_proper*0.5 + pct_slightly_burnt*1.0 + pct_burnt*4.0`(deadband 후); `burnt_score=pre-deadband burnt%`.

> 라이브 `beef_strip_loin/ComponentRecognizer_BeefStripLoin_CharBroiler` 임계는 _America와 약간 다를 수 있음
> (gate `(v410<=10&v440<=15)|v410<=7|v440<=7`; burnt `v650<=30&v720<=40&v930>=50` 등). 빌드시 라이브 파일로 최종 확정.

## 4. 메뉴별 규칙 테이블 (외부화, 전역상수 금지)
deadband: beef -3.0, pork_nape -2.0, pork_belly_herb -1.5. pork는 파장 460/520/620/840/930/585/650 사용.
미정의 메뉴(t_bone/l_bone/Combo/galbi/ddeokgalbi/data)는 "근사" 라벨 + 기본 규칙.

## 5. 등급 사다리 (데이터 구동, `{menu:(score_field, ladder)}`, grade 0=완료)
- Charcoalroom beef / `maillard_score`: >50→5, >30→**0**, >12→4, >8→3, >5→2, else 1
- Office chicken-thigh / `maillard_score`: >=27→4, >=20→**0**, >14→3, >7→2, else 1
- Kiyoung chicken / `slightly_burnt`: >=9→**0**, >6→2, >3→2, else 1
- Jungsooksung pork(복합): maillard>=35→**0**; elif burnt_score>10→**0**; elif maillard<10→1,<15→2,<20→3, else 4

## 6. band↔LED 정본 (빌드시 PropertiesDatabase로 확정)
정본(PropertiesDatabase.h:113-125): led0=410/420/415, led1=440/460/450, led2=460/480/470, led4=520/610/567, led5=585/595/590, led8=650/670/660, led9=720/750/**730**, led10=720/740/**740**, led11=800.., led12=840/870/850, led14=930.. .
meatSegNet 5ch = led 2,4,8,10,12 = 460/520/650/720(led10·peak740)/840. 도넨스 규칙 720 = **led10**.
**720nm 모호 → (min,max,peak)로 led9(730) vs led10(740) 구분**. PNG/JPEG 동일 band → **PNG 우선**. `999_999_999` 센티넬 드롭.
