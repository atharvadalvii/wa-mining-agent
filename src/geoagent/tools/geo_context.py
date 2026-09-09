"""Context-local collector for structured GeoJSON features produced by tool
handlers during a single agent turn.

Tool handlers call `record_geo_feature()` unconditionally after computing a
result. It's a no-op unless something is actively collecting (via
`collect_geo_features()`), so the CLI's behavior is unaffected — this exists
so the FastAPI layer can return real geometry (route lines, isochrone
polygons, ...) alongside the model's text reply, without threading a
collector object through every tool/domain function signature.

A contextvar (not a plain module global) is used so concurrent async
requests in the FastAPI server each get their own isolated collector.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

_collector: ContextVar[list[dict[str, Any]] | None] = ContextVar("geo_collector", default=None)


def record_geo_feature(feature: dict[str, Any]) -> None:
    features = _collector.get()
    if features is not None:
        features.append(feature)


@contextmanager
def collect_geo_features() -> Iterator[list[dict[str, Any]]]:
    features: list[dict[str, Any]] = []
    token = _collector.set(features)
    try:
        yield features
    finally:
        _collector.reset(token)
