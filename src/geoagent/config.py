"""Central place for env/secret loading and OSMnx global configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_model: str
    cache_dir: Path
    maps_dir: Path
    max_agent_turns: int
    overpass_url: str | None
    overpass_rate_limit: bool


def load_settings() -> Settings:
    load_dotenv()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit(
            "OPENAI_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    return Settings(
        openai_api_key=api_key,
        openai_model=os.environ.get("GEOAGENT_MODEL", "gpt-4o-mini"),
        cache_dir=Path(os.environ.get("GEOAGENT_CACHE_DIR", Path.cwd() / ".cache" / "osmnx")),
        maps_dir=Path(os.environ.get("GEOAGENT_MAPS_DIR", Path.cwd() / "maps")),
        max_agent_turns=int(os.environ.get("GEOAGENT_MAX_TURNS", "8")),
        # Left unset by default so OSMnx's own default endpoint and rate-limit
        # behavior (which respects the public Overpass API's usage policy) apply.
        # Override only if your network can't reach the default Overpass mirror.
        overpass_url=os.environ.get("GEOAGENT_OVERPASS_URL") or None,
        overpass_rate_limit=os.environ.get("GEOAGENT_OVERPASS_RATE_LIMIT", "true").lower()
        != "false",
    )


def _pick_reachable_ip(hostname: str, port: int = 443, timeout: float = 3.0) -> str | None:
    import socket

    try:
        infos = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    except OSError:
        return None
    seen: set[str] = set()
    for info in infos:
        ip = info[4][0]
        if ip in seen:
            continue
        seen.add(ip)
        try:
            with socket.create_connection((ip, port), timeout=timeout):
                return ip
        except OSError:
            continue
    return None


def _pin_dns_to_reachable_ip(hostname: str, probe_ttl: float = 5.0) -> None:
    """OSMnx pins its DNS resolution for the Overpass host to whichever IP
    `socket.gethostbyname()` happens to return, with no fallback if that specific
    IP is unreachable — unlike a normal HTTP client (curl, requests), which tries
    every address a hostname resolves to. Worse, which of `overpass-api.de`'s
    backend IPs is reachable from a given network can flap on a timescale of
    seconds to minutes, not just hours, so a one-time pin can already be stale by
    the time OSMnx uses it. This re-probes (at most once every `probe_ttl`
    seconds) so `gethostbyname` always returns whichever IP was reachable most
    recently, rather than a single value fixed at startup.
    """
    import socket
    import time

    original_gethostbyname = socket.gethostbyname
    state: dict[str, object] = {"ip": None, "checked_at": 0.0}

    def _patched(host: str) -> str:
        if host != hostname:
            return original_gethostbyname(host)
        now = time.monotonic()
        if state["ip"] is None or now - state["checked_at"] > probe_ttl:
            fresh = _pick_reachable_ip(hostname)
            if fresh:
                state["ip"] = fresh
            state["checked_at"] = now
        return state["ip"] or original_gethostbyname(host)

    socket.gethostbyname = _patched


def configure_osmnx(
    cache_dir: Path,
    use_cache: bool = True,
    overpass_url: str | None = None,
    overpass_rate_limit: bool = True,
) -> None:
    import osmnx as ox

    cache_dir.mkdir(parents=True, exist_ok=True)
    ox.settings.use_cache = use_cache
    ox.settings.cache_folder = str(cache_dir)
    ox.settings.log_console = False
    # The real setting is `requests_timeout`, not `timeout` (OSMnx has no
    # `timeout` attribute at all — setting it silently creates an unused
    # attribute rather than erroring, so an earlier version of this line was a
    # complete no-op). requests_timeout governs every HTTP request OSMnx makes
    # — both Overpass and Nominatim geocoding — and, since OSMnx also embeds
    # it into the Overpass query string's own `[timeout:N]` directive, the
    # server-side Overpass execution budget too. Its 180s default meant a
    # single slow/hanging request, combined with a couple of retries, could
    # keep an interactive query "thinking" for the better part of 10 minutes
    # with no feedback. 30s is still generous for a legitimate fetch; a
    # request that hasn't responded by then is far more likely hung.
    ox.settings.requests_timeout = 30
    ox.settings.http_user_agent = "geoagent/0.1 (contact: atharvadal7@gmail.com)"
    if overpass_url:
        ox.settings.overpass_url = overpass_url
    else:
        _pin_dns_to_reachable_ip("overpass-api.de")
    ox.settings.overpass_rate_limit = overpass_rate_limit