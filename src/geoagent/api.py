"""FastAPI microservice wrapping the geospatial agent.

Stateless by design: each request carries its own conversation `history` (if
continuing a prior exchange) instead of the server keeping session state, so
there's nothing to persist or clean up. Alongside the model's plain-text
reply, the response includes a `geojson` FeatureCollection built from
whatever routes/isochrones/mining sites were actually computed during that
turn's tool calls (see `geoagent.tools.geo_context`) — mining tenement
polygons aren't included since the tenement tool doesn't currently fetch
geometry (see `find_mining_tenements`).

Run with: uvicorn geoagent.api:app --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import Depends, FastAPI
from pydantic import BaseModel, Field

from geoagent.agent.conversation import Conversation
from geoagent.agent.loop import run_turn
from geoagent.agent.prompts import SYSTEM_PROMPT
from geoagent.config import Settings, configure_osmnx, load_settings
from geoagent.geospatial.mapping import configure_maps_dir
from geoagent.tools.geo_context import collect_geo_features

import geoagent.tools.routing  # noqa: F401  (import for tool-registration side effects)
import geoagent.tools.wa_mining  # noqa: F401


@lru_cache
def get_settings() -> Settings:
    return load_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_osmnx(
        settings.cache_dir,
        overpass_url=settings.overpass_url,
        overpass_rate_limit=settings.overpass_rate_limit,
    )
    configure_maps_dir(settings.maps_dir)
    yield


app = FastAPI(title="geoagent API", lifespan=lifespan)


def get_openai_client(settings: Settings = Depends(get_settings)):
    from openai import OpenAI

    return OpenAI(api_key=settings.openai_api_key)


class QueryRequest(BaseModel):
    message: str
    history: list[dict] = Field(
        default_factory=list,
        description="Prior non-system messages from a previous response's `history`, to continue a conversation.",
    )


class QueryResponse(BaseModel):
    reply: str
    history: list[dict]
    geojson: dict


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
def query(
    body: QueryRequest,
    client=Depends(get_openai_client),
    settings: Settings = Depends(get_settings),
) -> QueryResponse:
    conversation = Conversation.start(SYSTEM_PROMPT)
    conversation.messages.extend(body.history)
    conversation.add_user(body.message)

    with collect_geo_features() as features:
        reply = run_turn(client, settings.openai_model, conversation, settings.max_agent_turns)

    history = [m for m in conversation.messages if m.get("role") != "system"]
    return QueryResponse(
        reply=reply,
        history=history,
        geojson={"type": "FeatureCollection", "features": features},
    )
