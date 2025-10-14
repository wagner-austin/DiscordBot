from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


if TYPE_CHECKING:
    # Typed stub seen only by type checkers.
    def slash_cmd(*args: Any, **kwargs: Any) -> Callable[[F], F]:  # pragma: no cover - typing stub
        def _decorator(func: F) -> F:  # pragma: no cover - typing stub
            return func

        return _decorator
else:  # pragma: no cover - thin runtime wrapper
    from discord.ext import commands as _commands

    def slash_cmd(*args: Any, **kwargs: Any):
        return _commands.slash_command(*args, **kwargs)
