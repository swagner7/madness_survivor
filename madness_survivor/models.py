from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Team:
    name: str
    seed: int
    rating: float


@dataclass(frozen=True)
class Game:
    game_id: str
    day: int
    team1: str
    team2: str
    winner: Optional[str] = None

    def participants(self) -> tuple[str, str]:
        return self.team1, self.team2