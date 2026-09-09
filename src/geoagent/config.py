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
        max_agent_turns=int(os.environ.get("GEOAGENT_MAX_TURNS", "8")),
        # Left unset by default so OSMnx's own default endpoint and rate-limit
        # behavior (which respects the public Overpass API's usage policy) apply.
        # Override only if your network can't reach the default Overpass mirror.
        overpass_url=os.environ.get("GEOAGENT_OVERPASS_URL") or None,
        overpass_rate_limit=os.environ.get("GEOAGENT_OVERPASS_RATE_LIMIT", "true").lower()
        != "false",
    )


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
    ox.settings.timeout = 180
    ox.settings.http_user_agent = "geoagent/0.1 (contact: atharvadal7@gmail.com)"
    if overpass_url:
        ox.settings.overpass_url = overpass_url
    ox.settings.overpass_rate_limit = overpass_rate_limit