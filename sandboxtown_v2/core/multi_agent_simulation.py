from __future__ import annotations
from .contagion import ContagionConfig, apply_contagion

from dataclasses import dataclass
from typing import Any, Iterator, List, Optional, Sequence, Tuple

from .agent_state import AgentStatus, AgentState
from .environment_state import EnvironmentState
from .stability_rules import Thresholds, next_agent_status, environment_downshift_if_needed

# Optional contagion (safe: only used if passed in)
from .contagion import ContagionConfig, apply_contagion


@dataclass(frozen=True)
class MultiAgentStep:
    agents: List[AgentStatus]
    agent_events: List[Optional[str]]
    environment: EnvironmentState
    env_event: Optional[str] = None


@dataclass(frozen=True)
class MultiAgentSimResult:
    steps: List[MultiAgentStep]

    # Make it behave like a list for tests: steps[0] works.
    def __getitem__(self, idx: int) -> MultiAgentStep:
        return self.steps[idx]

    def __len__(self) -> int:
        return len(self.steps)

    def __iter__(self) -> Iterator[MultiAgentStep]:
        return iter(self.steps)


def _is_unstable(state: AgentState) -> bool:
    # Your current “unstable” bucket for env downshift + contagion source weighting
    return state in (AgentState.HELP_SEEKING, AgentState.REST)


def environment_upshift_if_needed(
    env: EnvironmentState, all_agents_stable: bool
) -> Tuple[EnvironmentState, Optional[str]]:
    """
    Rule:
      - If ALL agents are stable and env is CALM -> upshift to DENSE.
      - Otherwise no change.

    Test expectation:
      start_environment=CALM + all STABLE => steps[0].environment == DENSE
    """
    if all_agents_stable and env == EnvironmentState.CALM:
        return EnvironmentState.DENSE, "ENV_UPSHIFT"
    return env, None


def run_multi_agent_simulation(*args: Any, **kwargs: Any) -> MultiAgentSimResult:
    """
    Expected by tests:
      - returns a subscriptable list-like result: result[0].environment works
      - each step has .environment

    Common calling style:
      run_multi_agent_simulation(agents, sequences, thresholds=th(), start_environment=EnvironmentState.CALM)
    """

    # ---- Parse inputs (support test style) ----
    agents: Optional[List[AgentStatus]] = None
    sequences: Optional[List[List[float]]] = None

    if len(args) >= 1:
        agents = args[0]
    if len(args) >= 2:
        sequences = args[1]

    if agents is None or sequences is None:
        raise ValueError("run_multi_agent_simulation requires (agents, sequences, thresholds=...).")

    if len(sequences) != len(agents):
        raise ValueError("sequences must have one stability list per agent.")

    n_agents = len(agents)
    n_steps = len(sequences[0]) if n_agents else 0
    if any(len(seq) != n_steps for seq in sequences):
        raise ValueError("All sequences must have the same length.")

    thresholds: Thresholds = kwargs["thresholds"]
    start_env: EnvironmentState = kwargs.get(
        "start_environment",
        kwargs.get("start_env", EnvironmentState.DENSE),
    )

    # Optional contagion
    contagion: Optional[ContagionConfig] = kwargs.get("contagion", None)

    current_env = start_env
    current_agents: List[AgentStatus] = agents

    steps: List[MultiAgentStep] = []

    for t in range(n_steps):
        next_agents: List[AgentStatus] = []
        agent_events: List[Optional[str]] = []

        # ---- Contagion acts on stability inputs BEFORE transition eval ----
        raw_step_stabilities = [sequences[i][t] for i in range(n_agents)]
        current_states = [a.state for a in current_agents]

        if contagion is not None and contagion.enabled:
            step_stabilities = apply_contagion(
                raw_stabilities=raw_step_stabilities,
                current_states=current_states,
                env=current_env,
                cfg=contagion,
            )
        else:
            step_stabilities = raw_step_stabilities

        # Apply per-step stability + state transition
        for i in range(n_agents):
            cur = AgentStatus(current_agents[i].state, step_stabilities[i])
            tr = next_agent_status(cur, thresholds)
            next_agents.append(tr.next_status)
            agent_events.append(tr.event)

        # Environment gating: downshift if any unstable, otherwise upshift if all stable
        any_unstable = any(_is_unstable(a.state) for a in next_agents)
        all_stable = not any_unstable

        # Downshift has priority over upshift
        new_env, env_event = environment_downshift_if_needed(current_env, any_unstable)
        if new_env == current_env and env_event is None:
            new_env, env_event = environment_upshift_if_needed(current_env, all_stable)

        current_env = new_env

        steps.append(
            MultiAgentStep(
                agents=next_agents,
                agent_events=agent_events,
                environment=current_env,
                env_event=env_event,
            )
        )

        current_agents = next_agents

    return MultiAgentSimResult(steps=steps)
