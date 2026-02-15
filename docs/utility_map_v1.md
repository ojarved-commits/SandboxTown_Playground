\# ORPIN / MOS SandboxTown — Utility Map v1



\## Core entities

\- Agent = worker / process node

\- Zone = task context (type of work)

\- Commit = selecting a zone to work in (decision lock)

\- Transition = context-switch overhead / travel between zones

\- Pause = throttle / wait / sync / blocked state

\- Rest = recovery / cooldown / nervous-system reset



\## Internal state signals

\- energy = capacity / fuel / readiness

\- load = stress / task pressure / saturation

\- curiosity = exploration drive / novelty seeking

\- coherence = stability / clarity / focus quality



\## Telemetry meaning

\- transitions = number of context switches

\- pause\_ratio = % time in pause mode

\- zone\_pct\_\* = % time spent per zone

\- avg\_speed/std\_speed = locomotion / volatility (movement proxy)



\## Interpretation rule

\- “Good” runs reduce Transition waste while maintaining or increasing time in the intended work zones.

\- Sandbox purpose: small experiments → measurable deltas → reusable utility program patterns.



