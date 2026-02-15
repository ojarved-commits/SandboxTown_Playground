from __future__ import annotations

from typing import Optional, Tuple

from sandboxtown_v2.core.environment_state import EnvironmentState


class EnvironmentPolicy:
    """
    Spec:
    - If environment is DENSE and any_agent_unstable is True:
        -> downshift to CALM and emit ENV_DOWNSHIFT
    - Otherwise:
        -> no change and no event
    """

    def apply(
        self,
        env_state: EnvironmentState,
        *,
        any_agent_unstable: bool,
    ) -> Tuple[EnvironmentState, Optional[str]]:
        if env_state == EnvironmentState.DENSE and any_agent_unstable:
            return EnvironmentState.CALM, "ENV_DOWNSHIFT"

        return env_state, None
