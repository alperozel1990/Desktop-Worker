"""Structured action schema.

Every action the AI requests is represented as a validated structured command
*before* execution (requirements section 8). Malformed actions never run.

An Action is intentionally a thin (type, params) record validated against a
declarative spec table. This keeps the schema easy to extend by adding a row to
``ACTION_SPECS`` rather than writing a new class per action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


class ActionValidationError(ValueError):
    """Raised when an action is malformed or fails validation."""


# --- field validators -------------------------------------------------------

def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _is_point(v: Any) -> bool:
    return (
        isinstance(v, (list, tuple))
        and len(v) == 2
        and all(_is_number(c) for c in v)
    )


def _is_str(v: Any) -> bool:
    return isinstance(v, str)


def _is_button(v: Any) -> bool:
    return v in ("left", "right", "middle")


def _is_str_list(v: Any) -> bool:
    return isinstance(v, (list, tuple)) and len(v) > 0 and all(isinstance(k, str) for k in v)


@dataclass(frozen=True)
class _FieldSpec:
    name: str
    required: bool
    check: Callable[[Any], bool]
    hint: str


@dataclass(frozen=True)
class _ActionSpec:
    type: str
    fields: tuple[_FieldSpec, ...]
    summary: str


def _f(name: str, check: Callable[[Any], bool], hint: str, required: bool = True) -> _FieldSpec:
    return _FieldSpec(name=name, required=required, check=check, hint=hint)


# Declarative registry of every supported action type and its parameter shape.
# Mirrors requirements sections 8-11. Add a row here to add an action family.
ACTION_SPECS: dict[str, _ActionSpec] = {
    spec.type: spec
    for spec in (
        # --- mouse -------------------------------------------------------
        _ActionSpec("mouse.move", (
            _f("x", _is_number, "number"), _f("y", _is_number, "number"),
        ), "Move cursor to absolute (x, y)."),
        _ActionSpec("mouse.moveRelative", (
            _f("dx", _is_number, "number"), _f("dy", _is_number, "number"),
        ), "Move cursor by (dx, dy) from current position."),
        _ActionSpec("mouse.click", (
            _f("button", _is_button, "left|right|middle", required=False),
            _f("x", _is_number, "number", required=False),
            _f("y", _is_number, "number", required=False),
        ), "Click (optionally move to x,y first)."),
        _ActionSpec("mouse.doubleClick", (
            _f("button", _is_button, "left|right|middle", required=False),
            _f("x", _is_number, "number", required=False),
            _f("y", _is_number, "number", required=False),
        ), "Double click."),
        _ActionSpec("mouse.rightClick", (
            _f("x", _is_number, "number", required=False),
            _f("y", _is_number, "number", required=False),
        ), "Right click."),
        _ActionSpec("mouse.down", (
            _f("button", _is_button, "left|right|middle", required=False),
        ), "Press and hold a mouse button."),
        _ActionSpec("mouse.up", (
            _f("button", _is_button, "left|right|middle", required=False),
        ), "Release a mouse button."),
        _ActionSpec("mouse.scroll", (
            _f("dx", _is_int, "int", required=False),
            _f("dy", _is_int, "int", required=False),
        ), "Scroll vertically/horizontally."),
        _ActionSpec("mouse.drag", (
            _f("from", _is_point, "[x, y]"),
            _f("to", _is_point, "[x, y]"),
            _f("durationMs", _is_int, "int", required=False),
        ), "Drag from one point to another."),
        # --- keyboard ----------------------------------------------------
        _ActionSpec("keyboard.type", (
            _f("text", _is_str, "string"),
        ), "Type text."),
        _ActionSpec("keyboard.press", (
            _f("key", _is_str, "string"),
        ), "Press a single key."),
        _ActionSpec("keyboard.hotkey", (
            _f("keys", _is_str_list, "list[str], e.g. ['CTRL','L']"),
        ), "Press a key combination."),
        # --- clipboard ---------------------------------------------------
        _ActionSpec("clipboard.set", (
            _f("text", _is_str, "string"),
        ), "Set clipboard text."),
        _ActionSpec("clipboard.get", (), "Read clipboard text."),
        # --- window ------------------------------------------------------
        _ActionSpec("window.focus", (
            _f("titleContains", _is_str, "string"),
        ), "Focus a window whose title contains the given text."),
        # --- control flow ------------------------------------------------
        _ActionSpec("wait", (
            _f("durationMs", _is_int, "int"),
        ), "Wait for a fixed duration."),
        # --- cli (routed through the elevated broker only) --------------
        _ActionSpec("cli.run", (
            _f("command", _is_str, "string"),
            _f("cwd", _is_str, "string"),  # explicit working dir is mandatory
            _f("timeoutMs", _is_int, "int", required=False),
            _f("elevated", lambda v: isinstance(v, bool), "bool", required=False),
        ), "Run a command through the elevated CLI broker."),
        # --- high-level tools (reliable named workflows the AI may call) -
        _ActionSpec("tool.run", (
            _f("tool", _is_str, "string"),
            _f("args", lambda v: isinstance(v, dict), "object", required=False),
        ), "Run a reliable named workflow tool (e.g. create_text_file)."),
        # --- verification ------------------------------------------------
        _ActionSpec("verify", (
            _f("visibleTextContains", _is_str, "string", required=False),
            _f("activeWindowContains", _is_str, "string", required=False),
            _f("fileExists", _is_str, "string", required=False),
        ), "Verify an expected post-condition."),
    )
}

KNOWN_ACTION_TYPES = tuple(ACTION_SPECS.keys())


@dataclass(frozen=True)
class Action:
    """A validated structured action."""

    type: str
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def spec(self) -> _ActionSpec:
        return ACTION_SPECS[self.type]

    @property
    def summary(self) -> str:
        return ACTION_SPECS[self.type].summary

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, **self.params}

    def __str__(self) -> str:  # human-friendly one-liner for logs/UI
        if self.params:
            kv = ", ".join(f"{k}={v!r}" for k, v in self.params.items())
            return f"{self.type}({kv})"
        return f"{self.type}()"


def parse_action(data: dict[str, Any]) -> Action:
    """Parse and validate a raw dict into an :class:`Action`.

    Raises :class:`ActionValidationError` for unknown types, missing required
    fields, wrong field types, or unexpected fields.
    """
    if not isinstance(data, dict):
        raise ActionValidationError(f"action must be an object, got {type(data).__name__}")
    if "type" not in data:
        raise ActionValidationError("action is missing required 'type' field")

    atype = data["type"]
    spec = ACTION_SPECS.get(atype)
    if spec is None:
        raise ActionValidationError(
            f"unknown action type {atype!r}; known: {', '.join(KNOWN_ACTION_TYPES)}"
        )

    params = {k: v for k, v in data.items() if k != "type"}
    allowed = {fs.name for fs in spec.fields}
    unexpected = set(params) - allowed
    if unexpected:
        raise ActionValidationError(
            f"{atype}: unexpected field(s) {sorted(unexpected)}; allowed: {sorted(allowed)}"
        )

    for fs in spec.fields:
        if fs.name not in params:
            if fs.required:
                raise ActionValidationError(f"{atype}: missing required field {fs.name!r}")
            continue
        if not fs.check(params[fs.name]):
            raise ActionValidationError(
                f"{atype}: field {fs.name!r} expected {fs.hint}, got {params[fs.name]!r}"
            )

    return Action(type=atype, params=params)
