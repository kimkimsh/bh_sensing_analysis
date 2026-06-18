# DEMO_SCRIPT — 6-beat 60초 골든패스 (Phase-0 FROZEN)

> Stream D 빌드 **전**에 동결되는 데모 대본. **Phase-2 통합자는 이 경로의 버그만 수정**(전체가 아님).
> Demo Mode(F-D5)가 이 6-beat를 번호 `st.status`/`st.info` 캡션으로 구동한다. 상세 `DESIGN_SPEC §10`.

## 큐레이션 capture (확정 — Phase-0 게이트 통과)
`260612_office_backup/206/beef/striploin/250903` (device 206, posIdx 1, 10밴드).
⚠️ **Phase-0 육안검증 게이트 실행 결과**: 잠정 `251016`은 실추론에서 **AI 검출 0개**(objmax 0.079, 평탄 스펙트럼 = 고기 신호 없음)로 hero가 비어 **폐기**. 실추론 검증으로 `250903` 채택(ONNX-ROI 32991px vs Rule-ROI 30576px, **IoU 0.893, areaΔ +2415** — 강한 일치 + 가시적 불일치, BEEF-only). 대안: 251021(IoU 0.889)·250923(IoU 0.816, 최대 분리). 폐기된 `251016`은 empty-AI-ROI 가드 경로 fixture로 보존.

## 6 beats (~60초)
1. **Hook (~8s)** — "핏마스터는 숯불 위 스테이크의 굽기를 *눈*으로 판정합니다. 그걸 11개 파장으로 정량화하면?"
2. **Frame (~8s)** — 실제 BEEF striploin mono 프레임(ch3/led10)을 띄운다. "이게 센서가 보는 것 — 흑백 멀티스펙트럼."
3. **Hero reveal (~12s)** — ROI-diff overlap-map 공개. "AI 세그멘테이션(cyan)과 규칙 ROI(magenta)가 *어디서* 갈리는지." (wow 모먼트)
4. **The ONE number (~12s)** — KPI 캡션 한 줄: `IoU 0.93 · area Δ +X px`. "같은 굽기 규칙. 더 깨끗한 AI ROI. **무튜닝.**" (정확도 아님 — *일치도*)
5. **Why it matters (~12s)** — "11개 파장 → **AI가 고기를 분할(segments), 규칙이 굽기를 판정(decide)**. 메뉴별 규칙 재튜닝 없이 ROI만 더 깨끗해짐."
6. **Close (~8s)** — "정답 라벨은 없습니다. 그래서 '더 정확'이 아니라 '두 방식이 어디서 일치/불일치하는가'를 정직하게 보여줍니다."

## 카피 가드 (DESIGN_SPEC §11)
- "정확/더 나음/맞음" 금지 → 항상 "agreement / 일치도".
- "AI doneness" 금지 (AI는 ROI 전용).
- 델타는 sign-only·중립색·승자 표기 없음.
