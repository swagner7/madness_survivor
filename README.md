# Madness Survivor

A reusable March Madness survivor contest simulator.

## Rules modeled

- One pick per contest day
- You advance if your team wins that day
- A team can only be used once
- Tiebreaker = total seed sum of all picks, higher is better

## Inputs

### `teams.csv`

Required columns:

- `team`
- `seed`
- either `kenpom_rating` or `kenpom_rank`

Example:

```csv
team,seed,kenpom_rating
Houston,1,31.2
Connecticut,1,29.8
Purdue,1,28.6
Auburn,4,27.1