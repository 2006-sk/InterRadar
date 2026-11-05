"""Helpers shared by the source adapters."""

from __future__ import annotations

from ..http import FetchError, FetchResult


def expect_ok(result: FetchResult, kind: type | tuple = (dict, list)) -> object:
    """Raise if the destination didn't answer 200 with the shape we expect."""
    if result.status_code != 200:
        raise FetchError(f"{result.url} returned HTTP {result.status_code}", status=result.status_code)
    if not isinstance(result.data, kind):
        raise FetchError(f"{result.url}: unexpected response type {type(result.data).__name__}")
    return result.data
