# Cat drawing — status & autonomous continuation

**Goal:** the live AI agent draws a recognizable, reasonably complete cat in Paint.

## Progress
- 2026-06-22 morning: AI drew a recognizable cat FACE (round head + 2 triangular
  ears + an eye) on its own, with vision feedback. Saved:
  `artifacts/cat_attempts/cat_morning_crop.png`. It timed out (300s) before the
  body/tail and left one stray stroke. The drawing primitive is now correct
  (strokes draw real lines via absolute mouse moves — verified 1322 ink pixels).
- 2026-06-22 — **NEW APPROACH shipped (DW-AGENT-SKETCH).** Root-caused the slash +
  polygon + timeout to architecture: the AI was poking raw pixels blindly. Replaced
  with a `sketch` tool — the AI plans the WHOLE cat once as primitives on a 0..100
  grid; deterministic code finds Paint's real canvas (UIA-first) and tessellates
  smooth circles/curves; one stroke per primitive (no fusion → no slash). This
  supersedes the blind-stroke + autonomous-retry loop below.
- 2026-06-22 — **LIVE VALIDATED (Level 4) by Claude on the real desktop.** Drove the
  `sketch` tool against real Win11 Paint with the real input backend + real UIA canvas
  detection (no Claude quota used — the tool is deterministic). Result: a clean,
  recognizable cat drawn by the actual mouse — round head, 2 ears, 2 eyes, nose,
  smiling arc mouth, whiskers, body ellipse, curved tail; NO stray slash, circles
  round. Best image: `artifacts/cat_attempts/cat_live_best.png` (+ `_crop`).
  Two real-world fixes found by OBSERVING Paint: (1) `fit_square`+5% margin so the
  0..100 grid keeps aspect on a wide canvas (circles stay round, ears clear the
  ribbon); (2) after Select-All/clear, Paint stays in the SELECT tool — must click a
  drawing tool (Pencil/Brush) first or strokes become selections, not ink (guidance
  added for the live `do` flow). MANUAL-10 now only needs the user to watch the full
  AI-driven `do "...draw a cat" --vision` once.

## Autonomous continuation (self-paced, quota-bounded)
A ScheduleWakeup loop attempts a fuller cat while the user is away:
- Each wake: if the Claude limit is OPEN and < 6 auto attempts so far →
  run `do "draw a complete cat..." --vision` (longer time), save the canvas crop
  to `artifacts/cat_attempts/cat_auto_<N>.png`, close Paint.
- STOP (no more wake-ups) when a complete cat (head+ears+body+tail) is drawn OR
  6 attempts reached — to protect the user's quota. Keep the best image.
- If the limit is hit, reschedule ~45 min later without burning an attempt.

Latest result + how many attempts are recorded here on each cycle.
