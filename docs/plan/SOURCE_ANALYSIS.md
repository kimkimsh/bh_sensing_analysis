# SOURCE_ANALYSIS — 원본 C++ 센싱 서브시스템 검증 분석

원본: `/home/bh-mark-samsung/workspace/bh_chef_engine_charBroilerBot_revised` (header-only C++, ONNX Runtime).
아래 사실은 **실제 파일을 직접 읽어 확인**(cross-reference)했으며 파일:라인을 명시한다. 병렬 분석 워크플로(10 agents)가 교차 확인.

---

## 1. 전체 센싱 흐름

```
캡처(11 파장 raw) ─▶ [exlight_remover] 광 보정 ─▶ per-LED calibration ─▶ calibrated 스펙트럼 프레임
   ─▶ [meatSegNet] 고기 인스턴스/ROI 분할(고기 종류 4클래스) ─▶ label_map(0=bg,1..4)
   ─▶ per-instance 도넨스 분류(스펙트럼 규칙) ─▶ 픽셀 카운트 ─▶ 퍼센트/offset/점수 ─▶ 시각화
```

`AlgorithmManager::getOnnxInferenceOutput` 가 `OnnxROIRecognizer` → `OnnxComponentRecognizer` → `OnnxInferenceOutput` 순으로 호출 (`AlgorithmManager.h:3137-3154`).

---

## 2. 세 개의 ONNX 모델 (역할이 전부 다름)

| 모델 | 역할 | 입력/출력 | 우리 보유 |
|------|------|-----------|-----------|
| `exlight_remover_e32_int8.onnx` | 캡처시 광 보정(복원) | in `a[B,1,H,W]`+`raw[B,11,H,W]` → out `pred[1,11,H,W]` | ✅ (v1 미사용) |
| `meatSegNet_best.onnx` (+`.onnx.data` 134MB) | **고기 종류 인스턴스 분할/ROI** | in `input[B,5,480,640]` → `preds[B,6300,41]`,`protos[B,32,120,160]` | ✅ |
| `Merge_Main_Model_241105.onnx` | **픽셀단위 도넨스 MLP**(7파장→4클래스) | per-pixel 7-vec → 4 logits | ❌ **없음** |

- exlight 로드: `CameraController.cc:314` (`bh_initAIModel`), 배치 추론 `AIImageProcessor.cc:91-201` (`AI_MODEL_CHANNELS=11`).
- meatSegNet 로드 경로 `./ai_model/meatSegNet_best.onnx` (`OnnxROIRecognizer.h:39`), 미존재 시 규칙기반 ROI fallback (`:42-57`).
- 도넨스 MLP는 `ComponentRecognizer_BeefStripLoin_America_CharBroiler_AI.h:29` (`./ai_model/Merge_Main_Model_241105.onnx`), 미존재 시 규칙 fallback (`:32-44`). **단 이 _America AI 경로는 라이브 `OnnxComponentRecognizer` 경로가 아님.**

> **결론(직접 검증)**: 라이브 sensing 흐름(`BaseRobotTaskSensing.h:93`, `mainwindow.cpp:1747`)이 `getOnnxInferenceOutput` 호출 → ONNX는 **분할(ROI)** 만, 도넨스는 **규칙**. `Merge_Main_Model` 경로(`recognizeComponentAI`, `AlgorithmManager.h:1824-2412`)는 **라이브 미호출**(별도 레거시 경로). 학습형 AI 도넨스는 본 도구 비범위(구 F-B5 **컷**).

---

## 3. meatSegNet (ROI/분할) — 검증

- 입력 채널: ledId **2→ch0, 4→ch1, 8→ch2, 10→ch3, 12→ch4** (`OnnxROIRecognizer.h:101-108`), 누락 채널 0 채움(`:111-114`), 정규화 `/255` (`:215`).
- `mCurrentAnalysisMap = ch3(led10)` 모노 배경으로 저장(`:137`), 결과 `mCurrentFilteredMask = label_map`(`:138`).
- YOLOv8-seg: `INPUT_W=640,INPUT_H=480,NUM_CLASSES=4,NUM_PROTOS=32` (`:65-69`). pred_dim=4+1+4+32=**41**.
  obj=sigmoid(p[4]) `CONF_THRESH=0.3`; cls=softmax(p[5:9]); final=obj·max; box decode(cx=ax+dx·s 등); coeffs=tanh(p[9:41]); per-class NMS `0.4`; proto 마스크 합성 후 `MASK_THRESH=0.35`, MORPH_CLOSE; `label_map[roi]=classId+1` (`:269-365`).
- **직접 재검증(Python)**: `input[batch,5,480,640]` → `preds[batch,6300,41]`,`protos[batch,32,120,160]`, 로드 0.36s. 6300 = strides{8,16,32}@640×480, 앵커 **y-major**(for y: for x).
- label_map 픽셀값: `0=배경,1=BEEF,2=CHICKEN,3=LAMB,4=PORK` (헤더 주석은 `1=BEEF,2=LAMB,3=PORK,4=CHICKEN`로 **모순** → 실제 마스크로 확정 필요. `OnnxComponentRecognizer.h:7-12`, `CLASS_NAMES`는 BEEF,CHICKEN,LAMB,PORK `:194`).

## 4. 도넨스 분류 (라이브 경로 = 규칙기반)

- `OnnxComponentRecognizer.doProcess`: label_map을 클래스별(`label==classId+1`)로 분리(`:82-87`), 8-연결 connectedComponents(`:94`), `MIN_INSTANCE_PIXELS=500` 미만 제거(`:102`), per-instance로 `getRecognizer(classId)`에 라우팅(`:199-209`): PORK→`ComponentRecognizer_PorkBelly_Charcoal_CharBroiler`, 그 외→`ComponentRecognizer_BeefStripLoin_CharBroiler`(규칙).
- 규칙 도넨스(`beef_strip_loin/ComponentRecognizer_BeefStripLoin_CharBroiler.h:112-158`, **직접 read 확정**)는 ROI 픽셀마다 게이트(410/440) + burnt/slightly/proper(살코기+지방 2분기) cascade로 판정. 9밴드 로드(410/440/460/520/585/650/720/800/930)하나 **임계엔 410/440/520/585/650/720/930만 사용**(460·800 미사용). 정확한 식·OOB버그·NOT_DONE 버킷은 `SCORING_SPEC §3`. (초기 문서가 옮긴 `_america` 변형과 게이트/임계/밴드 상이 — **라이브로 확정**.)
- `beef_strip_loin_america/ComponentRecognizer_..._CharBroiler.h:87-147` (직접 읽음)은 동일 패턴의 _America 변형(약간 다른 임계).

## 5. 점수 계약과 계산

- 공유 필드: `BaseInferenceOutput.h:24-38` — `mPixels_{roi,raw,not_done,proper,slightly_burnt,burnt}`, `mPercent_*`, `mPercent_maillard_score`, `mPercent_burnt_score`.
- 퍼센트 = 클래스픽셀/roi·100. **offset** `burnt-3 / slightly-1.5 / proper-5`(0 floor):
  - 인식기 `ComponentRecognizer_...:179-186`(burnt만) / 라이브 `OnnxComponentRecognizer.h:155-180`(셋 다) / 출력 `OnnxInferenceOutput.h:88-90`(셋 다) → **최대 3회 중복 적용**(충실도 편차).
- **글로벌은 BEEF 인스턴스(classId==0)만 합산** `OnnxInferenceOutput.h:67-86`.
- 합성 점수(**셋 상이, 직접 read**): AI 글로벌 `proper*0.7 + slightly*1.5 + burnt*3.0` (`OnnxInferenceOutput.h:93-95`); 라이브 beef 단일메뉴 `proper*1.0 + slightly*1.0 + burnt*3.0` (`InferenceOutput_ChefCooking_BeefStripLoin.h:16`); _america `proper*0.5 + slightly*1.0 + burnt*4.0`. → **직접비교 불가 → 비교축 per-class %, maillard는 양 방식 동일식(0.7/1.5/3.0) 단일방식 뷰 한정**(Codex 권고).
- 네이밍: Deep Maillard=`proper`, Slightly Charred=`slightly_burnt`, Carbonized=`burnt`.

## 6. 시각화 (오버레이 패리티)

- `OnnxVisualization::render`: ch3(led10) 모노 배경에 클래스색·도넨스색 알파블렌딩(class α=0.45, doneness α=0.30).
- 픽셀 우선순위: **burnt(빨강) > slightly(주황) > proper(초록) > 클래스색**. 클래스 인덱스 `label-1`로 BEEF/CHICKEN/LAMB/PORK 팔레트 참조.
- 권장 팔레트(BGR): BEEF `#0048AD`, CHICKEN `#EC7822`, LAMB `#DCDCDC`, PORK `#E6A0DC`; 도넨스 proper `#22EE0B` / slightly `#FFC800` / burnt `#FF0500`.

## 7. 데이터셋 (직접 검증)

- 경로: `data/<backup>/<deviceId>/<meat>/<cut>/<YYMMDD>/<file>`; 한 날짜 폴더 = position(1,5,6,9 등) × 11 band.
- 파일명: `ver2_charbroiler_calibrated_<meat>_<cut>_<YYMMDD>_<posIdx>_<wMin>_<wMax>_<wPeak>.png|jpeg`.
- band 인벤토리: **capture별 8–16 band 가변**. beef striploin도 날짜별 8~16 band이며 **일부 capture는 620(620_630_625) 포함**(초기 가정 'beef=10·620없음'은 디스크 검증으로 반증). `band_count` 고정 가정 금지. 라벨/마스크 0개.
- 총 ~33,682 프레임 ≈ **~2.8k–3.0k captures**(그루핑 정의에 따라 2,817~2,961; 스캔 시 결정적 계산, 박제 금지). meatSegNet ~0.26s/추론 → 전수 AI ≈ 13–15분.

## 8. 검증 안 된 채 남긴 항목 (빌드 중 확정)
(a) label_map 클래스 인코딩 정본(주석 vs 팔레트 모순) — 실제 마스크로. (b) LED↔(min,max,peak) 정본표 — `PropertiesDatabase.h`. (c) GridBasedAlgorithm ROI 정확 식(모폴로지 근사 채택). (d) 3중 offset 복원 여부.
