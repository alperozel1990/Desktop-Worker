# Cat drawing — status & autonomous continuation

**Goal:** the live AI agent draws a recognizable, reasonably complete cat in Paint.

## Progress
- 2026-06-22 morning: AI drew a recognizable cat FACE (round head + 2 triangular
  ears + an eye) on its own, with vision feedback. Saved:
  `artifacts/cat_attempts/cat_morning_crop.png`. It timed out (300s) before the
  body/tail and left one stray stroke. The drawing primitive is now correct
  (strokes draw real lines via absolute mouse moves — verified 1322 ink pixels).

## Autonomous continuation (self-paced, quota-bounded)
A ScheduleWakeup loop attempts a fuller cat while the user is away:
- Each wake: if the Claude limit is OPEN and < 6 auto attempts so far →
  run `do "draw a complete cat..." --vision` (longer time), save the canvas crop
  to `artifacts/cat_attempts/cat_auto_<N>.png`, close Paint.
- STOP (no more wake-ups) when a complete cat (head+ears+body+tail) is drawn OR
  6 attempts reached — to protect the user's quota. Keep the best image.
- If the limit is hit, reschedule ~45 min later without burning an attempt.

Latest result + how many attempts are recorded here on each cycle.
