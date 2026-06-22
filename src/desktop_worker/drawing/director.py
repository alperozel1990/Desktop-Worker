"""DrawingDirector — generate → render-offline → judge → execute-clean → verify.

The research-backed quality pipeline (Chat2SVG/CLIPasso-style best-of-N + a
VLM judge). The AI only PROPOSES drawings (as SVG); rendering, scoring and
execution are deterministic, so a bad proposal never reaches the canvas and raw
strokes are never emitted. All Claude calls are INJECTED so the whole director is
unit-testable with stubs:

* ``ask_text(prompt) -> str``       — one text completion (candidate generation)
* ``ask_vision(prompt, image) -> str`` — one vision completion (judge / verify)
* ``draw_fn(program) -> dict``      — execute a Program on the real canvas (clean)
* ``screenshot_fn() -> str|None``   — capture the canvas for the verify pass

Typical cost: 1 generate + 1 judge (+ optional 1 verify + 1 refine) Claude calls.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, List, Optional

from desktop_worker.geometry.dsl import Program
from desktop_worker.geometry.preview import montage_png, render_program_png
from desktop_worker.geometry.svg import parse_svg
from desktop_worker.tools.registry import ToolError

_SVG_BLOCK = re.compile(r"<svg\b.*?</svg>", re.IGNORECASE | re.DOTALL)


def parse_svg_candidates(text: str, *, title: str = "drawing") -> List[Program]:
    """Extract every ``<svg>…</svg>`` block and parse the valid ones into Programs."""
    out: List[Program] = []
    for block in _SVG_BLOCK.findall(text or ""):
        try:
            out.append(parse_svg(block, title=title))
        except ToolError:
            continue
    return out


def _generate_prompt(subject: str, n: int) -> str:
    return (
        f"You are an expert illustrator. Produce {n} DISTINCT, simple, instantly "
        f"recognizable black line-drawings of: {subject}.\n"
        "Rules:\n"
        f"- Output EXACTLY {n} SVG drawings, each in its own ```svg fenced block.\n"
        '- Each SVG MUST use viewBox="0 0 100 100", no fills (stroke only), no colors '
        "(black), no text.\n"
        "- Use <path> (with smooth C/Q curves), <circle>, <ellipse>, <line>, "
        "<polyline>, <polygon>. Compose the whole subject (all major parts).\n"
        "- Vary the style/pose across the candidates so the best can be chosen.\n"
        "Return ONLY the SVG blocks, nothing else."
    )


def _judge_prompt(subject: str, n: int) -> str:
    return (
        f"The attached image is a grid of {n} candidate line-drawings of '{subject}', "
        "labelled #1.." f"{n}. Pick the SINGLE most recognizable, complete and well-"
        f"proportioned one. Reply with ONLY its number (1-{n})."
    )


def _verify_prompt(subject: str) -> str:
    return (
        f"The attached screenshot shows a drawing meant to depict '{subject}'. "
        'Reply with ONLY a JSON object: {"ok": true|false, "issue": "<short>"}. '
        "ok=true if it is clearly recognizable as the subject."
    )


def _refine_prompt(subject: str, issue: str) -> str:
    return (
        f"Improve a line-drawing of '{subject}'. Known issue: {issue}. "
        'Output ONE corrected SVG (viewBox="0 0 100 100", black stroke only, no text) '
        "in a single ```svg block. Return ONLY the SVG."
    )


class DrawingDirector:
    def __init__(self, *, ask_text: Callable[[str], str],
                 ask_vision: Callable[[str, str], str],
                 draw_fn: Callable[[Program], dict],
                 work_dir: str,
                 screenshot_fn: Optional[Callable[[], Optional[str]]] = None,
                 n_candidates: int = 3, refine: bool = True,
                 log: Optional[Callable[[str], None]] = None) -> None:
        self._ask_text = ask_text
        self._ask_vision = ask_vision
        self._draw_fn = draw_fn
        self._work = work_dir
        self._screenshot = screenshot_fn
        self._n = max(1, n_candidates)
        self._refine = refine
        self._log = log or (lambda m: None)

    # --- steps (each small + testable) --------------------------------
    def _generate(self, subject: str) -> List[Program]:
        text = self._ask_text(_generate_prompt(subject, self._n))
        return parse_svg_candidates(text, title=subject)

    def _judge(self, subject: str, montage: str, n: int) -> int:
        try:
            reply = self._ask_vision(_judge_prompt(subject, n), montage)
            m = re.search(r"\d+", reply or "")
            if m:
                return min(n - 1, max(0, int(m.group()) - 1))
        except Exception:
            pass
        return 0

    def _verify(self, subject: str) -> Optional[dict]:
        if self._screenshot is None:
            return None
        shot = self._screenshot()
        if not shot:
            return None
        try:
            reply = self._ask_vision(_verify_prompt(subject), shot)
            ok = '"ok": true' in reply.lower() or '"ok":true' in reply.lower()
            mi = re.search(r'"issue"\s*:\s*"([^"]*)"', reply)
            return {"ok": ok, "issue": mi.group(1) if mi else ""}
        except Exception:
            return None

    # --- the pipeline -------------------------------------------------
    def draw(self, subject: str) -> dict:
        try:
            candidates = self._generate(subject)
        except Exception as exc:                 # broker block / claude error
            return {"success": False, "error": f"candidate generation failed: {exc}",
                    "subject": subject}
        self._log(f"generated {len(candidates)} candidate(s)")
        if not candidates:
            return {"success": False, "error": "no valid SVG candidates produced",
                    "subject": subject}

        previews = [render_program_png(c, str(Path(self._work) / f"cand_{i}.png"))
                    for i, c in enumerate(candidates)]
        montage = montage_png([p for p in previews if p],
                              str(Path(self._work) / "montage.png"))

        idx = self._judge(subject, montage, len(candidates)) if montage else 0
        self._log(f"judge picked candidate #{idx + 1} of {len(candidates)}")
        winner = candidates[idx]

        try:
            draw_res = self._draw_fn(winner)
        except Exception as exc:                 # never let execution crash the command
            return {"success": False, "error": f"drawing failed: {exc}",
                    "subject": subject, "candidates": len(candidates), "chosen": idx + 1}

        verdict = self._verify(subject)
        refined = False
        if self._refine and verdict is not None and verdict.get("ok") is False:
            self._log(f"verify not satisfied ({verdict.get('issue')}) — one refine pass")
            try:
                fix = parse_svg_candidates(
                    self._ask_text(_refine_prompt(subject, verdict.get("issue", ""))),
                    title=subject)
                if fix:
                    draw_res = self._draw_fn(fix[0])
                    winner = fix[0]
                    refined = True
            except Exception:
                pass

        return {"success": bool(draw_res.get("success", False)),
                "subject": subject, "candidates": len(candidates),
                "chosen": idx + 1, "refined": refined,
                "primitives": len(winner.primitives), "verdict": verdict,
                "draw": draw_res, "error": draw_res.get("error")}
