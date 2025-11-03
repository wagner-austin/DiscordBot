from __future__ import annotations

import sys
import types
from pathlib import Path
from types import ModuleType, SimpleNamespace


def test_main_executes_under_script_guard(monkeypatch) -> None:
    # Create stub modules to avoid side effects
    logging_stub = types.ModuleType("src.clubbot.logging")
    logging_stub.setup_logging = lambda *_args, **_kwargs: None

    orchestrator_stub = types.ModuleType("src.clubbot.orchestrator")
    orchestrator_stub.ran = False

    class _FakeOrchestrator:
        def __init__(self, container) -> None:
            self.container = container

        def run(self) -> None:
            orchestrator_stub.ran = True

    orchestrator_stub.BotOrchestrator = _FakeOrchestrator

    container_stub = types.ModuleType("src.clubbot.container")

    class _FakeContainer:
        def __init__(self) -> None:
            self.cfg = SimpleNamespace(LOG_LEVEL="INFO")

        @classmethod
        def from_env(cls):
            return cls()

    container_stub.ServiceContainer = _FakeContainer

    # Install stubs in sys.modules for the import machinery used by run_module
    saved = {}
    for name, mod in {
        "src.clubbot.logging": logging_stub,
        "src.clubbot.orchestrator": orchestrator_stub,
        "src.clubbot.container": container_stub,
    }.items():
        saved[name] = sys.modules.get(name)
        sys.modules[name] = mod

    try:
        # Execute src/clubbot/main.py as __main__ without runpy to avoid warnings
        path = Path("src/clubbot/main.py")
        code = path.read_text(encoding="utf-8")
        mod = ModuleType("__main__")
        mod.__file__ = str(path)
        mod.__package__ = "src.clubbot"  # allow relative imports like `from .container import ...`
        exec(compile(code, str(path), "exec"), mod.__dict__)
        assert orchestrator_stub.ran is True
    finally:
        for name, prev in saved.items():
            if prev is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prev
