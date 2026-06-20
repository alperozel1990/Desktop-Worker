"""Desktop-Worker — AI-control-ready Windows desktop automation.

Core loop: observe -> understand -> plan -> act -> verify -> log -> continue.

Package layout (see docs/requirements.md section 5 for the architectural layers):

    schema/       structured actions, observations, results (no side effects)
    safety/       emergency stop + permission/risk policy + limits
    audit/        machine + human readable JSONL audit log with redaction
    broker/       elevated/admin-capable CLI broker (the ONLY CLI path)
    observation/  desktop observation layer (screenshot, cursor, windows)
    actions/      action executor + input backends (mouse / keyboard / clipboard)
    loop/         the observe-plan-act-verify task loop skeleton

The CORE has no third-party dependencies. Real desktop control lives in the
Windows backends, which import heavy libraries lazily; tests use Null backends.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
