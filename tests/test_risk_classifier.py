import pytest

from desktop_worker.broker.risk import classify_command
from desktop_worker.safety.policy import RiskLevel


@pytest.mark.parametrize("cmd", [
    "echo hello",
    "python --version",
    "npm test",
    "git status",
    "dir",
    "type readme.md",
])
def test_low_risk(cmd):
    assert classify_command(cmd) == RiskLevel.LOW


@pytest.mark.parametrize("cmd", [
    "npm install left-pad",
    "pip install requests",
    "mkdir newdir",
    "copy a.txt b.txt",
    "echo data > out.txt",
    "winget install Foo",
    "git push origin main",
    "curl https://example.com",
])
def test_medium_risk(cmd):
    assert classify_command(cmd) == RiskLevel.MEDIUM


@pytest.mark.parametrize("cmd", [
    "del C:\\important.txt",
    "rm -rf /",
    "Remove-Item -Recurse foo",
    "reg add HKLM\\Software\\X /v Y",
    "sc delete spooler",
    "netsh advfirewall set allprofiles state off",
    "schtasks /create /tn evil",
    "icacls C:\\ /grant everyone:F",
    "taskkill /im notepad.exe",
    "shutdown /s",
    "format C:",
    "net user attacker password /add",
    "bcdedit /set",
    "Stop-Service WinDefend",
])
def test_high_risk(cmd):
    assert classify_command(cmd) == RiskLevel.HIGH


def test_empty_is_low():
    assert classify_command("") == RiskLevel.LOW
    assert classify_command("   ") == RiskLevel.LOW
