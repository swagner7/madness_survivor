from __future__ import annotations

import argparse
from pathlib import Path

from .io_utils import load_games, load_teams, load_used_teams
from .planner import build_survivor_plan, format_plan_table
from .simulator import run_simulations


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

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

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


if __name__ == "__main__":
    main()