# SandboxTown v2 — Parameter Spec (Scaffold)

This folder implements the frozen SandboxTown v2 parameter spec:
- Coherence + Stability invariant
- Help < 0.60, Rest < 0.30
- Hysteresis: Help exit >= 0.65, Rest exit >= 0.40
- Environment downshift: Dense -> Calm if any agent is Help-Seeking or Rest
- Visual allowed only when Stable >= 0.65
- Passive telemetry only (write-only)

## Run (headless single)
python -m sandboxtown_v2.runs.run_headless_single
