# src/policy_engine.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


# ----------------------------
# Intent (Option 1: zone + rest)
# ----------------------------
@dataclass
class Intent:
    desired_zone: Optional[str] = None   # e.g. "Library", "Park", "Transition", "Rest"
    should_rest: bool = False


# ----------------------------
# World snapshot (keep it tiny)
# ----------------------------
@dataclass
class WorldState:
    dt: float
    # Optional fields you can add later without breaking anything:
    # tick: int = 0
    # pause_threshold: float = 2.0
    # zones: list = None


# ----------------------------
# Policy interface
# ----------------------------
class Policy(Protocol):
    def step(self, agent, world: WorldState) -> Intent: ...


# ----------------------------
# A dead-simple default policy
# (does nothing; safe baseline)
# ----------------------------
class NullPolicy:
    def step(self, agent, world: WorldState) -> Intent:
        return Intent()


# ----------------------------
# Example policy: "Rest when load is high"
# Works if agent.state.load exists (0..1)
# If it doesn't exist, it safely no-ops.
# ----------------------------
class RestWhenLoadedPolicy:
    def __init__(self, load_threshold: float = 0.75) -> None:
        self.load_threshold = load_threshold

    def step(self, agent, world: WorldState) -> Intent:
        st = getattr(agent, "state", None)
        load = getattr(st, "load", None) if st is not None else None
        if isinstance(load, (int, float)) and load >= self.load_threshold:
            return Intent(desired_zone="Rest", should_rest=True)
        return Intent()


# ----------------------------
# Policy bundle (compose later)
# ----------------------------
class PolicyBundle:
    """
    Start simple: one policy.
    Later you can chain multiple policies and merge Intents.
    """
    def __init__(self, policy: Optional[Policy] = None) -> None:
        self.policy: Policy = policy or NullPolicy()

    def step(self, agent, world: WorldState) -> Intent:
        return self.policy.step(agent, world)
