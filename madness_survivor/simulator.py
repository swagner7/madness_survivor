from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .models import Game, Team


@dataclass
class SimulationSummary:
    win_prob_by_day: Dict[int, Dict[str, float]]
    appearance_prob_by_day: Dict[int, Dict[str, float]]
    championship_prob: Dict[str, float]
    total_sims: int


def logistic_win_prob(rating_a: float, rating_b: float, scale: float = 11.0) -> float:
    x = (rating_a - rating_b) / scale
    return 1.0 / (1.0 + math.exp(-x))


def is_game_ref(token: str) -> bool:
    return token.startswith("W:")


def ref_game_id(token: str) -> str:
    return token.split(":", 1)[1]


def resolve_team(token: str, winners: Dict[str, str]) -> Optional[str]:
    if is_game_ref(token):
        return winners.get(ref_game_id(token))
    return token


def simulate_once(
    teams: Dict[str, Team],
    games: List[Game],
    rng: random.Random,
    scale: float = 11.0,
) -> Tuple[Dict[str, str], Dict[int, List[str]], Dict[int, List[str]]]:
    winners: Dict[str, str] = {}
    day_winners: Dict[int, List[str]] = defaultdict(list)
    day_appearances: Dict[int, List[str]] = defaultdict(list)

    for game in games:
        t1 = resolve_team(game.team1, winners)
        t2 = resolve_team(game.team2, winners)

        if t1 is None or t2 is None:
            raise ValueError(
                f"Game {game.game_id} could not resolve participants. "
                f"Check game ordering and references."
            )

        if t1 not in teams or t2 not in teams:
            raise ValueError(f"Unknown team in game {game.game_id}: {t1} vs {t2}")

        day_appearances[game.day].append(t1)
        day_appearances[game.day].append(t2)

        if game.winner is not None:
            if game.winner not in {t1, t2}:
                raise ValueError(
                    f"Preset winner '{game.winner}' is not a participant in game {game.game_id}"
                )
            winner = game.winner
        else:
            p_t1 = logistic_win_prob(teams[t1].rating, teams[t2].rating, scale=scale)
            winner = t1 if rng.random() < p_t1 else t2

        winners[game.game_id] = winner
        day_winners[game.day].append(winner)

    return winners, day_winners, day_appearances


def run_simulations(
    teams: Dict[str, Team],
    games: List[Game],
    n_sims: int = 10000,
    seed: int = 42,
    scale: float = 11.0,
) -> SimulationSummary:
    rng = random.Random(seed)

    max_day = max(game.day for game in games)

    day_win_counts: Dict[int, Dict[str, int]] = {
        day: defaultdict(int) for day in range(1, max_day + 1)
    }
    day_appearance_counts: Dict[int, Dict[str, int]] = {
        day: defaultdict(int) for day in range(1, max_day + 1)
    }
    championship_counts: Dict[str, int] = defaultdict(int)

    final_day = max_day

    for _ in range(n_sims):
        _, day_winners, day_appearances = simulate_once(teams, games, rng, scale=scale)

        for day, winners in day_winners.items():
            for team in winners:
                day_win_counts[day][team] += 1

        for day, appearing_teams in day_appearances.items():
            # dedupe in case input accidentally duplicates a team on same day
            for team in set(appearing_teams):
                day_appearance_counts[day][team] += 1

        for champ in day_winners.get(final_day, []):
            championship_counts[champ] += 1

    win_prob_by_day: Dict[int, Dict[str, float]] = {}
    appearance_prob_by_day: Dict[int, Dict[str, float]] = {}

    for day in range(1, max_day + 1):
        all_day_teams = set(day_win_counts[day]) | set(day_appearance_counts[day])
        win_prob_by_day[day] = {
            team: day_win_counts[day][team] / n_sims for team in all_day_teams
        }
        appearance_prob_by_day[day] = {
            team: day_appearance_counts[day][team] / n_sims for team in all_day_teams
        }

    championship_prob = {
        team: championship_counts[team] / n_sims for team in teams
    }

    return SimulationSummary(
        win_prob_by_day=win_prob_by_day,
        appearance_prob_by_day=appearance_prob_by_day,
        championship_prob=championship_prob,
        total_sims=n_sims,
    )