from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

from sandboxtown_v2.core.agent_state import AgentStatus
from sandboxtown_v2.core.stability_rules import Thresholds, next_agent_status


@dataclass(frozen=True)
class SimulationStep:
    """
    One step of the simulation after applying a single stability sample.
    Tests currently expect:
      - step.status.state
      - step.event (singular) as a string like "ENTER_HELP"
    Internally we keep `events` as a tuple for multi-event support.
    """
    status: AgentStatus
    events: Tuple[str, ...]

    @property
    def event(self) -> Optional[str]:
        """
        Compatibility shim: return the first event if any, else None.
        This makes `steps[0].event == "ENTER_HELP"` work.
        """
        if not self.events:
            return None
        return self.events[0]


def run_simulation(
    start: AgentStatus,
    stabilities: Iterable[float],
    thresholds: Thresholds,
) -> List[SimulationStep]:
    """
    Run a simple single-agent simulation over a sequence of stability values.

    Behavior:
      - At each step, we take the previous *state* and replace only the stability value
        with the next sample from `stabilities`.
      - We then call next_agent_status(...) to compute the next AgentStatus + transition events.
      - We return a list of SimulationStep objects (one per stability sample).
    """
    steps: List[SimulationStep] = []
    current = start

    for st in stabilities:
        # keep the previous state, update the stability sample
        sampled = AgentStatus(current.state, float(st))

        result = next_agent_status(sampled, thresholds)

        # Normalize events to a tuple[str, ...]
        # result.events may contain None in some older variants; filter those out safely.
        events_tuple: Tuple[str, ...] = tuple(e for e in (result.events or []) if e is not None)

        step = SimulationStep(status=result.next_status, events=events_tuple)
        steps.append(step)

        # advance
        current = result.next_status

    return steps
