"""Streamlit dashboard: chat with the geospatial agent in the sidebar, see the
results (route lines, isochrone polygons, mining deposit points) on a live map.

Reuses the same `agent/`/`tools/` core as `cli.py` and `api.py` — a third thin
front end, no HTTP call to `api.py` involved.

Run with: streamlit run src/geoagent/dashboard.py
"""

from __future__ import annotations

import folium
import streamlit as st
from streamlit_folium import st_folium

from geoagent.agent.conversation import Conversation
from geoagent.agent.loop import run_turn
from geoagent.agent.prompts import SYSTEM_PROMPT
from geoagent.config import configure_osmnx, load_settings
from geoagent.geospatial.mapping import configure_maps_dir
from geoagent.tools.geo_context import collect_geo_features

import geoagent.tools.routing  # noqa: F401  (import for tool-registration side effects)
import geoagent.tools.wa_mining  # noqa: F401

st.set_page_config(page_title="geoagent", layout="wide")


@st.cache_resource
def _setup():
    settings = load_settings()
    configure_osmnx(
        settings.cache_dir,
        overpass_url=settings.overpass_url,
        overpass_rate_limit=settings.overpass_rate_limit,
    )
    configure_maps_dir(settings.maps_dir)
    from openai import OpenAI

    return settings, OpenAI(api_key=settings.openai_api_key)


settings, client = _setup()

if "conversation" not in st.session_state:
    st.session_state.conversation = Conversation.start(SYSTEM_PROMPT)
if "features" not in st.session_state:
    st.session_state.features = []

st.title("geoagent")

with st.sidebar:
    st.header("Chat")
    if st.button("Clear conversation"):
        st.session_state.conversation = Conversation.start(SYSTEM_PROMPT)
        st.session_state.features = []
        st.rerun()

    for message in st.session_state.conversation.messages:
        if message.get("role") in ("user", "assistant") and message.get("content"):
            with st.chat_message(message["role"]):
                st.write(message["content"])

    prompt = st.chat_input("Ask about routing, isochrones, or WA mining data...")
    if prompt:
        checkpoint = len(st.session_state.conversation.messages)
        st.session_state.conversation.add_user(prompt)
        try:
            with st.spinner("Thinking..."):
                with collect_geo_features() as features:
                    run_turn(
                        client, settings.openai_model, st.session_state.conversation, settings.max_agent_turns
                    )
                if features:
                    st.session_state.features = features
        except Exception as exc:
            # Roll back to before this turn so a failed/interrupted request (e.g. a
            # transient API error) can't leave a half-appended tool call in history —
            # that would make every subsequent turn fail the same way, since OpenAI
            # rejects a message list with an unanswered tool_call.
            st.session_state.conversation.messages = st.session_state.conversation.messages[:checkpoint]
            st.error(f"Something went wrong: {exc}")
        else:
            st.rerun()


def _style(feature: dict) -> dict:
    kind = feature["properties"].get("kind")
    if kind == "route":
        return {"color": "#1a73e8", "weight": 5}
    if kind == "isochrone":
        return {"color": "#e8710a", "fillOpacity": 0.25}
    return {"color": "#d93025"}


m = folium.Map(location=[10, 20], zoom_start=2, tiles="OpenStreetMap")
if st.session_state.features:
    layer = folium.GeoJson(
        {"type": "FeatureCollection", "features": st.session_state.features},
        style_function=_style,
        marker=folium.CircleMarker(radius=6, fill=True, color="#d93025"),
        tooltip=folium.GeoJsonTooltip(fields=["kind"], aliases=["Type"]),
    )
    layer.add_to(m)
    bounds = layer.get_bounds()
    if bounds and bounds[0][0] is not None:
        m.fit_bounds(bounds)

st_folium(m, width=None, height=650)
