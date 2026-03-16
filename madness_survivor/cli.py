from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .field_simulator import (
    OpponentModelConfig,
    format_field_scores,
    score_candidate_plans_vs_field,
)
from .io_utils import load_games, load_teams, load_used_teams
from .logger import setup_logging
from .planner import build_survivor_plan, format_plan_table
from .simulator import run_simulations

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="madness-survivor",
        description="March Madness survivor simulator using KenPom-style ratings.",
    )

    parser.add_argument("--teams", required=True, help="Path to teams.csv")
    parser.add_argument("--games", required=True, help="Path to games.csv")
    parser.add_argument(
        "--used-teams",
        default=None,
        help="Optional CSV with one column: team",
    )
    parser.add_argument("--sims", type=int, default=20000, help="Number of Monte Carlo simulations")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument(
        "--scale",
        type=float,
        default=11.0,
        help="Logistic scale for converting rating differences into win probabilities",
    )
    parser.add_argument("--start-day", type=int, default=1, help="Contest day to begin planning from")
    parser.add_argument("--beam-width", type=int, default=500, help="Beam width for plan search")
    parser.add_argument(
        "--candidates-per-day",
        type=int,
        default=8,
        help="Top teams per day to consider in beam search",
    )
    parser.add_argument(
        "--top-alternatives",
        type=int,
        default=5,
        help="How many first-pick alternatives to show",
    )

    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (DEBUG, INFO, WARNING, ERROR)",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="Optional file to write logs",
    )

    # Phase 2: field simulation
    parser.add_argument(
        "--field-size",
        type=int,
        default=0,
        help="Total number of entries in the pool including your own. Set > 1 to enable field simulation.",
    )
    parser.add_argument(
        "--field-sims",
        type=int,
        default=5000,
        help="Number of simulations for the field/contest evaluation phase.",
    )
    parser.add_argument(
        "--field-candidate-plans",
        type=int,
        default=25,
        help="How many top phase-1 plans to evaluate against the field.",
    )
    parser.add_argument(
        "--opponent-chalkiness",
        type=float,
        default=7.0,
        help="Higher = opponents concentrate more heavily on favorites.",
    )
    parser.add_argument(
        "--opponent-seed-bias",
        type=float,
        default=0.0,
        help="Higher = opponents prefer larger seeds for tiebreak leverage.",
    )
    parser.add_argument(
        "--opponent-randomness",
        type=float,
        default=1.0,
        help="Higher = opponents spread picks more randomly.",
    )
    parser.add_argument(
        "--opponent-candidates-per-day",
        type=int,
        default=8,
        help="How many top day candidates opponents consider.",
    )
    parser.add_argument(
        "--field-top-n",
        type=int,
        default=10,
        help="How many field-ranked candidate plans to print.",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    setup_logging(args.log_level, args.log_file)
    logger.info("CLI logging is working")

    teams = load_teams(Path(args.teams))
    games = load_games(Path(args.games))
    used_teams = load_used_teams(args.used_teams)

    summary = run_simulations(
        teams=teams,
        games=games,
        n_sims=args.sims,
        seed=args.seed,
        scale=args.scale,
    )

    plans = build_survivor_plan(
        teams=teams,
        summary=summary,
        start_day=args.start_day,
        used_teams=used_teams,
        beam_width=args.beam_width,
        candidates_per_day=args.candidates_per_day,
    )

    print(format_plan_table(teams, plans, top_alternatives=args.top_alternatives))

    if args.field_size and args.field_size > 1:
        top_candidate_plans = plans[: args.field_candidate_plans]

        opponent_config = OpponentModelConfig(
            chalkiness=args.opponent_chalkiness,
            seed_bias=args.opponent_seed_bias,
            randomness=args.opponent_randomness,
            candidates_per_day=args.opponent_candidates_per_day,
        )

        field_scores = score_candidate_plans_vs_field(
            teams=teams,
            games=games,
            summary=summary,
            candidate_plans=top_candidate_plans,
            field_size=args.field_size,
            n_field_sims=args.field_sims,
            start_day=args.start_day,
            seed=args.seed + 999,
            scale=args.scale,
            opponent_config=opponent_config,
            used_teams=used_teams,
        )

        print()
        print(format_field_scores(teams, field_scores, top_n=args.field_top_n))


if __name__ == "__main__":
    main()