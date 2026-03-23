from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Set

import pandas as pd

from .models import Game, Team


def load_teams(path: str | Path) -> Dict[str, Team]:
    df = pd.read_csv(path)

    required_name = "team"
    required_seed = "seed"

    if required_name not in df.columns or required_seed not in df.columns:
        raise ValueError("teams.csv must contain at least: team, seed")

    if "kenpom_rating" in df.columns:
        df["rating"] = df["kenpom_rating"].astype(float)
    elif "kenpom_rank" in df.columns:
        # Lower rank is better; convert so bigger rating is better
        df["rating"] = -df["kenpom_rank"].astype(float)
    else:
        raise ValueError("teams.csv must contain either kenpom_rating or kenpom_rank")

    teams: Dict[str, Team] = {}
    for row in df.itertuples(index=False):
        team = Team(
            name=str(row.team),
            seed=int(row.seed),
            rating=float(row.rating),
        )
        teams[team.name] = team

    return teams


def load_games(path: str | Path) -> List[Game]:
    df = pd.read_csv(path)

    required = {"game_id", "day", "team1", "team2"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"games.csv missing columns: {sorted(missing)}")

    if "winner" not in df.columns:
        df["winner"] = None

    games: List[Game] = []
    for row in df.itertuples(index=False):
        winner = None if pd.isna(row.winner) else str(row.winner)
        games.append(
            Game(
                game_id=str(row.game_id),
                day=int(row.day),
                team1=str(row.team1),
                team2=str(row.team2),
                winner=winner,
            )
        )

    # stable order: by day then game_id
    games.sort(key=lambda g: (g.day, g.game_id))
    return games


def load_used_teams(path: str | Path | None) -> Set[str]:
    if path is None:
        return set()

    with open(path) as f:
        lines = f.read().strip().splitlines()

    if not lines:
        return set()

    # Skip header line, strip whitespace and trailing commas
    teams: Set[str] = set()
    for line in lines[1:]:
        name = line.strip().rstrip(",").strip()
        if name:
            teams.add(name)

    return teams