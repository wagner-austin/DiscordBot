from __future__ import annotations

import logging
import sys
from types import ModuleType

import pytest
import src.clubbot.logging as log_mod


def test_setup_logging_with_rich(monkeypatch: pytest.MonkeyPatch) -> None:
    # Build fake rich.logging and rich.traceback modules
    rich_mod = ModuleType("rich")
    rich_logging = ModuleType("rich.logging")
    rich_traceback = ModuleType("rich.traceback")

    class _RichHandler(logging.Handler):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__()

        def emit(self, record: logging.LogRecord) -> None:
            # Swallow output in tests
            return None

    def _install(**_: object) -> None:
        return None

    rich_logging.RichHandler = _RichHandler
    rich_traceback.install = _install

    monkeypatch.setitem(sys.modules, "rich", rich_mod)
    monkeypatch.setitem(sys.modules, "rich.logging", rich_logging)
    monkeypatch.setitem(sys.modules, "rich.traceback", rich_traceback)

    log_mod.setup_logging("INFO")
    root = logging.getLogger()
    assert root.handlers, "Expected a handler to be attached"
    # Ensure filters are attached on the first handler
    h = root.handlers[0]
    msgs = {type(f).__name__ for f in getattr(h, "filters", [])}
    assert "RequestIdFilter" in msgs and "InstanceIdFilter" in msgs
    assert log_mod.get_instance_id() != "-"
