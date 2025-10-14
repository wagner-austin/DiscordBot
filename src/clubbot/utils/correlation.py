from __future__ import annotations


def add_correlation_header(
    headers: dict[str, str] | None,
    request_id: str,
    *,
    header_name: str = "X-Request-ID",
) -> dict[str, str]:
    """Return a copy of headers including a correlation header.

    This stays client-agnostic; use it with `requests`, `aiohttp`, httpx, etc.
    Example:
        h = add_correlation_header({"Accept": "application/json"}, req_id)
        await session.get(url, headers=h)
    """
    base: dict[str, str] = dict(headers or {})
    base[header_name] = request_id
    return base
