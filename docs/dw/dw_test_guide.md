# Desktop-Worker — How to run the working demo

You asked for a real, working app: the agent creates a text file on your desktop,
types "başlıyoruz" inside, and saves it — while you just watch. **That is one
command.** This is the test that matters.

## ⭐ The main demo (MANUAL-8)

1. Open **PowerShell** and go to the project:
   ```powershell
   cd C:\Desktop-Worker
   ```
2. (First time only) make sure the desktop libraries are installed:
   ```powershell
   python -m pip install -e ".[windows]"
   ```
3. Run the demo and **watch your screen**:
   ```powershell
   python -m desktop_worker create-file
   ```

**What it does (you watch all of it):**
- Shows the desktop (minimises open windows).
- Moves the mouse to an empty spot and **right-clicks**.
- Goes **New → Text Document** in the menu.
- Names the file **dw-demo** and confirms.
- **Double-clicks** the new file to open it (Notepad).
- Types **başlıyoruz** inside.
- Presses **Ctrl+S** to save.

**What you should see at the end:** a report ending with
`11. ok: verified content on disk` and `# Create desktop file - OK`, and a file
**dw-demo.txt** on your desktop containing **başlıyoruz**.

**Stop button:** at any moment, in another PowerShell window:
```powershell
python -m desktop_worker estop
```
The agent halts before its next action. (Clear it later with `clear-stop`.)

**Options:**
```powershell
python -m desktop_worker create-file --text "merhaba dünya" --name notlar
```

### If it doesn't end with "OK"
- The command **verifies the file on disk** and only says OK if the content is
  really there — it won't lie. If it prints a FAILED step, copy the whole report
  back to Claude. Common cause: a different keyboard/menu language — Claude will
  adjust the menu names.
- If you already have a Notepad open with **unsaved** tabs, close them first (the
  modern Notepad's tab-restore can interfere). Saved tabs are fine.

---

## Optional: the AI planner demo (Claude decides the steps, no API key)

This uses your existing `claude` login (no API billing) to let Claude choose the
next action. Keep Notepad focused, then:
```powershell
claude auth status   # should say "loggedIn": true
python -c "from desktop_worker.app import Session; from desktop_worker.config import Config, Limits; from desktop_worker.safety.policy import PermissionPolicy, auto_approve; from desktop_worker.loop.claude_cli_planner import ClaudeCliPlanner; from desktop_worker.loop.task_loop import TaskLoop; s=Session(Config(session_id='ai',task_id='t'), policy=PermissionPolicy(approval_callback=auto_approve)); p=ClaudeCliPlanner(task='Type the word hello into the focused window then stop', broker=s.broker, cwd=r'C:\Desktop-Worker', audit=s.audit); print(TaskLoop(task_id='t', planner=p, observer=s.observer, executor=s.executor, audit=s.audit, estop=s.estop, limits=Limits(max_actions_per_task=5)).run().to_markdown())"
```

---

## Optional: automated tests (no clicking, safe)

```powershell
python -m pytest
```
Expect the last line `130 passed`. (These no longer pop UAC prompts.)

---

## What to send back to Claude
After the main demo: tell Claude whether **dw-demo.txt** appeared on your desktop
with **başlıyoruz** inside, or paste the report if a step said FAILED.
