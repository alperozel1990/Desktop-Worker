# Drawing v2 — Robust, Best-of-N, Multi-representation (DW-AGENT-DRAW)

## Problem / what was missing
v1 (`sketch` tool) draws a clean cat deterministically, but live the system still
let chaos happen (red scribbles over the canvas). Three gaps:
1. **No canvas hygiene / execution lock** — no guaranteed clean canvas, no
   color/brush control, and raw `mouse.stroke` stays available → the AI (or stale
   state) can scribble freely.
2. **No quality gate before ink** — the program is drawn blindly; a bad plan
   still lands on the canvas.
3. **No measurable objective / weak representation** — "look and fix" is vague;
   SOTA uses a VLM/CLIP judge + best-of-N reranking, and SVG as the substrate
   (LLMs generate SVG far better than a bespoke DSL).

Research basis: Chat2SVG (LLM SVG template + refine), CLIPasso/CLIPDraw++ (Bezier
+ perceptual objective), LLM4SVG (LLM SVG > custom format).

## Approach: generate → render-offline → score → select → execute-clean → verify
The AI only PROPOSES programs; execution is deterministic and hygienic. Phased:

### Phase A — quota-free robustness + SVG representation
- **`geometry/svg.py`** (pure): parse an SVG subset (`<path>` M/L/H/V/C/Q/Z,
  `<circle>`, `<ellipse>`, `<line>`, `<polyline>`, `<rect>`), normalize the viewBox
  to the 0..100 grid, sample each path subpath (de Casteljau for C/Q) into ONE
  continuous polyline → a `Program`. Reuses the v1 renderer + canvas detection.
- **`geometry/preview.py`** (PIL lazy): render a `Program` to a PNG offline (no
  mouse) for the self-check and the best-of-N montage.
- **`geometry/paint_setup.py`** (UIA, Null fallback): canvas hygiene —
  foreground+maximize Paint, clear (Ctrl+A/Delete/Escape), select a drawing tool
  (Pencil/Brush) and a known color via UIA. Pure key-sequence + injectable
  tool-finder for tests; validated live.
- **`SketchTool`**: accept `{svg: "..."}` OR `{primitives: [...]}`; run canvas prep
  first so strokes are ink on a clean canvas, never selections on garbage.

### Phase B — best-of-N + AI judge (max quality): `drawing/director.py`
A focused orchestrator behind `python -m desktop_worker draw "<subject>"`:
1. ONE Claude call → N candidate programs (SVG/DSL) for the subject.
2. Render all N offline (`preview.py`).
3. ONE Claude vision call → judge a montage, pick the best.
4. Execute ONLY the winner via the hygienic path (clean canvas + tool/color).
5. ONE Claude vision call → verify the real canvas vs subject; at most ONE
   correction. ~3–4 Claude calls total — best-of-N quality, quota-friendly.

Claude calls are INJECTED (`ask_text`, `ask_vision`, `draw_fn`) so the director is
pure-orchestration and unit-testable with stubs; real ones wired via the broker.
In this path the AI never emits raw strokes — the foot-gun cannot fire.

## Units (isolated, well-bounded)
| Unit | Purpose | Depends on |
|---|---|---|
| `geometry/svg.py` | SVG subset → Program (pure) | dsl, render |
| `geometry/preview.py` | Program → PNG offline | render, canvas, PIL(lazy) |
| `geometry/paint_setup.py` | clean canvas + tool/color (UIA) | input backend, uiautomation(lazy) |
| `drawing/director.py` | best-of-N + judge + verify orchestration | svg, preview, paint_setup, injected Claude |
| `__main__` `draw` cmd | wire real broker Claude calls | director, Session |

Unchanged + reused: `geometry/{dsl,render,canvas}`, `actions/windows_input.stroke`,
executor, audit, estop. No new schema action (the tool envelope suffices).

## Verification
- Unit: SVG parse (paths/shapes/viewBox, bad input rejected), offline preview
  (non-empty PNG / graceful no-PIL), paint_setup key-sequence + tool-finder,
  director flow with stubbed Claude (N candidates → judge picks → execute → verify).
- Live (Claude validates the deterministic path, no quota): clean canvas → draw a
  known SVG cat → screenshot shows ONE clean cat, NO red. Then the user observes the
  full AI-driven `draw "a cat"` (the ~3–4 Claude-call flagship).

## Phasing
Phase A first (kills the chaos, adds SVG + clean execution), then Phase B (the
`draw` flagship with best-of-N + judge). Both ship behind tests.
