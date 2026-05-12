# UI UX Round 19 Path Walk Notes

Date: 2026-05-11

## Prompt Archive Check

Ran:

```bash
python3 coding_prompts/_audit_implementation.py
```

Result: no active top-level Round 18 prompts were safe to archive. All 50 top-level `coding_prompts/[0-9][0-9]_*.txt` prompts are still partial or not implemented by their declared scope. Archived implemented prompts remain archived. This round is therefore isolated in `coding_prompts/ui_ux_round19/` so it can be run without accidentally executing the active Round 18 architecture batch.

## Live Path Walk

Checked:

- Public home: `https://www.theseuscodex.com/`
- Founder login: `https://www.theseuscodex.com/login`
- Dashboard: `/dashboard`
- Knowledge conclusions: `/knowledge`
- Conclusion detail: `/conclusions/c_2276f14a65124a1898843fb3`
- Transcript index: `/knowledge?tab=transcripts`
- Audio transcript detail: `/transcripts/c6080d00458676eb57380e57d`
- Upload: `/upload`
- Ask: `/codex-ask`
- Ops: `/ops`
- Founder Currents: `/founder-currents`
- Public Currents: `/currents`

## Findings

1. Conclusion detail is too busy by default. It shows hero/help copy, confidence, rationale, publication state, enqueue controls, failure modes, action buttons, tab navigation, overview accordions, source links, and deletion controls all at once. The page needs one clear default reading surface, with review/publishing/methodology details progressively disclosed.

2. The conclusion page gives equal visual weight to primary, secondary, administrative, and destructive actions. "Run peer review", "Queue for publication", "Peer review history", "Decay dashboard", "Export JSON", and "Request deletion" need hierarchy and grouping.

3. Typography is still overly theatrical in operational surfaces. Wide letter spacing, all-caps labels, decorative headings, and italic body copy make dashboard, upload, ask, conclusion, transcript, and ops pages feel heavier than their function warrants.

4. The Ops sub-navigation horizontally overflows at desktop width. It needs a responsive, wrapped, or segmented layout that does not create a hidden horizontal scroll lane.

5. Transcript audio detail now displays raw transcript text and chunks, but failed audio uploads still show `failed` status even when transcript data is present. The UI should distinguish "transcript available; downstream analysis failed" from "no transcript available".

6. The transcript detail page front-loads conversation geometry and methodology cards before the raw transcript. For podcasts/audio, the raw transcript should be the central first-class object, with analysis panels secondary.

7. Upload uses a large decorative split composition with lots of empty visual space. The practical task is file selection, visibility, description, and processing expectations; the interface should make those controls denser and clearer.

8. Ask has a disabled submit button until input exists, but the disabled state is not explained. The page should show a clear enabled/disabled state and a responsive loading state once asked.

9. Public and founder Currents both show `reconnecting...` and no opinions. The UI should surface backend health and missing-data reasons plainly in founder/admin contexts, while keeping the public empty state neutral.

10. Buttons and links generally navigate, but important workflow buttons need explicit loading, disabled, success, and failure states. The visual system should make anchors and client actions feel consistently responsive.

11. Public home currently has no public publications or currents. Empty states should be calmer, less ornamental, and should avoid implying the system is complete if backend generation is not yet active.

12. The top navigation is wide and visually dense. It works at desktop width but needs a clearer responsive strategy and a less noisy account/help/sign-out cluster.

