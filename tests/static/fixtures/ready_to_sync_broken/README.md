# ready_to_sync_broken

Stand-in scripts the `tests/static/test_ready_to_sync_gate.py` suite plants
in place of real gate steps via the `READY_TO_SYNC_CMD_<N>` environment
overrides. Each fixture exits with a fixed code and a deterministic
message so the gate's orchestration (failure halts, log capture, resume
hints, skip audit) is testable without mutating the live tree.
