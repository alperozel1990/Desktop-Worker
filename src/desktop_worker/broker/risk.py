"""CLI command risk classifier (requirements section 11).

Conservative, deny-toward-caution classification. When in doubt the command is
escalated to a higher risk band rather than a lower one. This is a heuristic
first line of defense — the broker still requires approval for HIGH commands.

Risk bands:
  low    : read-only commands, version checks, test commands.
  medium : package installs, project-local file writes, starting local services.
  high   : deletion, registry/service/firewall/startup changes, credential
           access, system-directory changes, permission changes, killing
           processes, disk formatting, shutdown.
"""

from __future__ import annotations

import re

from desktop_worker.safety.policy import RiskLevel

# High-risk signatures. Substring/regex match against the lowercased command.
_HIGH_PATTERNS: tuple[re.Pattern[str], ...] = tuple(re.compile(p) for p in (
    r"\bdel\b", r"\berase\b", r"\brd\b", r"\brmdir\b", r"\brm\b",
    r"remove-item", r"\bformat\b",
    r"\breg\b\s+(add|delete|import)", r"regedit",
    r"\bsc\b\s+(delete|stop|config|create)", r"set-service", r"stop-service",
    r"new-service", r"sc\.exe",
    r"netsh\s+(advfirewall|firewall)", r"set-netfirewall",
    r"\bschtasks\b", r"register-scheduledtask",
    r"\bicacls\b", r"\btakeown\b", r"\bcacls\b",
    r"\btaskkill\b", r"stop-process", r"\bkill\b",
    r"\bshutdown\b", r"restart-computer", r"stop-computer",
    r"\bdiskpart\b", r"\bcipher\b\s+/w",
    r"\bnet\b\s+user", r"\bnet\b\s+localgroup",
    r"\bbcdedit\b", r"\bvssadmin\b",
    r"set-executionpolicy", r"\bcmdkey\b",
    r"c:\\windows", r"%systemroot%", r"%windir%",
))

# Medium-risk signatures.
_MEDIUM_PATTERNS: tuple[re.Pattern[str], ...] = tuple(re.compile(p) for p in (
    r"\b(npm|pnpm|yarn)\b\s+(install|i|add|ci)", r"\bpip\b\s+install",
    r"\bchoco\b\s+install", r"\bwinget\b\s+install", r"\bdotnet\b\s+add",
    r"\bgit\b\s+(push|clean|reset)",
    r"\b(mkdir|new-item|copy|move|rename)\b",
    # Short ambiguous aliases must appear in command position, not as a file
    # extension (e.g. "type readme.md" must NOT match the mkdir alias "md").
    r"(?:^|[\s&|(;])(md|cp|mv|ren)\b",
    r"\bset-content\b", r"\bout-file\b", r"\badd-content\b", r">",
    r"\b(start|net\s+start|start-service)\b",
    r"\bcurl\b", r"\bwget\b", r"invoke-webrequest", r"invoke-restmethod",
))


def classify_command(command: str) -> RiskLevel:
    """Classify a raw command string into a :class:`RiskLevel`."""
    if not command or not command.strip():
        return RiskLevel.LOW
    text = command.lower()

    for pat in _HIGH_PATTERNS:
        if pat.search(text):
            return RiskLevel.HIGH
    for pat in _MEDIUM_PATTERNS:
        if pat.search(text):
            return RiskLevel.MEDIUM
    return RiskLevel.LOW
