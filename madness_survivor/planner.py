from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

from .models import Team
from .simulator import SimulationSummary
import logging
logger = logging.getLogger(__name__)


@dataclass(order=True)
class PlanCandidate:
    sort_key: Tuple[float, float] = field(init=False, repr=False)
    log_survival_score: float
    seed_sum: int
    picks: List[Tuple[int, str, float]]  # (day, team, win_prob)
    used: Set[str]

    def __post_init__(self) -> None:
        self.sort_key = (self.log_survival_score, self.seed_sum)


def build_survivor_plan(
    teams: Dict[str, Team],
    summary: SimulationSummary,
    start_day: int = 1,
    used_teams: Set[str] | None = None,
    beam_width: int = 500,
    candidates_per_day: int = 8,
    min_prob: float = 1e-6,
) -> List[PlanCandidate]:
    used_teams = set() if used_teams is None else set(used_teams)
    max_day = max(summary.win_prob_by_day.keys())

    beam: List[PlanCandidate] = [
        PlanCandidate(
            log_survival_score=0.0,
            seed_sum=0,
            picks=[],
            used=set(used_teams),
        )
    ]
    
    logger.info("Starting survivor plan optimization")
    for day in range(start_day, max_day + 1):
        logger.info("Planning picks for contest day %d", day)
        probs = summary.win_prob_by_day.get(day, {})
        ranked_candidates = sorted(
            ((team, p) for team, p in probs.items() if p > min_prob),
            key=lambda x: (x[1], teams[x[0]].seed),
            reverse=True,
        )[:candidates_per_day]

        new_beam: List[PlanCandidate] = []

        for plan in beam:
            expanded = False
            for team, p in ranked_candidates:
                if team in plan.used:
                    continue

                # Avoid impossible/meaningless picks
                if p <= 0.0:
                    continue

                expanded = True
                new_picks = plan.picks + [(day, team, p)]
                new_used = set(plan.used)
                new_used.add(team)

                new_beam.append(
                    PlanCandidate(
                        log_survival_score=plan.log_survival_score + math.log(max(p, min_prob)),
                        seed_sum=plan.seed_sum + teams[team].seed,
                        picks=new_picks,
                        used=new_used,
                    )
                )

            # If no legal candidate was found, keep a dead-end placeholder so caller can inspect
            if not expanded:
                new_beam.append(plan)

        new_beam.sort(reverse=True)
        beam = new_beam[:beam_width]

    beam.sort(reverse=True)
    logger.info("Planning complete. Best plans generated: %d", len(beam))
    return beam


def summarize_first_pick_options(
    plans: List[PlanCandidate],
    top_n: int = 5,
) -> List[Tuple[str, float, int]]:
    first_pick_best: Dict[str, Tuple[float, int]] = {}

    for plan in plans:
        if not plan.picks:
            continue
        _, team, _ = plan.picks[0]
        current = first_pick_best.get(team)
        candidate = (plan.log_survival_score, plan.seed_sum)
        if current is None or candidate > current:
            first_pick_best[team] = candidate

    ranked = sorted(
        ((team, vals[0], vals[1]) for team, vals in first_pick_best.items()),
        key=lambda x: (x[1], x[2]),
        reverse=True,
    )

    return ranked[:top_n]


def format_plan_table(
    teams: Dict[str, Team],
    plans: List[PlanCandidate],
    top_alternatives: int = 5,
) -> str:
    if not plans:
        return "No feasible plan found."

    best = plans[0]
    lines: List[str] = []

    survival_estimate = math.exp(best.log_survival_score)

    lines.append("BEST PLAN")
    lines.append("=" * 72)
    lines.append(f"Approx. survive-all-days score: {survival_estimate:.6f}")
    lines.append(f"Seed tiebreak total:           {best.seed_sum}")
    lines.append("")

    lines.append(f"{'Day':<6}{'Pick':<28}{'Seed':<8}{'Win Prob':<12}")
    lines.append("-" * 72)

    for day, team, p in best.picks:
        lines.append(f"{day:<6}{team:<28}{teams[team].seed:<8}{p:<12.4%}")

    lines.append("")
    lines.append("TOP FIRST-PICK ALTERNATIVES")
    lines.append("=" * 72)

    for idx, (team, log_score, seed_sum) in enumerate(
        summarize_first_pick_options(plans, top_n=top_alternatives), start=1
    ):
        lines.append(
            f"{idx}. {team:<24} "
            f"survive-score≈{math.exp(log_score):.6f} "
            f"seed_total={seed_sum}"
        )

    return "\n".join(lines)