# Contagion Layer v1 (Spec + Implementation)

Status: ✅ PASS (26 tests)

## What it does
Optional contagion modulation that adjusts per-agent stability inputs
BEFORE state transition evaluation.

Ordering:
Raw stability inputs -> (optional) apply_contagion() -> next_agent_status() -> env shift logic -> record step

## What it does NOT do
- Does not directly override agent state
- Does not add randomness
- Does not modify environment rules
- Does not break determinism

## Entry point
core/multi_agent_simulation.py
- run_multi_agent_simulation(..., contagion=ContagionConfig(...))

## Reason
Adds field/contagion mechanics at the input layer while keeping Canon + hysteresis stable.
