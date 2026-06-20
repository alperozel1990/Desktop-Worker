# dw_web_research.md — Web research

## Date
2026-06-20

## Status
**No web research performed during bootstrap.** It was not required to stand up
the Phase 1 foundation, which uses only the Python standard library + ctypes
(already known APIs). Web access was not used in this session.

## When to research next (per ease-me policy)
Run web research before implementing cards that touch external/uncertain APIs:
- **DW-PERCEPTION-OCR** — Tesseract install on Windows + `pytesseract` usage,
  current `mss` API, image preprocessing for OCR accuracy.
- **DW-PERCEPTION-UIA** — `uiautomation` / `comtypes` patterns, control-type maps,
  reliability notes vs raw COM UIAutomation.
- **DW-CLI-ELEVATE** — current, reliable pattern for ShellExecute "runas" with
  captured output + exit code on Windows 11 (verify behavior; it changes).
- **DW-PLANNER-AI** — latest Claude model IDs + tool-use/structured-output API
  (see also the `claude-api` skill); verify model names at implementation time.

## Recording rules for future research
For each source capture: date, URL, title, relevance, findings, implementation
implications, and a stale/uncertain flag (e.g. "docs for v1.x, we use v2.x").
If web access is unavailable, record that and proceed with repo/docs only.
