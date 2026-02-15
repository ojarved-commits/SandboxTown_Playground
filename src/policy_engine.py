# src/policy_engine.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol


class Policy(Protocol):
    """Optional hooks around an agent update step."""
    def before_step(self, ag: Any, ctx: Dict[str, Any]) -> None: ...
    def after_step(self, ag: Any, ctx: Dict[str, Any]) -> None: ...


class NullPolicy:
    """Does nothing. Safe default."""
    def before_step(self, ag: Any, ctx: Dict[str, Any]) -> None:
        return

    def after_step(self, ag: Any, ctx: Dict[str, Any]) -> None:
        return


class TracePolicy:
    """
    Example policy: record simple counters/timestamps in ctx (no behavior change).
    Good for verifying hook plumbing without touching movement.
    """
    def before_step(self, ag: Any, ctx: Dict[str, Any]) -> None:
        ctx["policy_hits_before"] = ctx.get("policy_hits_before", 0) + 1

    def after_step(self, ag: Any, ctx: Dict[str, Any]) -> None:
        ctx["policy_hits_after"] = ctx.get("policy_hits_after", 0) + 1


@dataclass
class PolicyBundle:
    """Wrapper so main.py can always call bundle.before_step / after_step safely."""
    policy: Policy

    def before_step(self, ag: Any, ctx: Dict[str, Any]) -> None:
        self.policy.before_step(ag, ctx)

    def after_step(self, ag: Any, ctx: Dict[str, Any]) -> None:
        self.policy.after_step(ag, ctx)


def make_policy(name: Optional[str]) -> PolicyBundle:
    """
    Factory. Name can be None / 'none' / 'null' => NullPolicy.
    """
    if not name or name.lower() in ("none", "null", "off"):
        return PolicyBundle(NullPolicy())
    if name.lower() in ("trace", "debug"):
        return PolicyBundle(TracePolicy())

    # Unknown policy name => fail fast (clear error)
    raise ValueError(f"Unknown policy '{name}'. Use --policy none|trace")
