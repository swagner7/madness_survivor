from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass
from typing import Dict, List, Sequence, Set, Tuple

from .models import Game, Team
from .planner import PlanCandidate
from .simulator import SimulationSummary, simulate_once

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OpponentModelConfig:
    chalkiness: float = 7.0
    seed_bias: float = 0.0
    randomness: float = 1.0
    candidates_per_day: int = 8


@dataclass(frozen=True)
class EntryOutcome:
    survived_days: int
    seed_sum_scored: int
    eliminated_on_day: int | None
    survived_all_days: bool


@dataclass(frozen=True)
class CandidateFieldScore:
    candidate_index: int
    contest_win_rate: float
    survive_all_rate: float
    avg_survived_days: float
    avg_seed_sum_scored: float
    plan: PlanCandidate


def _weighted_choice(
    rng: random.Random,
    items: Sequence[Tuple[str, float]],
) -> str:
    if not items:
        raise ValueError("Cannot sample from an empty list.")

    total = sum(weight for _, weight in items)
    if total <= 0:
        return items[0][0]

    x = rng.random() * total
    cumulative = 0.0
    for item, weight in items:
        cumulative += weight
        if x <= cumulative:
            return item
    return items[-1][0]


def _opponent_pick_weights_for_day(
    teams: Dict[str, Team],
    summary: SimulationSummary,
    used_teams: Set[str],
    day: int,
    config: OpponentModelConfig,
) -> List[Tuple[str, float]]:
    day_probs = summary.win_prob_by_day.get(day, {})
    if not day_probs:
        return []

    ranked = sorted(
        (
            (team, prob)
            for team, prob in day_probs.items()
            if team not in used_teams and prob > 0.0
        ),
        key=lambda x: (x[1], teams[x[0]].seed),
        reverse=True,
    )[: config.candidates_per_day]

    if not ranked:
        return []

    max_seed = max(team.seed for team in teams.values())
    randomness = max(config.randomness, 1e-9)

    weighted: List[Tuple[str, float]] = []
    for team, win_prob in ranked:
        # Chalkiness > 1 concentrates opponents on favorites.
        prob_component = max(win_prob, 1e-12) ** (config.chalkiness / randomness)

        # Positive seed_bias nudges toward larger seed numbers for tiebreak greed.
        seed_component = 1.0
        if config.seed_bias != 0.0:
            normalized_seed = teams[team].seed / max_seed
            seed_component = max(normalized_seed, 1e-12) ** config.seed_bias

        weight = prob_component * seed_component
        weighted.append((team, weight))

    return weighted


def sample_opponent_plan(
    teams: Dict[str, Team],
    summary: SimulationSummary,
    rng: random.Random,
    config: OpponentModelConfig,
    start_day: int,
    used_teams: Set[str] | None = None,
) -> PlanCandidate:
    used = set() if used_teams is None else set(used_teams)
    max_day = max(summary.win_prob_by_day.keys())

    picks: List[Tuple[int, str, float]] = []
    seed_sum = 0
    log_survival_score = 0.0

    for day in range(start_day, max_day + 1):
        weighted = _opponent_pick_weights_for_day(
            teams=teams,
            summary=summary,
            used_teams=used,
            day=day,
            config=config,
        )
        if not weighted:
            break

        team = _weighted_choice(rng, weighted)
        day_prob = summary.win_prob_by_day[day][team]

        picks.append((day, team, day_prob))
        used.add(team)
        seed_sum += teams[team].seed
        log_survival_score += math.log(max(day_prob, 1e-12))

    return PlanCandidate(
        log_survival_score=log_survival_score,
        seed_sum=seed_sum,
        picks=picks,
        used=used,
    )


def evaluate_plan_against_realization(
    teams: Dict[str, Team],
    plan: PlanCandidate,
    realized_day_winners: Dict[int, List[str]],
) -> EntryOutcome:
    survived_days = 0
    seed_sum_scored = 0
    eliminated_on_day: int | None = None

    for day, team, _ in plan.picks:
        seed_sum_scored += teams[team].seed

        winners = realized_day_winners.get(day, [])
        if team in winners:
            survived_days += 1
            continue

        eliminated_on_day = day
        return EntryOutcome(
            survived_days=survived_days,
            seed_sum_scored=seed_sum_scored,
            eliminated_on_day=eliminated_on_day,
            survived_all_days=False,
        )

    return EntryOutcome(
        survived_days=survived_days,
        seed_sum_scored=seed_sum_scored,
        eliminated_on_day=None,
        survived_all_days=True,
    )


def _fractional_win_share(
    user_outcome: EntryOutcome,
    opponent_outcomes: Sequence[EntryOutcome],
) -> float:
    """
    Returns the fraction of the contest won by the user in this simulation.
    If the user is uniquely best, result is 1.0.
    If tied for best with k total entries, result is 1/k.
    Otherwise 0.0.
    """
    all_outcomes = [user_outcome, *opponent_outcomes]

    def ranking_key(outcome: EntryOutcome) -> Tuple[int, int]:
        return outcome.survived_days, outcome.seed_sum_scored

    best_key = max(ranking_key(o) for o in all_outcomes)
    user_key = ranking_key(user_outcome)

    if user_key != best_key:
        return 0.0

    num_tied_best = sum(1 for o in all_outcomes if ranking_key(o) == best_key)
    return 1.0 / num_tied_best


def score_candidate_plans_vs_field(
    teams: Dict[str, Team],
    games: List[Game],
    summary: SimulationSummary,
    candidate_plans: Sequence[PlanCandidate],
    *,
    field_size: int,
    n_field_sims: int,
    start_day: int = 1,
    seed: int = 123,
    scale: float = 11.0,
    opponent_config: OpponentModelConfig | None = None,
    used_teams: Set[str] | None = None,
) -> List[CandidateFieldScore]:
    if field_size < 1:
        raise ValueError("field_size must be at least 1 (including your own entry).")

    if not candidate_plans:
        return []

    config = opponent_config or OpponentModelConfig()
    used_teams = set() if used_teams is None else set(used_teams)
    rng = random.Random(seed)

    logger.info("Starting field simulation")
    logger.info("Candidate plans: %d", len(candidate_plans))
    logger.info("Field size: %d", field_size)
    logger.info("Field simulations: %d", n_field_sims)
    logger.info(
        "Opponent model | chalkiness=%.3f seed_bias=%.3f randomness=%.3f candidates_per_day=%d",
        config.chalkiness,
        config.seed_bias,
        config.randomness,
        config.candidates_per_day,
    )

    total_days = 0
    if candidate_plans and candidate_plans[0].picks:
        total_days = len(candidate_plans[0].picks)

    win_share_totals = [0.0 for _ in candidate_plans]
    survive_all_counts = [0 for _ in candidate_plans]
    survived_days_totals = [0.0 for _ in candidate_plans]
    seed_sum_totals = [0.0 for _ in candidate_plans]

    progress_interval = max(1, n_field_sims // 10)

    for sim_idx in range(n_field_sims):
        if sim_idx % progress_interval == 0:
            logger.info("Field simulation progress: %d / %d", sim_idx, n_field_sims)

        _, realized_day_winners, _ = simulate_once(
            teams=teams,
            games=games,
            rng=rng,
            scale=scale,
        )

        opponent_plans = [
            sample_opponent_plan(
                teams=teams,
                summary=summary,
                rng=rng,
                config=config,
                start_day=start_day,
                used_teams=used_teams,
            )
            for _ in range(field_size - 1)
        ]

        opponent_outcomes = [
            evaluate_plan_against_realization(
                teams=teams,
                plan=opp_plan,
                realized_day_winners=realized_day_winners,
            )
            for opp_plan in opponent_plans
        ]

        for idx, plan in enumerate(candidate_plans):
            user_outcome = evaluate_plan_against_realization(
                teams=teams,
                plan=plan,
                realized_day_winners=realized_day_winners,
            )

            win_share = _fractional_win_share(user_outcome, opponent_outcomes)

            win_share_totals[idx] += win_share
            survived_days_totals[idx] += user_outcome.survived_days
            seed_sum_totals[idx] += user_outcome.seed_sum_scored

            if user_outcome.survived_all_days and user_outcome.survived_days == total_days:
                survive_all_counts[idx] += 1

    logger.info("Field simulation complete")

    scored: List[CandidateFieldScore] = []
    for idx, plan in enumerate(candidate_plans):
        scored.append(
            CandidateFieldScore(
                candidate_index=idx,
                contest_win_rate=win_share_totals[idx] / n_field_sims,
                survive_all_rate=survive_all_counts[idx] / n_field_sims,
                avg_survived_days=survived_days_totals[idx] / n_field_sims,
                avg_seed_sum_scored=seed_sum_totals[idx] / n_field_sims,
                plan=plan,
            )
        )

    scored.sort(
        key=lambda x: (
            x.contest_win_rate,
            x.survive_all_rate,
            x.avg_survived_days,
            x.avg_seed_sum_scored,
        ),
        reverse=True,
    )
    return scored


def format_field_scores(
    teams: Dict[str, Team],
    scores: Sequence[CandidateFieldScore],
    top_n: int = 10,
) -> str:
    if not scores:
        return "No field-simulation results available."

    lines: List[str] = []
    lines.append("FIELD-SIMULATION RANKING")
    lines.append("=" * 100)
    lines.append(
        f"{'Rank':<6}{'Contest Win %':<16}{'Survive All %':<16}{'Avg Days':<12}{'First Pick':<24}{'Seed Total':<12}"
    )
    lines.append("-" * 100)

    for rank, score in enumerate(scores[:top_n], start=1):
        first_pick = score.plan.picks[0][1] if score.plan.picks else "N/A"
        lines.append(
            f"{rank:<6}"
            f"{score.contest_win_rate:<16.4%}"
            f"{score.survive_all_rate:<16.4%}"
            f"{score.avg_survived_days:<12.3f}"
            f"{first_pick:<24}"
            f"{score.plan.seed_sum:<12}"
        )

    best = scores[0]
    lines.append("")
    lines.append("BEST FIELD-EV PLAN")
    lines.append("=" * 100)
    lines.append(f"Contest win rate:  {best.contest_win_rate:.4%}")
    lines.append(f"Survive-all rate:  {best.survive_all_rate:.4%}")
    lines.append(f"Average days alive: {best.avg_survived_days:.3f}")
    lines.append(f"Seed total:        {best.plan.seed_sum}")
    lines.append("")
    lines.append(f"{'Day':<6}{'Pick':<28}{'Seed':<8}{'Base Win Prob':<14}")
    lines.append("-" * 100)

    for day, team, p in best.plan.picks:
        lines.append(f"{day:<6}{team:<28}{teams[team].seed:<8}{p:<14.4%}")

    return "\n".join(lines)