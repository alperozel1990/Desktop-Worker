"""Geometry: vector drawing DSL, deterministic renderer, and canvas detection.

The "smart + controlled" drawing pipeline. The AI plans a figure as primitives on
a 0..100 grid (:mod:`dsl`); the canvas locator finds Paint's real drawing area
(:mod:`canvas`); the renderer tessellates primitives into precise per-primitive
strokes in canvas pixels (:mod:`render`). Pure and dependency-free except for the
lazily-imported Windows locator.
"""

from desktop_worker.geometry.canvas import (CanvasRect, NullCanvasLocator,
                                            apply_inner_margin, client_to_canvas,
                                            crop_to_canvas, fit_square,
                                            get_canvas_locator)
from desktop_worker.geometry.dsl import Primitive, Program, parse_program
from desktop_worker.geometry.render import compile_program, map_point, samples_for

__all__ = ["CanvasRect", "NullCanvasLocator", "get_canvas_locator", "client_to_canvas",
           "apply_inner_margin", "crop_to_canvas", "fit_square", "Primitive", "Program",
           "parse_program", "compile_program", "map_point", "samples_for"]
