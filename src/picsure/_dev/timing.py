from __future__ import annotations

import functools
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, TypeVar

from picsure._dev.events import Event

if TYPE_CHECKING:
    from picsure._dev.config import DevConfig

F = TypeVar("F", bound=Callable[..., Any])


def timed(name: str) -> Callable[[F], F]:
    """Method decorator: emits a 'function' event on success, 'error' on exception.

    Wrapped object must expose ``self._dev_config: DevConfig | None``.
    When the attribute is missing or the config is disabled, the decorator
    is a no-op.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            cfg: DevConfig | None = getattr(self, "_dev_config", None)
            if cfg is None or not cfg.enabled:
                return func(self, *args, **kwargs)

            start = time.monotonic()
            try:
                result = func(self, *args, **kwargs)
            except Exception as exc:
                duration_ms = (time.monotonic() - start) * 1000.0
                cfg.emit(
                    Event(
                        timestamp=datetime.now(timezone.utc),
                        kind="error",
                        name=name,
                        duration_ms=duration_ms,
                        bytes_in=None,
                        bytes_out=None,
                        status=None,
                        retry=0,
                        error=type(exc).__name__,
                        metadata={},
                    )
                )
                raise

            duration_ms = (time.monotonic() - start) * 1000.0
            cfg.emit(
                Event(
                    timestamp=datetime.now(timezone.utc),
                    kind="function",
                    name=name,
                    duration_ms=duration_ms,
                    bytes_in=None,
                    bytes_out=_bytes_out_for(result),
                    status=None,
                    retry=0,
                    error=None,
                    metadata=_metadata_for(result),
                )
            )
            return result

        return wrapper  # type: ignore[return-value]

    return decorator


def _bytes_out_for(result: Any) -> int | None:
    # Best-effort: DataFrames don't expose a byte count cheaply, and we do
    # not want to serialize large payloads just to measure them. Leave None.
    return None


def _metadata_for(result: Any) -> dict[str, Any]:
    try:
        import pandas as pd
    except Exception:  # pragma: no cover — pandas is a hard dep
        return {}
    if isinstance(result, pd.DataFrame):
        return {"df_rows": int(result.shape[0]), "df_cols": int(result.shape[1])}
    if isinstance(result, int):
        return {"result_type": "int"}
    return {}
