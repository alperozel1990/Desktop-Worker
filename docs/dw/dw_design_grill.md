# dw_design_grill.md — Design vs repo reality

## Source documents read
- `docs/requirements.md` — full Desktop-Worker spec (north star, 7 phases, MVP,
  safety/audit/broker mandates). Read in full during bootstrap.

## Spec vs repo gaps (at end of bootstrap)
| Spec item (requirements §) | Repo has | Missing |
|---|---|---|
| Screenshot capture (§6) | Windows (mss) + Null placeholder | real capture needs `[windows]` extra |
| Cursor / active window (§6) | ✅ real ctypes backend | multi-monitor |
| Mouse/keyboard/clipboard (§9) | ✅ SendInput + clipboard | reliability hardening (DW-INPUT-HARDEN) |
| Action schema (§8) | ✅ validated registry | fs.* actions, richer browser actions |
| Audit log (§13) | ✅ JSONL + redaction | UI timeline viewer (Phase 7) |
| Emergency stop (§12) | ✅ in-process + file sentinel | UI button (Phase 7) |
| Structured loop (§14) | ✅ scripted planner | retry/re-plan (DW-LOOP-RECOVERY), AI planner |
| Elevated CLI broker (§11) | ✅ capture/preview/approval/risk/audit | true per-cmd UAC (DW-CLI-ELEVATE) |
| Perception OCR/UIA (§7) | ☐ | entire Phase 4 |
| Browser/desktop workflows (§10) | ☐ | entire Phase 5 |
| Multi-agent (§4) | workspace schema seeds it | orchestration code (Phase 6) |
| UI (§16) | CLI only | full UI (Phase 7) |

## Contradictions / tensions resolved
- **"Elevated by default" vs output capture.** True per-command UAC re-elevation
  spawns a separate process whose stdout can't be captured inline. **Resolution:**
  the broker is elevation-*capable* and reports actual token state; intended
  deployment runs admin via UAC launcher; per-command re-elevation w/ capture is
  the explicit card DW-CLI-ELEVATE. Logs never overstate privilege.
- **"No raw shell" vs string commands (§8 example `npm test`).** Resolution: the
  broker accepts command strings (run via cmd.exe) but exposes **no passthrough** —
  every command is classified, approval-gated, captured, and audited. That gating,
  not shell-sandboxing, is the control boundary.
- **Rich verification vs no perception yet.** §14 lists OCR/UIA verification, which
  don't exist until Phase 4. Resolution: loop verifies what a structured
  observation supports (active window, clipboard) and marks the rest
  "requires Perception layer" rather than silently passing.

## Unclear areas + recommended defaults
- **AI provider/model for the planner:** default Claude; interface is
  provider-agnostic. (Non-blocking.)
- **UI technology (Phase 7):** decide at Phase 7; CLI suffices now. (Non-blocking.)
- **Approval UX:** headless deny-by-default; pluggable callback for a future UI prompt.

## Assumptions (logged; none blocking)
- Python 3.11+; Windows 11; single-monitor MVP acceptable.
- Demo uses auto-approve to demonstrate the broker path; production uses deny-all.

## Blocking questions
**None.** Stack was confirmed (Python). All other open items have safe defaults
recorded in `dw_state.md` Open Questions.

## Implementation implications
- Phases 1–3 have a tested foundation; the backlog closes the named gaps.
- Keep the Planner interface stable so DW-PLANNER-AI drops in without loop changes.
- Element schema should be designed once (DW-PERCEPTION-OCR) and reused by UIA.
