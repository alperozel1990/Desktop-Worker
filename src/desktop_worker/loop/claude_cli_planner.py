"""Claude Code CLI planner (DW-PLANNER-AI) — no API key, no billing.

Drives the loop's planner with the user's *installed, logged-in* `claude` CLI
(subscription auth), NOT the Anthropic SDK or any API-key provider. The CLI call
is routed through the Desktop-Worker **CLI broker** — there is no raw subprocess
path here — so the planner's own model calls are risk-classified, approval-gated,
and audited like every other command.

Pipeline per step:
    build_planner_prompt(observation) -> claude -p (via broker, tools disabled,
    max-turns 1, output-format json) -> parse_planner_output -> parse_action
    (STRICT schema validation) -> PlannedStep.

Safety: model output is fully validated by the existing action schema before it
can run; anything malformed or unknown yields no step (the loop safe-stops). The
AI cannot bypass the executor's emergency-stop / approval / audit gates.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Optional

from desktop_worker.loop.task_loop import PlannedStep
from desktop_worker.schema.actions import (
    ACTION_SPECS,
    ActionValidationError,
    KNOWN_ACTION_TYPES,
    parse_action,
)
from desktop_worker.schema.observations import Observation
from desktop_worker.schema.results import ActionResult

# Flags: print mode, single turn, tools disabled, JSON envelope output.
_CLAUDE_FLAGS = '-p --output-format json --max-turns 1 --tools ""'
# Vision flags: allow ONLY the read-only Read tool (so Claude can view the
# screenshot) and one extra turn for the read. Still cannot take any action —
# every real action goes through our executor.
_CLAUDE_FLAGS_VISION = '-p --output-format json --max-turns 2 --allowedTools Read'

_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp")

# Mouse action types that accept x/y (so an elementId can be resolved to coords).
_COORD_ACTIONS = frozenset({
    "mouse.move", "mouse.click", "mouse.doubleClick", "mouse.rightClick",
})


# --- pure helpers --------------------------------------------------------

def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        # drop the opening fence line (``` or ```json) and the closing fence
        nl = t.find("\n")
        if nl != -1:
            t = t[nl + 1:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[: -3]
    return t.strip()


def _first_json_object(text: str) -> Optional[dict[str, Any]]:
    """Extract the best balanced JSON object from a string, or None.

    Scans every '{' for a decodable object (tolerating surrounding prose) and
    PREFERS the object that actually looks like a planner answer (has "action"
    or "done"), so a stray prose object emitted before the answer is not picked.
    """
    decoder = json.JSONDecoder()
    candidates: list[dict[str, Any]] = []
    start = text.find("{")
    while start != -1:
        try:
            obj, _ = decoder.raw_decode(text[start:])
            if isinstance(obj, dict):
                candidates.append(obj)
        except json.JSONDecodeError:
            pass
        start = text.find("{", start + 1)
    if not candidates:
        return None
    for obj in candidates:
        if "action" in obj or "done" in obj:
            return obj
    return candidates[0]


def parse_planner_output(stdout_text: str) -> dict[str, Any]:
    """Robustly extract the planner's JSON object from claude CLI output.

    Handles both the `--output-format json` envelope (where the answer is the
    string `result` field) and raw JSON, plus markdown fences / surrounding
    prose. Raises ValueError on error envelopes or unparseable output.
    """
    text = (stdout_text or "").strip()
    if not text:
        raise ValueError("empty planner output")

    inner = text
    try:
        env = json.loads(text)
    except json.JSONDecodeError:
        env = None
    if isinstance(env, dict) and "result" in env:
        if env.get("is_error"):
            raise ValueError(f"claude returned an error: {env.get('result')!r}")
        inner = env["result"] if isinstance(env["result"], str) else json.dumps(env["result"])

    obj = _first_json_object(_strip_fences(inner))
    if obj is None:
        raise ValueError(f"no JSON object found in planner output: {inner[:200]!r}")
    return obj


def _action_catalog() -> str:
    lines = []
    for t in KNOWN_ACTION_TYPES:
        spec = ACTION_SPECS[t]
        fields = ", ".join(
            f"{f.name}{'?' if not f.required else ''}:{f.hint}" for f in spec.fields
        )
        lines.append(f"- {t}({fields}) — {spec.summary}")
    return "\n".join(lines)


def build_planner_prompt(
    task: str, observation: Observation, history: list[ActionResult],
    *, failed_note: str = "", env_context: str = "", screenshot_path: str = "",
    tools_catalog: Optional[list[dict]] = None,
    max_elements: int = 40, max_history: int = 8,
) -> str:
    """Build the instruction asking Claude for the next structured action.

    ``max_elements``/``max_history`` cap the variable sections — lowering them
    (frugal mode) shrinks the prompt and the per-step Claude cost.
    """
    env = f"\nEnvironment:\n{env_context}" if env_context else ""
    tools = ""
    if tools_catalog:
        rows = "\n".join(f"  - {t['name']}({t['args']}) — {t['description']}"
                         for t in tools_catalog)
        tools = (
            "\nReliable TOOLS you may call (PREFER a tool when it matches the task — "
            "it is more reliable and cheaper than many manual steps) via "
            '{"action":{"type":"tool.run","tool":"<name>","args":{...}}}:\n' + rows
        )
    vision = (
        f"\nThe accessibility element list above may be incomplete for this app. "
        f"A screenshot of the current screen is saved at {screenshot_path} — use your "
        f"Read tool to VIEW it, then choose the next action based on what you see "
        f"(give pixel coordinates for clicks when the element has no id)."
        if screenshot_path else ""
    )
    elements = ""
    if observation.elements:
        # Number elements by id so the AI targets a REAL element (no invented
        # coordinates): it returns "elementId" and we resolve it to the element's
        # center against THIS observation.
        elements = "\n".join(
            f"  {e.id}: {e.type} {e.text!r} {list(e.bounds)} [{e.source}]"
            for e in observation.elements[:max_elements]
        )
        elements = f"\nVisible UI elements (target these by elementId):\n{elements}"

    # Memory: what you already TRIED and what RESULTED. This is how you avoid
    # repeating actions that don't work — reason over your own action/outcome trace.
    hist = ""
    if history:
        lines = []
        for r in history[-max_history:]:
            d = r.detail or {}
            what = d.get("actionStr", r.action_type)
            why = d.get("reasoning", "")
            if not r.success:
                effect = f"ERROR: {r.error}"
            elif d.get("screenChanged") is False:
                effect = "ran but the screen did NOT change (no visible effect)"
            elif d.get("screenChanged") is True:
                effect = "screen changed"
            else:
                effect = "ok"
            why_txt = f" [you reasoned: {why}]" if why else ""
            lines.append(f"  - {what}{why_txt} => {effect}")
        hist = ("\nActions you ALREADY tried this task (oldest first) — if an action "
                "had no effect or errored, do NOT repeat it, try a different approach:\n"
                + "\n".join(lines))

    fail = f"\nThe previous step FAILED: {failed_note}\nRe-observe and propose a corrected next step." if failed_note else ""

    return f"""You are the planner for Desktop-Worker, an AI agent controlling a real Windows desktop.
TASK: {task}{env}{tools}{vision}

Current desktop observation:
  {observation.summary()}{elements}{hist}{fail}

Decide the SINGLE next action that moves the task forward, then stop. Respond with
ONLY a JSON object (no prose, no markdown fences). Either signal completion:
  {{"done": true, "reasoning": "<why the task is complete>"}}
or give the next step:
  {{"done": false, "reasoning": "<one line: what you see and why this action>",
    "action": <ACTION>, "description": "<short>", "expectedResult": {{...}},
    "elementId": "<id from the list, when clicking an element>"}}

To CLICK a visible element, set "elementId" to its id above and use action
{{"type":"mouse.click"}} (or "mouse.doubleClick"/"mouse.rightClick"); we resolve
the id to its on-screen position — do NOT guess pixel coordinates. For typing use
{{"type":"keyboard.type","text":"..."}}; for shortcuts {{"type":"keyboard.hotkey","keys":["CTRL","S"]}}.
<ACTION> must be exactly one of these structured actions:
{_action_catalog()}

Rules: output valid JSON only; prefer clicking elements by elementId over raw
coordinates; take one small verifiable step; set expectedResult when you can
(e.g. {{"activeWindowContains":"Notepad"}}, {{"visibleTextContains":"Done"}} or
{{"fileExists":"C:\\\\path\\\\to\\\\file.txt"}}); say done:true only when the task
is actually achieved."""


# --- availability check --------------------------------------------------

def claude_available(broker: Any, cwd: str) -> bool:
    """Return True if the installed claude CLI reports a logged-in session.

    Runs `claude auth status` through the broker (no raw subprocess).
    """
    try:
        res = broker.run("claude auth status", cwd, elevated=False)
    except Exception:
        return False
    out = _read_stdout(res)
    try:
        data = json.loads(_first_json_text(out))
        return bool(data.get("loggedIn"))
    except Exception:
        return False


def _first_json_text(text: str) -> str:
    obj = _first_json_object(text or "")
    return json.dumps(obj) if obj is not None else (text or "")


def _read_stdout(res: Any) -> str:
    ref = getattr(res, "stdoutRef", None)
    if ref:
        try:
            return Path(ref).read_text(encoding="utf-8")
        except OSError:
            pass
    return getattr(res, "stdoutTail", "") or ""


# --- the planner ---------------------------------------------------------

AskFn = Callable[[str], str]


class ClaudeCliPlanner:
    """A loop Planner that asks the logged-in claude CLI for the next action."""

    def __init__(
        self,
        *,
        task: str,
        broker: Any,
        cwd: str,
        ask: Optional[AskFn] = None,
        claude_path: str = "claude",
        audit: Any = None,
        env_context: str = "",
        vision: bool = False,
        vision_threshold: int = 4,
        max_vision_steps: int = 6,
        tools_catalog: Optional[list[dict]] = None,
        frugal: bool = False,
    ) -> None:
        self.task = task
        self.broker = broker
        self.cwd = cwd
        self.claude_path = claude_path
        self.audit = audit
        self.env_context = env_context
        self.tools_catalog = tools_catalog
        # Frugal mode: smaller prompt (fewer elements + shorter history) => fewer
        # input tokens per step => less Claude usage. Tools already cut total steps.
        self.frugal = frugal
        self._max_elements = 12 if frugal else 40
        self._max_history = 4 if frugal else 8
        # Vision FALLBACK: attach a screenshot only when the UIA element list is
        # sparse (< vision_threshold) — so the costly image call is made only when
        # the cheap accessibility data is insufficient (e.g. Electron/custom UIs).
        self.vision = vision
        self.vision_threshold = vision_threshold
        # Hard cap on costly vision steps per task (a low-UIA app is sparse on
        # EVERY step, so without a cap vision could fire every step). Once hit, the
        # planner falls back to text-only for the rest of the task.
        self.max_vision_steps = max_vision_steps
        self.vision_steps_used = 0
        self._vision_active = False  # whether the CURRENT call uses vision
        # Injectable for tests; default routes through the broker.
        self._ask: AskFn = ask or self._ask_via_broker
        # Last decision (for explain-before-execute printing by the `do` command).
        self.last_reasoning: str = ""
        self.last_done_reason: str = ""
        # Why the last _plan returned None: "done" | "error" | "invalid" | "step".
        # Lets the loop tell genuine completion from a failed/blocked AI call.
        self.last_outcome: str = "done"
        # Human-readable reason for the last failure (e.g. the claude CLI error),
        # surfaced to the user so a cryptic "invalid" isn't all they see.
        self.last_error: str = ""

    # Planner protocol -------------------------------------------------
    def _vision_path(self, observation: Observation, force: bool = False) -> str:
        """Return a real screenshot path to send to vision, or '' to stay text-only.

        Only triggers when vision is enabled AND the accessibility element list is
        sparse AND a real image screenshot exists (cost is incurred only when the
        cheap UIA data is insufficient).
        """
        if not self.vision or self.vision_steps_used >= self.max_vision_steps:
            return ""
        # Trigger when UIA is sparse OR (forced) right after a drawing action, where
        # the result is on the canvas which UIA can't see — so the AI can look.
        if not force and len(observation.elements) >= self.vision_threshold:
            return ""
        ref = observation.screenshotRef or ""
        if ref and Path(ref).suffix.lower() in _IMAGE_SUFFIXES and Path(ref).exists():
            return ref
        return ""

    def _activate_vision(self, observation: Observation, force: bool = False) -> str:
        shot = self._vision_path(observation, force=force)
        self._vision_active = bool(shot)
        if shot:
            self.vision_steps_used += 1
        return shot

    @staticmethod
    def _drew_last(history: list[ActionResult]) -> bool:
        from desktop_worker.loop.task_loop import _DRAW_ACTIONS
        if not history:
            return False
        last = history[-1]
        if last.action_type in _DRAW_ACTIONS:
            return True
        # A `sketch` tool.run renders to the canvas (UIA can't see it) — force ONE
        # look so the AI can critique its drawing and optionally correct it. The
        # executor records the tool name explicitly in the action detail.
        if last.action_type == "tool.run":
            return (last.detail or {}).get("tool") == "sketch"
        return False

    @staticmethod
    def _sketch_canvas(history: list[ActionResult]) -> Optional[tuple]:
        """Canvas rect [l,t,r,b] from the last action if it was a sketch, else None."""
        if not history or history[-1].action_type != "tool.run":
            return None
        result = (history[-1].detail or {}).get("result") or {}
        canvas = result.get("canvas")
        if isinstance(canvas, (list, tuple)) and len(canvas) == 4:
            return tuple(canvas)
        return None

    def _crop_for_sketch(self, shot: str, history: list[ActionResult]) -> str:
        """If the last action drew with `sketch`, crop the screenshot to the canvas.

        A canvas-cropped image shows the drawing large and clear so the critique is
        accurate. Best-effort: falls back to the full screenshot if PIL is absent
        or cropping fails.
        """
        rect = self._sketch_canvas(history)
        if not shot or rect is None:
            return shot
        from desktop_worker.geometry import CanvasRect, crop_to_canvas
        dest = str(Path(shot).with_name(Path(shot).stem + "_canvas.png"))
        # source="crop": a reconstructed rect for cropping only, not a fresh detection.
        cropped = crop_to_canvas(shot, CanvasRect(*rect, source="crop"), dest)
        return cropped or shot

    def next_step(self, observation: Observation, history: list[ActionResult]) -> Optional[PlannedStep]:
        shot = self._activate_vision(observation, force=self._drew_last(history))
        shot = self._crop_for_sketch(shot, history)
        prompt = build_planner_prompt(self.task, observation, history,
                                      env_context=self.env_context, screenshot_path=shot,
                                      tools_catalog=self.tools_catalog,
                                      max_elements=self._max_elements,
                                      max_history=self._max_history)
        return self._plan(prompt, observation)

    def replan(self, failed: PlannedStep, observation: Observation,
               history: list[ActionResult]) -> Optional[PlannedStep]:
        note = f"{failed.action} ({failed.description})"
        shot = self._activate_vision(observation, force=self._drew_last(history))
        shot = self._crop_for_sketch(shot, history)
        prompt = build_planner_prompt(self.task, observation, history,
                                      failed_note=note, env_context=self.env_context,
                                      screenshot_path=shot, tools_catalog=self.tools_catalog,
                                      max_elements=self._max_elements,
                                      max_history=self._max_history)
        return self._plan(prompt, observation)

    # internals --------------------------------------------------------
    def _resolve_element(self, obj: dict, action_data: dict, observation: Observation):
        """If the AI targeted an element by id, inject its center coordinates.

        Resolves against THIS observation's elements (no invented coordinates).
        Returns the updated action_data, or None if an elementId was given for a
        mouse action but doesn't match any current element (stale/hallucinated) —
        so the caller rejects it instead of clicking at the wrong place.
        """
        eid = obj.get("elementId")
        atype = action_data.get("type")
        # Only mouse actions accept x/y; never inject coords into keyboard/etc.
        if not eid or atype not in _COORD_ACTIONS or "x" in action_data:
            return action_data
        for el in observation.elements:
            if el.id == eid:
                left, top, right, bottom = el.bounds
                action_data = dict(action_data)
                action_data["x"] = (left + right) // 2
                action_data["y"] = (top + bottom) // 2
                return action_data
        return None  # unknown/stale elementId — reject rather than misclick

    def _plan(self, prompt: str, observation: Observation) -> Optional[PlannedStep]:
        self.last_reasoning = ""
        try:
            raw = self._ask(prompt)
        except Exception as exc:  # noqa: BLE001 — a planner I/O failure must not crash the loop
            self.last_outcome = "error"
            self.last_error = f"AI call failed: {exc}"
            self._log("planner.error", error=self.last_error)
            return None

        try:
            obj = parse_planner_output(raw)
        except ValueError as exc:
            self.last_outcome = "invalid"
            self.last_error = str(exc)
            self._log("planner.invalid", error=str(exc))
            return None

        self.last_reasoning = str(obj.get("reasoning", "")).strip()

        if obj.get("done") is True:
            self.last_outcome = "done"
            self.last_error = ""
            self.last_done_reason = self.last_reasoning
            self._log("planner.done", reasoning=self.last_reasoning)
            return None

        action_data = obj.get("action")
        if not isinstance(action_data, dict):
            self.last_outcome = "invalid"
            self.last_error = "AI returned no action"
            self._log("planner.invalid", error="missing 'action' object")
            return None

        action_data = self._resolve_element(obj, action_data, observation)
        if action_data is None:
            self.last_outcome = "invalid"
            self.last_error = f"AI targeted an unknown element ({obj.get('elementId')!r})"
            self._log("planner.invalid", error=f"unknown elementId: {obj.get('elementId')!r}")
            return None

        try:
            action = parse_action(action_data)  # STRICT schema validation
        except ActionValidationError as exc:
            self.last_outcome = "invalid"
            self.last_error = f"AI proposed an invalid action: {exc}"
            self._log("planner.invalid", error=f"action rejected: {exc}")
            return None

        self.last_outcome = "step"
        self.last_error = ""
        self._log("planner.step", reasoning=self.last_reasoning, vision=self._vision_active,
                  planned={"action": action.to_dict(), "elementId": obj.get("elementId")})
        return PlannedStep(
            action=action,
            description=str(obj.get("description", action.summary)),
            expected=obj.get("expectedResult", {}) if isinstance(obj.get("expectedResult"), dict) else {},
            reasoning=self.last_reasoning,
        )

    def _ask_via_broker(self, prompt: str) -> str:
        """Run claude through the CLI broker, prompt delivered via stdin file."""
        cli_dir = Path(getattr(self.broker, "cli_dir", None) or self.cwd)
        try:
            cli_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            cli_dir = Path(self.cwd)
        fd, name = tempfile.mkstemp(suffix=".txt", prefix="dw_planner_", dir=str(cli_dir))
        os.close(fd)
        prompt_file = Path(name)
        try:
            prompt_file.write_text(prompt, encoding="utf-8")
            # Prompt goes via stdin redirection so it never touches the command
            # line (no quoting/injection); only fixed flags + a controlled path do.
            # Vision steps allow the read-only Read tool so Claude can view the
            # screenshot; non-vision steps keep all tools disabled.
            flags = _CLAUDE_FLAGS_VISION if self._vision_active else _CLAUDE_FLAGS
            command = f'{self.claude_path} {flags} < "{prompt_file}"'
            res = self.broker.run(command, self.cwd, elevated=False,
                                  agent="Claude CLI Planner", role="planner")
            if getattr(res, "blocked", False):
                raise RuntimeError(f"broker blocked the planner call: {getattr(res, 'blockedReason', '')}")
            return _read_stdout(res)
        finally:
            try:
                prompt_file.unlink()
            except OSError:
                pass

    def _log(self, event: str, **fields: Any) -> None:
        if self.audit is not None:
            try:
                self.audit.record(event, agent="Claude CLI Planner", role="planner", **fields)
            except Exception:
                pass
