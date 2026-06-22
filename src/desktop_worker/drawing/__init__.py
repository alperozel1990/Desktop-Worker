"""Drawing orchestration: best-of-N candidate generation, AI judging, hygienic
execution, and one verification pass — the `draw "<subject>"` flagship."""

from desktop_worker.drawing.director import DrawingDirector, parse_svg_candidates

__all__ = ["DrawingDirector", "parse_svg_candidates"]
