"""Session replay — turn an audit JSONL log into a readable HTML timeline.

Requirements §16 (audit log viewer) + §17 (task reports): a standalone, no-server
HTML page showing what the agent did — each planned step, the AI's reasoning, the
executed action and its result, verification, CLI/tool calls, and screenshots.
The builder is a pure function (entries -> HTML string), fully unit-testable.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


def _esc(v: Any) -> str:
    return html.escape(str(v), quote=True)


def _badge(ok: bool | None) -> str:
    if ok is None:
        return '<span class="b b-na">—</span>'
    return '<span class="b b-ok">ok</span>' if ok else '<span class="b b-fail">FAIL</span>'


def _row(entry: dict[str, Any]) -> str:
    ev = entry.get("event", "")
    ts_raw = entry.get("timestamp", "")
    ts = _esc(ts_raw[11:23] if isinstance(ts_raw, str) else ts_raw)
    agent = _esc(entry.get("agent", ""))
    body = ""

    if ev == "planner.step":
        why = _esc(entry.get("reasoning", ""))
        act = entry.get("planned", {}).get("action", {})
        vis = " 👁" if entry.get("vision") else ""
        body = f'<b>AI decided{vis}:</b> <code>{_esc(json.dumps(act, ensure_ascii=False))}</code>' \
               f'<div class="why">{why}</div>'
    elif ev == "planner.done":
        body = f'<b>AI: task complete.</b> <div class="why">{_esc(entry.get("reasoning",""))}</div>'
    elif ev in ("planner.invalid", "planner.error"):
        body = f'<b class="fail">AI could not decide:</b> {_esc(entry.get("error",""))}'
    elif ev == "step.planned":
        p = entry.get("planned", {})
        n = len(entry.get("elements", []) or [])
        body = f'planned: {_esc(p.get("description",""))} ' \
               f'<code>{_esc(json.dumps(p.get("action",{}), ensure_ascii=False))}</code>' \
               f' <span class="muted">({n} elements seen)</span>'
    elif ev in ("action.executed", "action.failed", "action.blocked", "action.halted"):
        res = entry.get("result", {})
        body = f'action <code>{_esc(entry.get("action",{}).get("type",""))}</code> ' \
               f'{_badge(res.get("success"))} {_esc(res.get("error") or "")}'
    elif ev == "step.completed":
        res = entry.get("result", {})
        verif = verif_safe(entry.get("verification"))
        body = f'step done {_badge(res.get("success"))}'
        if verif:
            body += (f' · verify {_badge(verif.get("passed"))} '
                     f'<span class="muted">{_esc(verif.get("method",""))}</span>')
    elif ev == "cli.executed":
        c = entry.get("cli", {})
        body = f'CLI <code>{_esc(c.get("command",""))}</code> exit={_esc(c.get("exitCode"))}' \
               f' {"(elevated)" if c.get("elevated") else ""}'
    elif ev == "cli.blocked":
        c = entry.get("cli", {})
        body = f'<b class="fail">CLI blocked:</b> <code>{_esc(c.get("command",""))}</code>'
    elif ev in ("task.started", "task.finished", "task.halted", "task.timeout",
                "task.stalled", "task.planner_failed"):
        body = f'<b>{_esc(ev)}</b> {_esc(entry.get("reason",""))}'
    else:
        body = _esc(ev)

    return f'<tr class="e-{_esc(ev).replace(".","-")}"><td class="ts">{ts}</td>' \
           f'<td class="ag">{agent}</td><td>{body}</td></tr>'


def verif_safe(v):
    return v if isinstance(v, dict) else None


def build_html_report(entries: list[dict[str, Any]], *, title: str = "Desktop-Worker session") -> str:
    """Build a standalone HTML replay from audit entries (pure function)."""
    if entries:
        sess = entries[0].get("sessionId", "")
        task = entries[0].get("taskId", "")
    else:
        sess = task = ""
    rows = "\n".join(_row(e) for e in entries)
    n_steps = sum(1 for e in entries if e.get("event") == "step.completed")
    n_ai = sum(1 for e in entries if e.get("event") == "planner.step")
    finished = next((e for e in reversed(entries)
                     if e.get("event") == "task.finished"), {})
    completed = finished.get("result", {}).get("completed")
    status = "completed" if completed else ("ended" if finished else "in progress")

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>{_esc(title)}</title><style>
body{{background:#0f1117;color:#e7eaf0;font:13px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:20px}}
h1{{font-size:18px;margin:0 0 4px}} .sub{{color:#8b93a7;font-size:12px;margin-bottom:14px}}
table{{width:100%;border-collapse:collapse}} td{{padding:5px 8px;border-bottom:1px solid #222634;vertical-align:top}}
.ts{{color:#5b6172;white-space:nowrap;font-family:Consolas,monospace}} .ag{{color:#8b93a7;white-space:nowrap}}
code{{background:#0c0e14;color:#9fd0ff;padding:1px 4px;border-radius:4px;font-family:Consolas,monospace;font-size:12px;word-break:break-all}}
.why{{color:#b9c2d6;font-style:italic;margin-top:2px}} .muted{{color:#5b6172}} .fail{{color:#e74c3c}}
.b{{padding:1px 7px;border-radius:999px;font-size:11px;font-weight:600}}
.b-ok{{background:rgba(46,204,113,.18);color:#2ecc71}} .b-fail{{background:rgba(231,76,60,.18);color:#e74c3c}}
.b-na{{background:rgba(91,97,114,.2);color:#8b93a7}}
tr.e-planner-step td{{background:rgba(74,163,255,.06)}} tr.e-task-started td,tr.e-task-finished td{{background:rgba(46,204,113,.05)}}
</style></head><body>
<h1>{_esc(title)} <span class="b {'b-ok' if completed else 'b-na'}">{_esc(status)}</span></h1>
<div class="sub">session {_esc(sess)} · task {_esc(task)} · {n_ai} AI decisions · {n_steps} steps · {len(entries)} audit events</div>
<table>{rows}</table>
</body></html>"""


def write_html_report(audit_path: Path, out_path: Path, *, title: str = "Desktop-Worker session") -> Path:
    """Read an audit JSONL file and write an HTML replay; returns the output path."""
    audit_path = Path(audit_path)
    entries: list[dict[str, Any]] = []
    if audit_path.exists():
        for line in audit_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    out_path = Path(out_path)
    out_path.write_text(build_html_report(entries, title=title), encoding="utf-8")
    return out_path
