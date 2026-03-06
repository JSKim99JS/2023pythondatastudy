from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple
import math
import random

import matplotlib.path as mpath
import numpy as np


@dataclass
class Department:
    name: str
    area: float


@dataclass
class LayoutCandidate:
    positions: Dict[str, Tuple[float, float]]
    score: float


@dataclass
class SimulationResult:
    utilization: float
    avg_lead_time: float


def generate_grid_within_polygon(
    polygon: List[Tuple[float, float]],
    grid_step: float = 1.0,
) -> List[Tuple[float, float]]:
    """Return grid points that are inside a non-rectangular factory site."""
    if len(polygon) < 3:
        raise ValueError("polygon requires at least 3 points")

    poly_path = mpath.Path(np.array(polygon))
    xs, ys = zip(*polygon)
    min_x, max_x = math.floor(min(xs)), math.ceil(max(xs))
    min_y, max_y = math.floor(min(ys)), math.ceil(max(ys))

    points: List[Tuple[float, float]] = []
    x = min_x
    while x <= max_x:
        y = min_y
        while y <= max_y:
            if poly_path.contains_point((x, y)):
                points.append((x, y))
            y += grid_step
        x += grid_step

    if not points:
        raise ValueError("No usable area found within polygon")
    return points


def _weighted_random_order(departments: List[Department], rng: random.Random) -> List[Department]:
    remaining = departments[:]
    ordered: List[Department] = []
    while remaining:
        total_area = sum(d.area for d in remaining)
        r = rng.uniform(0, total_area)
        acc = 0.0
        for i, dep in enumerate(remaining):
            acc += dep.area
            if r <= acc:
                ordered.append(dep)
                remaining.pop(i)
                break
    return ordered


def aldep_generate_candidates(
    departments: List[Department],
    arc_scores: Dict[Tuple[str, str], float],
    usable_points: List[Tuple[float, float]],
    n_candidates: int = 15,
    seed: int = 42,
) -> List[LayoutCandidate]:
    """Generate initial alternatives (10~20 typical) using simple ALDEP-like heuristic."""
    if n_candidates < 1:
        raise ValueError("n_candidates must be >= 1")
    if len(usable_points) < len(departments):
        raise ValueError("Not enough usable points for all departments")

    rng = random.Random(seed)
    candidates: List[LayoutCandidate] = []

    for _ in range(n_candidates):
        order = _weighted_random_order(departments, rng)
        available = usable_points[:]
        rng.shuffle(available)

        positions: Dict[str, Tuple[float, float]] = {}
        for dep in order:
            best_point = None
            best_gain = -float("inf")
            sample = available[: min(30, len(available))]
            for pt in sample:
                gain = 0.0
                for placed_name, ppos in positions.items():
                    key = tuple(sorted((dep.name, placed_name)))
                    closeness = arc_scores.get(key, 0.0)
                    dist = euclidean_distance(pt, ppos)
                    gain += closeness / max(dist, 0.5)
                if gain > best_gain:
                    best_gain = gain
                    best_point = pt

            chosen = best_point if best_point is not None else available[0]
            positions[dep.name] = chosen
            available.remove(chosen)

        score = layout_cost(positions, flow={})
        candidates.append(LayoutCandidate(positions=positions, score=score))

    return candidates


def layout_cost(
    positions: Dict[str, Tuple[float, float]],
    flow: Dict[Tuple[str, str], float],
) -> float:
    cost = 0.0
    for (a, b), f in flow.items():
        if a not in positions or b not in positions:
            continue
        cost += f * euclidean_distance(positions[a], positions[b])
    return cost


def craft_optimize(
    candidate: LayoutCandidate,
    flow: Dict[Tuple[str, str], float],
    max_iters: int = 200,
) -> LayoutCandidate:
    """Swap locations iteratively until material handling cost cannot be improved."""
    names = list(candidate.positions.keys())
    pos = dict(candidate.positions)
    best_cost = layout_cost(pos, flow)

    improved = True
    iters = 0
    while improved and iters < max_iters:
        improved = False
        iters += 1
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a, b = names[i], names[j]
                pos[a], pos[b] = pos[b], pos[a]
                c = layout_cost(pos, flow)
                if c + 1e-9 < best_cost:
                    best_cost = c
                    improved = True
                else:
                    pos[a], pos[b] = pos[b], pos[a]
    return LayoutCandidate(positions=pos, score=best_cost)


def evaluate_with_simpy(
    candidate: LayoutCandidate,
    flow: Dict[Tuple[str, str], float],
    horizon: int = 480,
    seed: int = 42,
) -> SimulationResult:
    import simpy

    rng = random.Random(seed)
    env = simpy.Environment()
    station_capacity = max(1, len(candidate.positions) // 3)
    station = simpy.Resource(env, capacity=station_capacity)

    total_busy = 0.0
    lead_times: List[float] = []

    def part_process(pair: Tuple[str, str], volume: float):
        nonlocal total_busy
        source, sink = pair
        n_jobs = max(1, int(volume / 5))
        for _ in range(n_jobs):
            arrival = env.now
            with station.request() as req:
                yield req
                travel = euclidean_distance(candidate.positions[source], candidate.positions[sink])
                service = max(0.5, rng.expovariate(1 / (travel + 1)))
                total_busy += service
                yield env.timeout(service)
            lead_times.append(env.now - arrival)

    for pair, vol in flow.items():
        if pair[0] in candidate.positions and pair[1] in candidate.positions:
            env.process(part_process(pair, vol))

    env.run(until=horizon)

    utilization = min(1.0, total_busy / (horizon * station_capacity))
    avg_lead_time = float(np.mean(lead_times)) if lead_times else 0.0
    return SimulationResult(utilization=utilization, avg_lead_time=avg_lead_time)


def euclidean_distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
