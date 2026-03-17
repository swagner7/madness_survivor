from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

from .models import Team
from .simulator import SimulationSummary

logger = logging.getLogger(__name__)


@dataclass(order=True)
class PlanCandidate:
    sort_key: Tuple[float, float] = field(init=False, repr=False)
    log_survival_score: float
    seed_sum: int
    # (day, team, reach_day_prob, game_win_if_available, pick_success_prob, cumulative_survival)
    picks: List[Tuple[int, str, float, float, float, float]]
    used: Set[str] = field(compare=False)
    alive_sim_mask: int = field(compare=False, repr=False)
    surviving_sim_count: int = field(compare=False)

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
    if not summary.team_day_win_sim_masks or not summary.team_day_appearance_sim_masks:
        raise ValueError(
            "SimulationSummary is missing required simulation masks. "
            "run_simulations() must be used to generate a planning corpus."
        )

    logger.info("Starting survivor plan optimization")

    used_teams = set() if used_teams is None else set(used_teams)
    max_day = max(summary.win_prob_by_day.keys())
    all_sims_mask = (1 << summary.total_sims) - 1

    beam: List[PlanCandidate] = [
        PlanCandidate(
            log_survival_score=0.0,
            seed_sum=0,
            picks=[],
            used=set(used_teams),
            alive_sim_mask=all_sims_mask,
            surviving_sim_count=summary.total_sims,
        )
    ]

    for day in range(start_day, max_day + 1):
        logger.info("Planning picks for contest day %d", day)

        day_team_win_masks = summary.team_day_win_sim_masks.get(day, {})
        day_team_appearance_masks = summary.team_day_appearance_sim_masks.get(day, {})
        new_beam: List[PlanCandidate] = []

        for plan in beam:
            if plan.surviving_sim_count == 0:
                continue

            candidate_rows: List[Tuple[str, float, float, float, float, int, int]] = []

            for team, team_win_mask in day_team_win_masks.items():
                if team in plan.used:
                    continue

                team_appearance_mask = day_team_appearance_masks.get(team, 0)
                if team_appearance_mask == 0:
                    continue

                reachable_mask = plan.alive_sim_mask & team_appearance_mask
                reachable_count = reachable_mask.bit_count()
                if reachable_count == 0:
                    continue

                next_alive_mask = plan.alive_sim_mask & team_win_mask
                next_count = next_alive_mask.bit_count()
                if next_count == 0:
                    continue

                reach_day_prob = reachable_count / plan.surviving_sim_count
                game_win_if_available = next_count / reachable_count
                pick_success_prob = next_count / plan.surviving_sim_count
                cumulative_survival = next_count / summary.total_sims

                if pick_success_prob < min_prob:
                    continue

                candidate_rows.append(
                    (
                        team,
                        reach_day_prob,
                        game_win_if_available,
                        pick_success_prob,
                        cumulative_survival,
                        next_count,
                        next_alive_mask,
                    )
                )

            candidate_rows.sort(
                key=lambda x: (x[3], x[1], teams[x[0]].seed),
                reverse=True,
            )
            candidate_rows = candidate_rows[:candidates_per_day]

            for (
                team,
                reach_day_prob,
                game_win_if_available,
                pick_success_prob,
                cumulative_survival,
                next_count,
                next_alive_mask,
            ) in candidate_rows:
                new_used = set(plan.used)
                new_used.add(team)

                new_picks = plan.picks + [
                    (
                        day,
                        team,
                        reach_day_prob,
                        game_win_if_available,
                        pick_success_prob,
                        cumulative_survival,
                    )
                ]

                new_beam.append(
                    PlanCandidate(
                        log_survival_score=plan.log_survival_score + math.log(max(pick_success_prob, min_prob)),
                        seed_sum=plan.seed_sum + teams[team].seed,
                        picks=new_picks,
                        used=new_used,
                        alive_sim_mask=next_alive_mask,
                        surviving_sim_count=next_count,
                    )
                )

        if not new_beam:
            logger.warning("No feasible plans remain on day %d", day)
            return []

        new_beam.sort(reverse=True)
        beam = new_beam[:beam_width]
        logger.debug("Beam size after pruning: %d", len(beam))

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
        _, team, _, _, _, _ = plan.picks[0]
        candidate = (plan.log_survival_score, plan.seed_sum)
        current = first_pick_best.get(team)
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

    survival_estimate = best.picks[-1][5] if best.picks else 0.0

    lines.append("BEST PLAN")
    lines.append("=" * 140)
    lines.append(f"Approx. survive-all-days score: {survival_estimate:.6f}")
    lines.append(f"Seed tiebreak total:           {best.seed_sum}")
    lines.append("")
    lines.append(
        f"{'Day':<5}"
        f"{'Pick':<24}"
        f"{'Seed':<6}"
        f"{'Reach Day':<12}"
        f"{'Game Win If Avail':<19}"
        f"{'Pick Success':<14}"
        f"{'Survive Through Day':<20}"
    )
    lines.append("-" * 140)

    for day, team, reach_day_prob, game_win_if_available, pick_success_prob, cumulative_survival in best.picks:
        lines.append(
            f"{day:<5}"
            f"{team:<24}"
            f"{teams[team].seed:<6}"
            f"{reach_day_prob:<12.4%}"
            f"{game_win_if_available:<19.4%}"
            f"{pick_success_prob:<14.4%}"
            f"{cumulative_survival:<20.4%}"
        )

    lines.append("")
    lines.append("TOP FIRST-PICK ALTERNATIVES")
    lines.append("=" * 140)

    for idx, (team, log_score, seed_sum) in enumerate(
        summarize_first_pick_options(plans, top_n=top_alternatives), start=1
    ):
        lines.append(
            f"{idx}. {team:<24} "
            f"survive-score≈{math.exp(log_score):.6f} "
            f"seed_total={seed_sum}"
        )

    return "\n".join(lines)