"""Offline rendering of a drawing Program to a PNG — no mouse, no Paint.

Used for the pre-ink self-check and the best-of-N montage: the AI proposes
programs, we render them here, score/pick, and only THEN draw the winner on the
real canvas. PIL is imported lazily; if absent, functions return ``None`` and the
caller degrades gracefully (the core stays dependency-free).
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from desktop_worker.geometry.canvas import CanvasRect
from desktop_worker.geometry.render import compile_program


def render_program_png(program, dest: str, *, size: int = 512, margin: int = 24,
                       line_width: int = 4) -> Optional[str]:
    """Render a Program to a square PNG at ``dest``; None if PIL is unavailable."""
    try:
        from PIL import Image, ImageDraw  # type: ignore
    except Exception:
        return None
    canvas = CanvasRect(margin, margin, size - margin, size - margin, source="preview")
    strokes = compile_program(program, canvas)
    img = Image.new("RGB", (size, size), "white")
    d = ImageDraw.Draw(img)
    for pts in strokes:
        if len(pts) >= 2:
            d.line([(x, y) for x, y in pts], fill="black", width=line_width, joint="curve")
        elif pts:
            x, y = pts[0]
            d.ellipse([x-2, y-2, x+2, y+2], fill="black")
    try:
        img.save(dest)
    except Exception:
        return None
    return dest


def montage_png(image_paths: Sequence[str], dest: str, *, cell: int = 320,
                cols: int = 3, label: bool = True) -> Optional[str]:
    """Combine candidate PNGs into one labelled grid (for the AI judge); None if no PIL."""
    try:
        from PIL import Image, ImageDraw  # type: ignore
    except Exception:
        return None
    paths = [p for p in image_paths if p]
    if not paths:
        return None
    cols = max(1, min(cols, len(paths)))
    rows = (len(paths) + cols - 1) // cols
    pad = 8
    W = cols * cell + (cols + 1) * pad
    H = rows * cell + (rows + 1) * pad
    sheet = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(sheet)
    for idx, p in enumerate(paths):
        r, c = divmod(idx, cols)
        x0 = pad + c * (cell + pad)
        y0 = pad + r * (cell + pad)
        try:
            with Image.open(p) as im:
                sheet.paste(im.resize((cell, cell)), (x0, y0))
        except Exception:
            continue
        draw.rectangle([x0, y0, x0 + cell - 1, y0 + cell - 1], outline="black")
        if label:
            draw.text((x0 + 6, y0 + 4), f"#{idx + 1}", fill="red")
    try:
        sheet.save(dest)
    except Exception:
        return None
    return dest
