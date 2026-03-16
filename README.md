# Madness Survivor Simulator

A Monte Carlo simulator for **March Madness survivor contests** using KenPom-style team ratings.  
The tool simulates the NCAA tournament thousands of times and recommends picks that maximize:

- probability of surviving each day
- seed tiebreak advantage
- probability of **winning the entire pool vs the field**

It is designed to be **rerun daily** as games finish and ratings update.

---

# Contest Rules Modeled

The simulator assumes a survivor pool with rules similar to:

- Pick **one team per contest day**
- If your team **wins**, you advance
- If your team **loses**, you are eliminated
- You **cannot reuse a team**
- Contest lasts **10 days**
- Tiebreaker = **sum of seeds of all picks (higher wins)**

---

# How the Model Works

The simulator runs in two phases.

### Phase 1 — Survivor Optimization

1. Simulate the tournament many times.
2. Estimate the probability each team wins on each contest day.
3. Generate candidate pick paths that maximize:
   - survival probability
   - seed tiebreak total
   - no team reuse

This produces strong survivor strategies assuming **no opponents exist**.

---

### Phase 2 — Field Simulation

To estimate actual contest equity:

1. Simulate tournament outcomes.
2. Simulate opponent picks.
3. Compare all entries.
4. Determine the contest winner.

This estimates **your probability of winning the pool**.

---

# Required Inputs

## teams.csv

Team strengths and seeds.

Required columns:

team, seed, kenpom_rating

Example:
team,seed,kenpom_rating
Houston,1,31.2
Purdue,1,29.5
Duke,4,23.7
Vermont,13,12.4

## games.csv

Defines the tournament bracket.

Required columns:
game_id, day, team1, team2, winner (optional)

Example:
game_id,day,team1,team2,winner
R64_G1,1,Houston,Longwood,
R64_G2,1,Nebraska,Texas A&M,
R32_G1,3,W:R64_G1,W:R64_G2,


`W:<game_id>` references a previous game winner.

---

## Optional used_teams.csv

Tracks picks already used.

Example:
team
Houston,
Duke,

run with: --used-teams data/used_teams.csv

---

# Running the Simulator

Basic run:
madness-survivor \
  --teams data/teams.csv \
  --games data/games.csv \
  --sims 5000 \

Run with field simulation:
madness-survivor \
  --teams data/teams.csv \
  --games data/games.csv \
  --sims 5000 \
  --field-size 15 \
  --field-sims 10000 \
  --field-candidate-plans 40 \
  --beam-width 1500 \
  --candidates-per-day 12 \
  --opponent-chalkiness 8.0 \
  --opponent-randomness 1.0 \
  --log-level INFO

---

# Reading the Output

The CLI prints two sections.

---

## Phase 1 — Survivor Plan

Example:
BEST PLAN
Day Pick Seed Win Prob
1 Houston 1 96.3%
2 Duke 4 82.1%
3 Auburn 4 75.2%


Meaning:

| Column | Description |
|------|-------------|
Day | contest day |
Pick | recommended team |
Seed | NCAA seed |
Win Prob | probability that team wins that day |

Also shown:

**survive-all-days score**

Approximate probability the entire pick path survives the contest.

---

## First Pick Alternatives

Example:
TOP FIRST-PICK ALTERNATIVES
Houston survive-score≈0.038
Purdue survive-score≈0.036
Arizona survive-score≈0.034


These represent the **best full strategies starting with each possible first pick**.

Useful if the most obvious pick will be extremely popular.

---

## Phase 2 — Field Simulation

Example:
FIELD-SIMULATION RANKING
Rank Contest Win % Survive All % Avg Days First Pick
1 3.21% 3.88% 6.21 Purdue
2 3.07% 3.91% 6.24 Houston


Metrics:

| Metric | Meaning |
|------|---------|
Contest Win % | probability your entry wins the entire pool |
Survive All % | probability you survive all days |
Avg Days | average days survived |

Important:

The strategy with the **highest survival probability is not always the strategy most likely to win the pool.**

Field simulation captures:

- opponent clustering on favorites
- tiebreak outcomes
- strategy diversification.

---

# Tuning the Simulation

## Tournament Simulations
--sims

Number of bracket simulations.

Typical values:

| sims | purpose |
|-----|---------|
10000 | quick test |
50000 | standard |
100000+ | higher precision |

---

## Field Simulation
--field-size

Number of entries in your pool.

--field-sims

Number of simulated contests.

Typical:

| sims | accuracy |
|-----|-----------|
5000 | quick |
10000 | standard |
25000+ | very stable |

---

## Planner Search Controls

--beam-width

Number of candidate strategies explored.

Typical: 1500

--candidates-per-day

Teams considered each day.

Typical: 10

--
Higher values explore more strategies but increase runtime.

---

## Opponent Behavior

Field simulation models opponent picks probabilistically.

### Chalkiness

--opponent-chalkiness


How strongly opponents prefer favorites.

| value | behavior |
|------|----------|
5 | moderate chalk |
7 | strong chalk |
10 | extreme chalk |

Typical: 7

---

### Randomness

--opponent-randomness

How varied opponent picks are.

| value | effect |
|------|-------|
0.8 | concentrated picks |
1.0 | normal |
1.3 | more randomness |

---

### Seed Bias

--opponent-seed-bias

How much opponents care about seed tiebreak totals.

| value | effect |
|------|-------|
0 | none |
0.3 | mild |
1.0 | strong |

Typical: 0.2