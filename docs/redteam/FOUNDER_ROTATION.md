# Red-team founder rotation (SP08)

## Intent

Security and robustness thinking must not collapse into a single “security person.” One founder per calendar month acts as **red-team sponsor**:

- Read the Robustness Ledger and open tickets for **accepted_risk** items.
- Add at least one new synthetic attack or benign false-positive test when a shipped mitigation touches their area.
- Attend the monthly **red-team sync** (30–45 minutes) to triage CI regressions from `python -m noosphere redteam run`.

## Calendar

Assign months in the operating plan (e.g. rotating alphabetical by founder handle). Update the row here when the roster changes:

| Month (2026) | Sponsor |
|--------------|---------|
| April | _TBD_ |
| May | _TBD_ |

## Handoff checklist

1. Confirm CI green on `redteam run` + coherence eval subset.
2. Note any external disclosure threads in the private security inbox.
3. Update `docs/Robustness_Ledger.md` if status changed.
