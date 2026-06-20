"""DW-PLANNER-AI — Claude Code CLI planner (no API key).

Tests STUB the CLI response (via an injected `ask` callable or a fake broker) and
NEVER call the real Claude service. They verify: envelope/output parsing, strict
action-schema validation, safe failure on malformed output, and broker routing.
"""

import json

import pytest

from desktop_worker.loop.claude_cli_planner import (
    ClaudeCliPlanner,
    build_planner_prompt,
    parse_planner_output,
)
from desktop_worker.schema.observations import Cursor, Observation, Screen


def _obs():
    return Observation(screen=Screen(800, 600), cursor=Cursor(1, 2))


def _envelope(result_text: str, is_error: bool = False) -> str:
    """Mimic `claude -p --output-format json` output."""
    return json.dumps({"type": "result", "subtype": "success",
                       "is_error": is_error, "result": result_text})


# --- pure parsing --------------------------------------------------------

def test_parse_envelope_with_action_json():
    inner = '{"action": {"type": "mouse.move", "x": 5, "y": 6}, "description": "m"}'
    obj = parse_planner_output(_envelope(inner))
    assert obj["action"]["type"] == "mouse.move"


def test_parse_raw_json_without_envelope():
    raw = '{"done": true}'
    assert parse_planner_output(raw) == {"done": True}


def test_parse_strips_markdown_fences():
    inner = '```json\n{"done": true}\n```'
    assert parse_planner_output(_envelope(inner)) == {"done": True}


def test_parse_extracts_object_amid_prose():
    inner = 'Sure, here you go: {"done": true} hope that helps'
    assert parse_planner_output(_envelope(inner)) == {"done": True}


def test_parse_error_envelope_raises():
    with pytest.raises(ValueError):
        parse_planner_output(_envelope("nope", is_error=True))


def test_parse_garbage_raises():
    with pytest.raises(ValueError):
        parse_planner_output("not json at all <<<")


# --- planner behavior (stubbed ask) --------------------------------------

def _planner(response_text, **kw):
    return ClaudeCliPlanner(task="do a thing", broker=None, cwd=".",
                            ask=lambda prompt: response_text, **kw)


def test_next_step_returns_validated_action():
    resp = _envelope('{"action": {"type": "mouse.click", "button": "left"}, '
                     '"description": "click", "expectedResult": {"visibleTextContains": "ok"}}')
    step = _planner(resp).next_step(_obs(), [])
    assert step is not None
    assert step.action.type == "mouse.click"
    assert step.description == "click"
    assert step.expected == {"visibleTextContains": "ok"}


def test_done_returns_none():
    step = _planner(_envelope('{"done": true}')).next_step(_obs(), [])
    assert step is None


def test_malformed_output_fails_safe():
    step = _planner("totally broken !!!").next_step(_obs(), [])
    assert step is None        # never raises, never executes


def test_invalid_action_schema_fails_safe():
    # Unknown action type must be rejected by parse_action -> no step.
    resp = _envelope('{"action": {"type": "mouse.teleport", "x": 1, "y": 2}}')
    step = _planner(resp).next_step(_obs(), [])
    assert step is None


def test_missing_action_key_fails_safe():
    step = _planner(_envelope('{"foo": "bar"}')).next_step(_obs(), [])
    assert step is None


def test_build_prompt_mentions_task_and_allowed_types():
    prompt = build_planner_prompt("open chrome", _obs(), [])
    assert "open chrome" in prompt
    assert "mouse.click" in prompt          # allowed action types listed
    assert "JSON" in prompt or "json" in prompt


# --- broker routing (fake broker, no real claude) ------------------------

class _FakeCliResult:
    def __init__(self, stdout):
        self.stdoutRef = None
        self.stdoutTail = stdout
        self.blocked = False
        self.exitCode = 0


class FakeBroker:
    def __init__(self, stdout):
        self.stdout = stdout
        self.commands = []
        self.kwargs = []
        self.cli_dir = None  # planner falls back to cwd for the prompt temp file

    def run(self, command, cwd, **kw):
        self.commands.append(command)
        self.kwargs.append(kw)
        return _FakeCliResult(self.stdout)


def test_planner_routes_through_broker():
    resp = _envelope('{"action": {"type": "wait", "durationMs": 5}, "description": "w"}')
    broker = FakeBroker(resp)
    planner = ClaudeCliPlanner(task="t", broker=broker, cwd=".")  # default ask -> broker
    step = planner.next_step(_obs(), [])
    assert step is not None and step.action.type == "wait"
    assert broker.commands, "planner must invoke the broker"
    cmd = broker.commands[0]
    assert "claude" in cmd and "-p" in cmd
    assert '--tools' in cmd and '--max-turns' in cmd and '--output-format' in cmd


def test_planner_call_is_non_elevated_and_uses_stdin():
    resp = _envelope('{"done": true}')
    broker = FakeBroker(resp)
    ClaudeCliPlanner(task="t", broker=broker, cwd=".").next_step(_obs(), [])
    # the planner's own model call must NOT be elevated, and the prompt is piped
    # via stdin redirection (never on the command line — injection-safe).
    assert broker.kwargs[0].get("elevated") is False
    assert "< " in broker.commands[0]


def test_prefers_answer_object_over_prose_object():
    inner = 'I will use {"note": "thinking"} then answer: {"done": true}'
    assert parse_planner_output(_envelope(inner)) == {"done": True}


def test_claude_available_true_false_and_error():
    from desktop_worker.loop.claude_cli_planner import claude_available
    assert claude_available(FakeBroker('{"loggedIn": true, "subscriptionType": "max"}'), ".") is True
    assert claude_available(FakeBroker('{"loggedIn": false}'), ".") is False

    class BoomBroker:
        cli_dir = None
        def run(self, *a, **k):
            raise RuntimeError("claude missing")
    assert claude_available(BoomBroker(), ".") is False
