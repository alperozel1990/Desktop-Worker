"""Tests for the DrawingDirector best-of-N pipeline (all Claude calls stubbed)."""

from desktop_worker.drawing.director import DrawingDirector, parse_svg_candidates

_SVG1 = '<svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="20"/></svg>'
_SVG2 = '<svg viewBox="0 0 100 100"><circle cx="50" cy="40" r="22"/><ellipse cx="50" cy="78" rx="15" ry="12"/></svg>'


def test_parse_svg_candidates_extracts_valid_blocks():
    text = f"Here you go:\n```svg\n{_SVG1}\n```\nand\n```svg\n{_SVG2}\n```"
    progs = parse_svg_candidates(text)
    assert len(progs) == 2
    # an invalid block is skipped, valid ones kept
    progs2 = parse_svg_candidates(f"{_SVG1}\n<svg></svg>")
    assert len(progs2) == 1


def _director(tmp_path, *, gen_text, judge_reply="2", verify_reply=None, drawn=None,
              refine=True, screenshot=None):
    drawn = drawn if drawn is not None else []

    def draw_fn(program):
        drawn.append(program)
        return {"success": True, "strokes": len(program.primitives), "error": None}

    def ask_text(prompt):
        return gen_text

    def ask_vision(prompt, image):
        return verify_reply if "screenshot" in prompt.lower() else judge_reply

    d = DrawingDirector(ask_text=ask_text, ask_vision=ask_vision, draw_fn=draw_fn,
                        work_dir=str(tmp_path), n_candidates=2, refine=refine,
                        screenshot_fn=(lambda: screenshot) if screenshot is not None else None)
    return d, drawn


def test_pipeline_picks_judged_winner_and_draws_it(tmp_path):
    gen = f"```svg\n{_SVG1}\n```\n```svg\n{_SVG2}\n```"
    d, drawn = _director(tmp_path, gen_text=gen, judge_reply="2")
    res = d.draw("a cat")
    assert res["success"] is True
    assert res["candidates"] == 2 and res["chosen"] == 2     # judge picked #2
    assert len(drawn) == 1 and drawn[0].primitives[0].kind == "circle"
    assert drawn[0] is not None and len(drawn[0].primitives) == 2  # _SVG2 has 2 shapes


def test_generate_exception_fails_safe(tmp_path):
    # A broker block / claude error during generation must NOT crash — clean dict.
    def boom(prompt):
        raise RuntimeError("broker blocked the draw call")
    d = DrawingDirector(ask_text=boom, ask_vision=lambda p, i: "1",
                        draw_fn=lambda prog: {"success": True}, work_dir=str(tmp_path))
    res = d.draw("a cat")
    assert res["success"] is False and "generation failed" in res["error"]


def test_draw_fn_exception_fails_safe(tmp_path):
    def boom_draw(prog):
        raise RuntimeError("locator exploded")
    d = DrawingDirector(ask_text=lambda p: f"```svg\n{_SVG2}\n```",
                        ask_vision=lambda p, i: "1", draw_fn=boom_draw,
                        work_dir=str(tmp_path), refine=False)
    res = d.draw("a cat")
    assert res["success"] is False and "drawing failed" in res["error"]


def test_no_candidates_fails_safe(tmp_path):
    d, drawn = _director(tmp_path, gen_text="sorry, no svg here")
    res = d.draw("a cat")
    assert res["success"] is False and "candidate" in res["error"]
    assert drawn == []


def test_judge_unparseable_defaults_to_first(tmp_path):
    gen = f"```svg\n{_SVG1}\n```\n```svg\n{_SVG2}\n```"
    d, drawn = _director(tmp_path, gen_text=gen, judge_reply="dunno")
    res = d.draw("a cat")
    assert res["chosen"] == 1                                 # fell back to #1


def test_verify_triggers_one_refine_when_not_ok(tmp_path):
    gen = f"```svg\n{_SVG1}\n```\n```svg\n{_SVG2}\n```"
    # ask_text returns the SAME gen text for both generate and refine; refine parses
    # the first svg block -> a valid corrected program, drawn a SECOND time.
    d, drawn = _director(tmp_path, gen_text=gen, judge_reply="1",
                         verify_reply='{"ok": false, "issue": "missing ears"}',
                         screenshot="shot.png", refine=True)
    res = d.draw("a cat")
    assert res["refined"] is True
    assert len(drawn) == 2                                    # initial + one correction
    assert res["verdict"] == {"ok": False, "issue": "missing ears"}


def test_verify_ok_skips_refine(tmp_path):
    gen = f"```svg\n{_SVG2}\n```"
    d, drawn = _director(tmp_path, gen_text=gen, judge_reply="1",
                         verify_reply='{"ok": true, "issue": ""}', screenshot="shot.png")
    res = d.draw("a cat")
    assert res["refined"] is False and len(drawn) == 1
