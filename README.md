# 공장 레이아웃 설계 프로그램 (Python)

비정형 공장 부지를 입력받아 아래 흐름으로 설비 배치를 탐색합니다.

1. **부지 사용 가능 영역 선택**: 폴리곤 내부 격자 포인트 추출
2. **ALDEP**: 초기 배치안 10~20개 자동 생성
3. **CRAFT**: 위치 스왑으로 물류비(Flow × 거리) 최소화
4. **SimPy**: 가동률(ρ), 평균 리드타임 검증
5. **Output**: 최적 레이아웃 평면도 + 후보별 성과 표

## 실행

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 입력 형식

- 부서 테이블: `name`, `area`
- ARC: `[("CUT","WELD",6), ...]`
- Flow: `[("CUT","WELD",20), ...]`
- 비정형 부지 폴리곤: `[(0,0),(15,0),(15,7),(8,12),(0,8)]`

## 파일 구성

- `app.py`: Streamlit UI + 시각화
- `layout_engine.py`: 부지 선택, ALDEP, CRAFT, SimPy 로직
