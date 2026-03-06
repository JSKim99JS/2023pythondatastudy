from __future__ import annotations

import ast
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from layout_engine import (
    Department,
    aldep_generate_candidates,
    craft_optimize,
    evaluate_with_simpy,
    generate_grid_within_polygon,
)


st.set_page_config(page_title="공장 레이아웃 설계 시스템", layout="wide")
st.title("ALDEP + CRAFT + SimPy 기반 공장 레이아웃 설계")
st.caption("비정형 공장 부지에서 사용 가능 영역 선택 → 초기안 생성 → 스왑 최적화 → 시뮬레이션 검증")

with st.sidebar:
    st.header("설정")
    n_candidates = st.slider("초기 배치안 개수(ALDEP)", 10, 20, 12)
    top_k = st.slider("시뮬레이션 검증 후보 수", 1, 5, 3)

st.subheader("Input 1) 부서 정보")
default_dept = pd.DataFrame(
    {
        "name": ["CUT", "WELD", "PAINT", "ASSY", "PACK"],
        "area": [8, 10, 6, 12, 7],
    }
)
dept_df = st.data_editor(default_dept, use_container_width=True, num_rows="dynamic")

st.subheader("Input 2) ARC 점수 (친밀도)")
st.write("형식: [(\"CUT\",\"WELD\",6), (\"WELD\",\"ASSY\",8)]")
arc_raw = st.text_area(
    "ARC 리스트",
    value='[("CUT","WELD",6),("WELD","ASSY",8),("ASSY","PACK",7),("PAINT","ASSY",5)]',
)

st.subheader("Input 3) Flow 데이터")
st.write("형식: [(\"CUT\",\"WELD\",20), (\"ASSY\",\"PACK\",35)]")
flow_raw = st.text_area(
    "Flow 리스트",
    value='[("CUT","WELD",20),("WELD","PAINT",10),("PAINT","ASSY",24),("ASSY","PACK",35)]',
)

st.subheader("Input 4) 비정형 공장 부지")
st.write("부지 꼭짓점 형식: [(0,0),(15,0),(15,7),(8,12),(0,8)]")
polygon_raw = st.text_input("부지 폴리곤", value="[(0,0),(15,0),(15,7),(8,12),(0,8)]")



def parse_triplets(raw: str) -> List[Tuple[str, str, float]]:
    data = ast.literal_eval(raw)
    return [(str(a), str(b), float(v)) for a, b, v in data]


if st.button("레이아웃 생성 및 검증", type="primary"):
    try:
        departments = [Department(name=row["name"], area=float(row["area"])) for _, row in dept_df.iterrows()]
        arc_pairs = parse_triplets(arc_raw)
        flow_pairs = parse_triplets(flow_raw)
        polygon = [(float(x), float(y)) for x, y in ast.literal_eval(polygon_raw)]

        arc_scores: Dict[Tuple[str, str], float] = {
            tuple(sorted((a, b))): s for a, b, s in arc_pairs
        }
        flow: Dict[Tuple[str, str], float] = {(a, b): v for a, b, v in flow_pairs}

        usable_points = generate_grid_within_polygon(polygon, grid_step=1.0)

        candidates = aldep_generate_candidates(
            departments=departments,
            arc_scores=arc_scores,
            usable_points=usable_points,
            n_candidates=n_candidates,
        )

        optimized = [craft_optimize(c, flow=flow, max_iters=150) for c in candidates]
        optimized = sorted(optimized, key=lambda x: x.score)

        st.success(f"ALDEP {n_candidates}개 생성, CRAFT 최적화 완료")
        top_candidates = optimized[:top_k]

        rows = []
        best_layout = None
        best_metric = float("inf")
        for i, cand in enumerate(top_candidates, start=1):
            sim = evaluate_with_simpy(cand, flow=flow)
            metric = cand.score + sim.avg_lead_time * 2
            rows.append(
                {
                    "candidate": i,
                    "cost": round(cand.score, 3),
                    "rho": round(sim.utilization, 3),
                    "lead_time": round(sim.avg_lead_time, 3),
                    "composite_metric": round(metric, 3),
                }
            )
            if metric < best_metric:
                best_metric = metric
                best_layout = cand

        st.subheader("Output) 후보안 성과")
        st.dataframe(pd.DataFrame(rows), use_container_width=True)

        if best_layout is not None:
            st.subheader("최적 레이아웃 평면도")
            fig, ax = plt.subplots(figsize=(8, 6))
            px, py = zip(*polygon)
            ax.fill(px + (px[0],), py + (py[0],), alpha=0.2, label="Factory Site")

            ux, uy = zip(*usable_points)
            ax.scatter(ux, uy, s=8, alpha=0.15, color="gray", label="Usable grid")

            for name, (x, y) in best_layout.positions.items():
                ax.scatter([x], [y], s=120)
                ax.text(x + 0.1, y + 0.1, name, fontsize=10)

            for (a, b), v in flow.items():
                if a in best_layout.positions and b in best_layout.positions:
                    x1, y1 = best_layout.positions[a]
                    x2, y2 = best_layout.positions[b]
                    ax.plot([x1, x2], [y1, y2], linewidth=max(0.5, v / 10), alpha=0.4)

            ax.set_title("Best Candidate Layout")
            ax.set_xlabel("X")
            ax.set_ylabel("Y")
            ax.legend(loc="upper right")
            ax.set_aspect("equal", adjustable="box")
            st.pyplot(fig)

    except Exception as e:
        st.error(f"입력 파싱 또는 연산 중 오류: {e}")
