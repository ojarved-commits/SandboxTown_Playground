from __future__ import annotations
from pathlib import Path

from ..core.agent_state import AgentState, AgentStatus
from ..core.environment_state import EnvironmentState
from ..core.mode_gate import Mode, enforce_mode
from ..core.stability_rules import Thresholds, environment_downshift_if_needed, next_agent_status
from ..telemetry.passive_logger import PassiveCSVLogger
from ..telemetry.schemas import TelemetryRecord


def main() -> None:
    thresholds = Thresholds.load(Path(__file__).parents[1] / "config" / "thresholds_v2.json")

    env = EnvironmentState.DENSE
    status = AgentStatus(AgentState.STABLE, 0.70)
    mode = Mode.HEADLESS

    log = PassiveCSVLogger(Path("sandboxtown_v2_output") / "telemetry_single.csv")

    records: list[TelemetryRecord] = []

    # Inject a destabilizing sequence: 0.70 -> 0.58 -> 0.63 -> 0.66 -> 0.27 -> 0.42 -> 0.66
    stability_series = [0.70, 0.58, 0.63, 0.66, 0.27, 0.42, 0.66]

    for t, s in enumerate(stability_series):
        status = AgentStatus(status.state, s)
        tr = next_agent_status(status, thresholds)
        status = tr.next_status

        any_unstable = status.state in (AgentState.HELP_SEEKING, AgentState.REST)
        env, env_event = environment_downshift_if_needed(env, any_unstable)

        mr = enforce_mode(mode, status, thresholds)
        mode = mr.mode

        event = tr.event or env_event or mr.event
        records.append(TelemetryRecord(t=t, state=status.state, stability=status.stability, mode=mode.value, event=event))

    log.write(records)
    print("OK: wrote sandboxtown_v2_output/telemetry_single.csv")


if __name__ == "__main__":
    main()
