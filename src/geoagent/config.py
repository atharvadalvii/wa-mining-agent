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

    When no candidate IP answers the probe (all currently unreachable), this
    falls back to plain, unverified DNS resolution rather than raising:
    OSMnx's own `_config_dns` catches a `gethostbyname` failure by re-resolving
    via a DNS-over-HTTPS detour, which doesn't check reachability either and
    just adds a slow, unhelpful extra hop. See `network._fetch_with_retry`'s
    up-front reachability check for how a totally-unreachable host is actually
    failed fast, ahead of ever reaching OSMnx's fetch machinery.
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
    # with no feedback.
    #
    # NOTE: this can't be split into a (connect_timeout, read_timeout) tuple
    # (which `requests`'s own `timeout=` accepts) to fail fast on a dead IP —
    # OSMnx double-uses this same value as the Overpass QL query's own
    # server-side `[timeout:N]` execution budget (see `_make_overpass_settings`
    # in osmnx/_overpass.py), which expects a single integer. A tuple here
    # would get stringified straight into the query text as `[timeout:(8, 30)]`,
    # a syntax error that would break every *reachable* Overpass request, not
    # just speed up the unreachable case. The connect-side fast-fail instead
    # lives in `is_overpass_reachable` below, used by
    # `network._fetch_with_retry` as an up-front check.
    ox.settings.requests_timeout = 30
    ox.settings.http_user_agent = "geoagent/0.1 (contact: atharvadal7@gmail.com)"
    if overpass_url:
        ox.settings.overpass_url = overpass_url
    else:
        _pin_dns_to_reachable_ip("overpass-api.de")
    ox.settings.overpass_rate_limit = overpass_rate_limit


def is_overpass_reachable() -> bool:
    """A fast (bounded to a couple seconds per candidate IP), independent
    TCP-reachability check for the currently configured Overpass host.

    Exists because OSMnx has no cheap way to fail fast on total
    unreachability: when its own internal `/status` check (done before every
    query, to respect the server's rate limit — see `overpass_rate_limit`)
    can't connect, it doesn't fail — it falls back to a hardcoded 60-second
    "default_pause" sleep and then attempts the real query anyway, which then
    also fails after its own full `requests_timeout`. That sequence repeats
    per retry, turning a totally-dead Overpass mirror into a multi-minute
    wait. Call this before attempting a fetch (see
    `network._fetch_with_retry`) to skip straight to a clear error instead.
    """
    import osmnx as ox

    from urllib.parse import urlparse

    hostname = urlparse(ox.settings.overpass_url).hostname or "overpass-api.de"
    return _pick_reachable_ip(hostname) is not None