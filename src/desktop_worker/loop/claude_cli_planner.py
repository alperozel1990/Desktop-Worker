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
    *, failed_note: str = "", env_context: str = "",
) -> str:
    """Build the instruction asking Claude for the next structured action."""
    env = f"\nEnvironment:\n{env_context}" if env_context else ""
    elements = ""
    if observation.elements:
        # Number elements by id so the AI targets a REAL element (no invented
        # coordinates): it returns "elementId" and we resolve it to the element's
        # center against THIS observation.
        elements = "\n".join(
            f"  {e.id}: {e.type} {e.text!r} {list(e.bounds)} [{e.source}]"
            for e in observation.elements[:40]
        )
        elements = f"\nVisible UI elements (target these by elementId):\n{elements}"

    hist = ""
    if history:
        recent = history[-4:]
        hist = "\nRecent results:\n" + "\n".join(
            f"  {r.action_type}: {'ok' if r.success else 'FAILED ' + (r.error or '')}"
            for r in recent
        )

    fail = f"\nThe previous step FAILED: {failed_note}\nRe-observe and propose a corrected next step." if failed_note else ""

    return f"""You are the planner for Desktop-Worker, an AI agent controlling a real Windows desktop.
TASK: {task}{env}

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
(e.g. {{"activeWindowContains":"Notepad"}} or {{"visibleTextContains":"Done"}});
say done:true only when the task is actually achieved."""


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
    ) -> None:
        self.task = task
        self.broker = broker
        self.cwd = cwd
        self.claude_path = claude_path
        self.audit = audit
        self.env_context = env_context
        # Injectable for tests; default routes through the broker.
        self._ask: AskFn = ask or self._ask_via_broker
        # Last decision (for explain-before-execute printing by the `do` command).
        self.last_reasoning: str = ""
        self.last_done_reason: str = ""
        # Why the last _plan returned None: "done" | "error" | "invalid" | "step".
        # Lets the loop tell genuine completion from a failed/blocked AI call.
        self.last_outcome: str = "done"

    # Planner protocol -------------------------------------------------
    def next_step(self, observation: Observation, history: list[ActionResult]) -> Optional[PlannedStep]:
        prompt = build_planner_prompt(self.task, observation, history,
                                      env_context=self.env_context)
        return self._plan(prompt, observation)

    def replan(self, failed: PlannedStep, observation: Observation,
               history: list[ActionResult]) -> Optional[PlannedStep]:
        note = f"{failed.action} ({failed.description})"
        prompt = build_planner_prompt(self.task, observation, history,
                                      failed_note=note, env_context=self.env_context)
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
            self._log("planner.error", error=f"ask failed: {exc}")
            return None

        try:
            obj = parse_planner_output(raw)
        except ValueError as exc:
            self.last_outcome = "invalid"
            self._log("planner.invalid", error=str(exc))
            return None

        self.last_reasoning = str(obj.get("reasoning", "")).strip()

        if obj.get("done") is True:
            self.last_outcome = "done"
            self.last_done_reason = self.last_reasoning
            self._log("planner.done", reasoning=self.last_reasoning)
            return None

        action_data = obj.get("action")
        if not isinstance(action_data, dict):
            self.last_outcome = "invalid"
            self._log("planner.invalid", error="missing 'action' object")
            return None

        action_data = self._resolve_element(obj, action_data, observation)
        if action_data is None:
            self.last_outcome = "invalid"
            self._log("planner.invalid", error=f"unknown elementId: {obj.get('elementId')!r}")
            return None

        try:
            action = parse_action(action_data)  # STRICT schema validation
        except ActionValidationError as exc:
            self.last_outcome = "invalid"
            self._log("planner.invalid", error=f"action rejected: {exc}")
            return None

        self.last_outcome = "step"
        self._log("planner.step", reasoning=self.last_reasoning,
                  planned={"action": action.to_dict(), "elementId": obj.get("elementId")})
        return PlannedStep(
            action=action,
            description=str(obj.get("description", action.summary)),
            expected=obj.get("expectedResult", {}) if isinstance(obj.get("expectedResult"), dict) else {},
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
            command = f'{self.claude_path} {_CLAUDE_FLAGS} < "{prompt_file}"'
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
