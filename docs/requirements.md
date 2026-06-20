# Desktop-Worker Requirements

## 1. North Star

Desktop-Worker is a local Windows desktop automation application that allows an AI agent to perform real work on a user's PC using the same interaction surfaces a human user has: screen observation, mouse, keyboard, clipboard, windows, files, browser, desktop applications, and CLI.

The final product must be AI-control-ready: an AI should be able to observe the current desktop state, decide the next action, execute it, verify the result, recover from errors, and continue until the user's task is complete.

This is not only a click automation tool. The core loop is:

1. Observe the desktop.
2. Understand the current state.
3. Plan the next step.
4. Execute a structured action.
5. Verify the result.
6. Log everything.
7. Continue, retry, ask for approval, or stop.

## 2. Non-Negotiable Requirements

The following requirements are mandatory and must be treated as project constraints:

- Desktop-Worker must run on Windows.
- The system must be able to control mouse and keyboard like a real user.
- The system must be able to take screenshots and expose them to the AI.
- The system must know the current mouse position.
- The system must support drag and drop.
- The system must support browser and desktop application workflows.
- The system must support CLI execution.
- All CLI execution must be routed through an elevated/admin-capable command broker by default.
- Elevated CLI operations must include command preview, working directory isolation, output capture, exit-code reporting, audit logging, risk classification, and user approval for dangerous operations.
- The system must include safety controls from the first milestone, not as a later add-on.
- The system must include an emergency stop mechanism.
- Every action must be logged.
- Every action should be followed by observation and verification.
- The architecture must support multi-agent planning, implementation, and auditing.

## 3. Target User Experience

The user should be able to give Desktop-Worker a natural language task such as:

> Open Chrome, go to the given website, fill out the form, upload this file, submit the request, download the result, and save it to the project folder.

Desktop-Worker should then:

1. Capture the desktop state.
2. Ask the AI to plan the next step.
3. Execute mouse, keyboard, clipboard, window, file, browser, or CLI actions.
4. Verify that each step worked.
5. Ask the user for approval when an action is risky.
6. Produce a final report with what was done, what succeeded, what failed, and where outputs were saved.

## 4. Agent Organization

Desktop-Worker must be built with a multi-agent operating model inspired by the existing autonomous project pattern.

### 4.1 Claude Strategist

Claude Strategist is the main planner and task coordinator.

Responsibilities:

- Own the product roadmap.
- Break high-level project goals into implementation tasks.
- Spawn implementer agents for scoped work.
- Define acceptance criteria for each task.
- Track progress against the roadmap.
- Incorporate auditor feedback.
- Keep the project aligned with the AI-control-ready north star.

### 4.2 Implementer Agents

Implementer agents perform scoped implementation work.

Example implementation areas:

- Screenshot capture.
- Mouse control.
- Keyboard control.
- Clipboard integration.
- Window management.
- UI Automation integration.
- OCR integration.
- Action schema.
- Elevated CLI broker.
- Audit log.
- Permission policy engine.
- Task execution loop.
- Browser workflow support.
- Replay/debug tooling.

Implementers must receive narrow tasks with clear acceptance criteria and must return a concise implementation report.

### 4.3 Codex Auditor

Codex Auditor reviews code quality, test coverage, implementation risks, and technical correctness.

Responsibilities:

- Review implementation changes.
- Identify bugs, regressions, missing tests, and unsafe assumptions.
- Pay special attention to desktop control, elevated CLI, filesystem access, permissions, and process execution.
- Check whether changes are consistent with the existing architecture.
- Report findings before summaries.

### 4.4 Northstar Auditor

Northstar Auditor reviews the overall direction of the project.

Responsibilities:

- Evaluate whether the roadmap is still aligned with the product north star.
- Identify architectural drift.
- Identify missing safety, auditability, observability, and user-control mechanisms.
- Challenge features that make the system less reliable or less controllable.
- Confirm whether the product is becoming genuinely AI-control-ready.

## 5. System Architecture Requirements

The architecture should be modular. At minimum, the system must contain these layers:

1. Desktop Observation Layer
2. Perception Layer
3. Action Layer
4. Elevated CLI Broker
5. Permission and Safety Layer
6. Audit and Replay Layer
7. Agent Orchestration Layer
8. User Interface Layer

Each layer must expose clear interfaces and structured data. Avoid hidden side effects and ad hoc command strings where structured actions are possible.

## 6. Desktop Observation Requirements

Desktop-Worker must be able to observe the desktop state.

Required capabilities:

- Capture full-screen screenshots.
- Capture active-window screenshots where possible.
- Read screen dimensions and scaling.
- Read current cursor position.
- Include cursor position in observation metadata.
- Optionally render cursor marker into debug screenshots.
- Detect active window title and process.
- List visible windows.
- Track focused window.
- Support multi-monitor setups eventually, but single-monitor support is acceptable for the first MVP.

Observation output must be structured.

Example:

```json
{
  "timestamp": "2026-06-20T10:00:00Z",
  "screen": {
    "width": 1920,
    "height": 1080,
    "scaleFactor": 1.0
  },
  "cursor": {
    "x": 812,
    "y": 431
  },
  "activeWindow": {
    "title": "Example - Google Chrome",
    "process": "chrome.exe",
    "bounds": [0, 0, 1920, 1080]
  },
  "screenshotRef": "artifacts/screenshots/step-0001.png"
}
```

## 7. Perception Requirements

Desktop-Worker must help the AI understand what is visible on screen.

Required capabilities:

- OCR for visible text.
- UI element detection for common controls.
- Button, input, checkbox, radio, dropdown, tab, menu, modal, link, table, list, and icon detection where possible.
- Element bounding boxes.
- Confidence scores for detected elements.
- Structured observation summaries for AI prompts.
- Raw screenshot access for vision-capable models.

Important architectural requirement:

> Visual coordinate automation alone is not enough. Desktop-Worker must use Windows UI Automation or Accessibility APIs where available, and use screenshot/OCR/vision as fallback.

Perception output example:

```json
{
  "elements": [
    {
      "id": "element-17",
      "type": "button",
      "text": "Submit",
      "bounds": [700, 400, 820, 440],
      "confidence": 0.91,
      "source": "uia"
    },
    {
      "id": "element-18",
      "type": "input",
      "label": "Email",
      "bounds": [420, 315, 760, 350],
      "confidence": 0.84,
      "source": "ocr"
    }
  ]
}
```

## 8. Action Requirements

All actions must be represented as structured commands before execution.

Required action families:

- Mouse actions.
- Keyboard actions.
- Clipboard actions.
- Window actions.
- Filesystem actions.
- Browser-oriented actions where available.
- CLI actions.
- Wait actions.
- Verification actions.

Example actions:

```json
{ "type": "mouse.move", "x": 500, "y": 300 }
{ "type": "mouse.click", "button": "left" }
{ "type": "mouse.doubleClick", "button": "left" }
{ "type": "mouse.rightClick" }
{ "type": "mouse.drag", "from": [100, 100], "to": [600, 400], "durationMs": 600 }
{ "type": "keyboard.type", "text": "hello world" }
{ "type": "keyboard.hotkey", "keys": ["CTRL", "L"] }
{ "type": "clipboard.set", "text": "value to paste" }
{ "type": "window.focus", "titleContains": "Chrome" }
{ "type": "wait", "durationMs": 1000 }
{ "type": "cli.run", "command": "npm test", "cwd": "C:\\Desktop-Worker" }
```

Action execution requirements:

- Validate each action before execution.
- Record action start time and end time.
- Capture success or failure.
- Capture error details.
- Capture observation before and after important actions.
- Support retries with limits.
- Never execute malformed actions.
- Never execute high-risk actions without policy approval.

## 9. Mouse and Keyboard Requirements

Mouse capabilities:

- Move to absolute coordinates.
- Move relative to current position.
- Left click.
- Right click.
- Double click.
- Press and hold.
- Release.
- Scroll vertical and horizontal where supported.
- Drag and drop from one coordinate to another.
- Query current cursor position.

Keyboard capabilities:

- Type text.
- Press individual keys.
- Press key combinations.
- Hold and release modifier keys.
- Support common shortcuts such as Ctrl+C, Ctrl+V, Ctrl+L, Alt+Tab, Enter, Escape, Tab, Shift+Tab.
- Use clipboard paste for long text where appropriate.

The system must account for keyboard layout and text entry reliability.

## 10. Browser and Desktop Workflow Requirements

Desktop-Worker must be able to operate inside Chrome and common desktop applications.

Browser workflow capabilities:

- Open a URL.
- Focus address bar.
- Navigate pages.
- Click links and buttons.
- Fill forms.
- Select dropdowns.
- Upload files through file picker dialogs.
- Download files.
- Detect page load states where possible.
- Handle modals, popups, and confirmation dialogs.

Desktop workflow capabilities:

- Open applications.
- Switch windows.
- Use native dialogs.
- Work with file explorer.
- Select files.
- Move or copy files.
- Use drag and drop.
- Read visible status messages.

## 11. Elevated CLI Broker Requirements

This is a core requirement.

All CLI operations must be routed through an elevated/admin-capable command execution broker by default. The broker must be designed as a controlled execution boundary, not as a raw unrestricted shell.

The CLI broker must support:

- Elevated/admin command execution.
- Explicit working directory for every command.
- Command preview before execution.
- stdout capture.
- stderr capture.
- exit code capture.
- timeout handling.
- environment variable control.
- structured execution result.
- command history.
- audit logging.
- risk classification.
- user approval gates.
- session-scoped allow rules.

Structured result example:

```json
{
  "command": "npm test",
  "cwd": "C:\\Desktop-Worker",
  "startedAt": "2026-06-20T10:00:00Z",
  "endedAt": "2026-06-20T10:00:05Z",
  "exitCode": 0,
  "stdoutRef": "artifacts/cli/0007.stdout.txt",
  "stderrRef": "artifacts/cli/0007.stderr.txt",
  "elevated": true,
  "riskLevel": "low",
  "approvedByUser": false
}
```

Risk classification examples:

- Low risk: read-only commands, version checks, test commands.
- Medium risk: package installation, file writes inside project directory, local service start.
- High risk: deletion, registry edits, service changes, firewall changes, startup changes, credential access, system directory changes, permission changes, process killing outside the project scope.

High-risk CLI operations must require explicit user approval.

The AI must not be able to silently bypass the elevated broker. The broker is the only supported CLI execution path.

## 12. Safety Requirements

Safety is a product feature and must be present from the beginning.

Required safety features:

- Global pause.
- Global emergency stop.
- Clear current-task status.
- Action timeline.
- Permission profiles.
- Approval prompts for high-risk actions.
- Dry-run mode.
- Explain-before-execute mode.
- Maximum retry limits.
- Maximum action limits per task.
- Maximum time limits per task.
- Application allowlist or denylist support.
- Filesystem scope policies.
- CLI command risk policies.

Actions that should normally require approval:

- Deleting files outside a temporary workspace.
- Modifying system files.
- Editing registry.
- Changing services.
- Changing firewall or network settings.
- Installing software.
- Uninstalling software.
- Sending payments.
- Submitting irreversible forms.
- Accessing credentials or secrets.
- Uploading private files to remote services.

The user must always remain in control.

## 13. Audit Log Requirements

Every meaningful operation must be logged.

The audit log must include:

- Timestamp.
- Session ID.
- Task ID.
- Agent name.
- Agent role.
- Observation reference.
- Planned step.
- Executed action.
- Action parameters.
- Result.
- Error details.
- CLI command details if applicable.
- User approval details if applicable.
- Screenshot references before and after the action where applicable.
- Verification result.

The audit log must be machine-readable and human-readable.

Recommended format:

- JSONL for machine logs.
- Optional UI timeline for human inspection.

Example JSONL entry:

```json
{
  "timestamp": "2026-06-20T10:00:00Z",
  "sessionId": "session-001",
  "taskId": "task-004",
  "agent": "Claude Strategist",
  "role": "strategist",
  "event": "action.executed",
  "action": {
    "type": "mouse.click",
    "button": "left",
    "x": 710,
    "y": 420
  },
  "result": {
    "success": true
  },
  "beforeObservationRef": "artifacts/screenshots/step-0010-before.png",
  "afterObservationRef": "artifacts/screenshots/step-0010-after.png"
}
```

## 14. Verification Requirements

Desktop-Worker must verify whether actions worked.

Verification methods:

- Compare before/after screenshots.
- Check active window state.
- Check visible text through OCR.
- Check UI Automation element state.
- Check CLI exit code.
- Check filesystem result.
- Ask the AI to inspect the new observation.

Each task step should include an expected result when possible.

Example:

```json
{
  "step": "Click Submit",
  "action": { "type": "mouse.click", "x": 710, "y": 420 },
  "expectedResult": {
    "visibleTextContains": "Request submitted"
  }
}
```

## 15. Error Handling and Recovery Requirements

The system must be able to recover from common automation failures.

Required behavior:

- Detect when an expected UI state did not appear.
- Retry safe actions a limited number of times.
- Re-observe after failure.
- Ask the AI for a revised plan.
- Ask the user for help when blocked.
- Stop safely after repeated failures.
- Preserve logs and screenshots for debugging.

Common failure cases:

- Click missed the target.
- Page did not load.
- Modal appeared.
- File picker opened unexpectedly.
- Permission prompt appeared.
- CLI command failed.
- Window focus changed.
- OCR result was incomplete.
- UI element moved.

## 16. User Interface Requirements

The UI should make the system inspectable and controllable.

Required UI features:

- Task input.
- Current status.
- Current screenshot preview.
- Cursor position display.
- Planned next action display.
- Approve/deny prompt for risky actions.
- Pause button.
- Emergency stop button.
- Action timeline.
- Audit log viewer.
- CLI output viewer.
- Settings for permission profiles.

The UI should not hide what the AI is doing. Users must be able to understand and interrupt execution.

## 17. Data and Artifact Requirements

Desktop-Worker must preserve useful artifacts.

Artifacts:

- Screenshots.
- OCR outputs.
- UI element detection outputs.
- Action logs.
- CLI stdout/stderr.
- Final task reports.
- Error reports.

Artifacts must be organized by session and task.

Example:

```text
artifacts/
  sessions/
    session-001/
      task-001/
        screenshots/
        observations/
        cli/
        audit.jsonl
        report.md
```

## 18. Secrets and Privacy Requirements

The system may encounter sensitive information on screen or in files. It must handle this carefully.

Requirements:

- Do not store secrets in plain text unless explicitly allowed.
- Redact known secret patterns in logs where possible.
- Avoid sending unnecessary private data to remote AI providers.
- Allow the user to configure sensitive applications or regions.
- Require approval before uploading local files to remote services.
- Require approval before submitting forms that may contain private data.

## 19. Roadmap

### Phase 1: Local Control Foundation

Goal: prove that Desktop-Worker can observe and control the local desktop.

Deliverables:

- Screenshot capture.
- Cursor position reading.
- Mouse move/click/double-click/right-click.
- Keyboard typing and hotkeys.
- Clipboard set/get.
- Active window detection.
- Basic action schema.
- Basic audit log.
- Emergency stop.

Acceptance criteria:

- The system can take a screenshot and save it as an artifact.
- The system can move the mouse, click, type text, and use hotkeys.
- Every action is written to the audit log.
- The user can stop execution immediately.

### Phase 2: Structured Action Loop

Goal: establish the observe-plan-act-verify loop.

Deliverables:

- Structured observation object.
- Structured action executor.
- Before/after observation capture.
- Step verification interface.
- Retry limits.
- Final task report.

Acceptance criteria:

- A simple task can run as a sequence of structured actions.
- Each action has a result record.
- Failed verification causes retry, re-plan, or safe stop.

### Phase 3: Elevated CLI Broker

Goal: implement safe elevated command execution.

Deliverables:

- Elevated/admin-capable CLI broker.
- Command preview.
- cwd handling.
- stdout/stderr capture.
- exit code capture.
- timeouts.
- risk classifier.
- approval prompts for high-risk commands.
- audit integration.

Acceptance criteria:

- CLI commands run only through the broker.
- CLI results are fully captured.
- High-risk commands require approval.
- Elevated execution is logged.

### Phase 4: Perception Layer

Goal: help the AI understand the screen beyond raw screenshots.

Deliverables:

- OCR integration.
- UI Automation integration.
- Element detection output.
- Element bounds.
- Source attribution: uia, ocr, vision, heuristic.
- Confidence scores.

Acceptance criteria:

- The system can identify visible text and common controls.
- The AI receives structured observation data plus screenshot references.
- UI Automation is preferred when available.

### Phase 5: Browser and Desktop Workflows

Goal: perform real user workflows in Chrome and common Windows UI.

Deliverables:

- Chrome navigation workflow.
- Form filling workflow.
- File upload workflow.
- Download handling.
- File picker handling.
- Window switching.
- Drag and drop workflow.

Acceptance criteria:

- The system can complete a browser form workflow.
- The system can upload a file through a native file picker.
- The system can download and locate a file.

### Phase 6: Multi-Agent Orchestration

Goal: formalize strategist, implementer, and auditor workflows.

Deliverables:

- Roadmap state file.
- Task handoff schema.
- Implementer spawn protocol.
- Claude Strategist workflow.
- Codex Auditor workflow.
- Northstar Auditor workflow.
- Auditor feedback integration.

Acceptance criteria:

- Strategist can create scoped implementation tasks.
- Implementers can execute tasks and return reports.
- Auditors can review work and produce actionable findings.
- Roadmap updates reflect completed and blocked work.

### Phase 7: Production Hardening

Goal: make Desktop-Worker reliable enough for extended real use.

Deliverables:

- Permission profiles.
- Session replay.
- Better recovery flows.
- Artifact retention settings.
- Privacy controls.
- More robust UI.
- Integration tests.
- Long-running task supervision.

Acceptance criteria:

- The system can run multi-step tasks with clear supervision.
- Users can inspect, pause, approve, deny, and stop.
- Logs and artifacts are sufficient to debug failures.

## 20. MVP Definition

The MVP is complete when Desktop-Worker can:

1. Accept a user task.
2. Capture a screenshot.
3. Read cursor position.
4. Produce a structured observation.
5. Execute structured mouse and keyboard actions.
6. Run CLI commands through the broker.
7. Log every action.
8. Verify action outcomes.
9. Ask for approval on risky actions.
10. Stop immediately on user request.
11. Produce a final task report.

MVP example scenario:

> Open Chrome, navigate to a test web page, fill a form, submit it, verify the success message, and save a report.

## 21. Implementation Rules for Claude

Claude must follow these rules while building the project:

- Start with the simplest reliable local Windows implementation.
- Keep modules small and testable.
- Prefer structured APIs over ad hoc string parsing.
- Prefer Windows UI Automation over image-only automation when available.
- Use screenshot/OCR/vision as fallback, not the only strategy.
- Implement safety and audit logging early.
- Do not add broad abstractions before the action loop works.
- Do not bypass the elevated CLI broker.
- Do not execute destructive actions silently.
- Make every important operation observable in logs.
- Define acceptance criteria before assigning implementer work.
- Run tests or provide a clear reason when tests cannot be run.

## 22. Definition of AI-Control-Ready

Desktop-Worker is AI-control-ready when:

- The AI can observe the screen.
- The AI can understand enough of the UI state to choose actions.
- The AI can move the mouse, click, type, use shortcuts, and drag.
- The AI can use CLI through the elevated broker.
- The AI can verify whether actions worked.
- The AI can recover from common failures.
- The user can pause, stop, approve, and inspect actions.
- Auditors can review decisions and implementation quality.
- Logs and artifacts explain what happened after the fact.

The project must not be considered complete if it only sends clicks without verification, logging, safety controls, or user override.
