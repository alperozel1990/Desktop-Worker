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
    *, failed_note: str = "",
) -> str:
    """Build the instruction asking Claude for the next structured action."""
    elements = ""
    if observation.elements:
        elements = "\n".join(
            f"  [{e.source}] {e.type} {e.text!r} {list(e.bounds)}"
            for e in observation.elements[:25]
        )
        elements = f"\nDetected UI elements (UIA preferred, OCR fallback):\n{elements}"

    hist = ""
    if history:
        recent = history[-3:]
        hist = "\nRecent results:\n" + "\n".join(
            f"  {r.action_type}: {'ok' if r.success else 'FAILED ' + (r.error or '')}"
            for r in recent
        )

    fail = f"\nThe previous step FAILED: {failed_note}\nPropose a corrected next step." if failed_note else ""

    return f"""You are the planner for Desktop-Worker, controlling a Windows desktop.
TASK: {task}

Current desktop observation:
  {observation.summary()}{elements}{hist}{fail}

Decide the SINGLE next action. Respond with ONLY a JSON object, no prose, no
markdown fences. Either signal completion:
  {{"done": true}}
or give the next step:
  {{"done": false, "action": <ACTION>, "description": "<short>", "expectedResult": {{...}}}}
where <ACTION> is exactly one of these structured actions (use these types/fields):
{_action_catalog()}

Rules: output valid JSON only; pick coordinates from the observation/elements when
possible; prefer one small, verifiable step; set expectedResult when you can (e.g.
{{"activeWindowContains": "Chrome"}} or {{"visibleTextContains": "Done"}})."""


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
    ) -> None:
        self.task = task
        self.broker = broker
        self.cwd = cwd
        self.claude_path = claude_path
        self.audit = audit
        # Injectable for tests; default routes through the broker.
        self._ask: AskFn = ask or self._ask_via_broker

    # Planner protocol -------------------------------------------------
    def next_step(self, observation: Observation, history: list[ActionResult]) -> Optional[PlannedStep]:
        return self._plan(build_planner_prompt(self.task, observation, history))

    def replan(self, failed: PlannedStep, observation: Observation,
               history: list[ActionResult]) -> Optional[PlannedStep]:
        note = f"{failed.action} ({failed.description})"
        return self._plan(build_planner_prompt(self.task, observation, history, failed_note=note))

    # internals --------------------------------------------------------
    def _plan(self, prompt: str) -> Optional[PlannedStep]:
        try:
            raw = self._ask(prompt)
        except Exception as exc:  # noqa: BLE001 — a planner I/O failure must not crash the loop
            self._log("planner.error", error=f"ask failed: {exc}")
            return None

        try:
            obj = parse_planner_output(raw)
        except ValueError as exc:
            self._log("planner.invalid", error=str(exc))
            return None

        if obj.get("done") is True:
            self._log("planner.done")
            return None

        action_data = obj.get("action")
        if not isinstance(action_data, dict):
            self._log("planner.invalid", error="missing 'action' object")
            return None

        try:
            action = parse_action(action_data)  # STRICT schema validation
        except ActionValidationError as exc:
            self._log("planner.invalid", error=f"action rejected: {exc}")
            return None

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
