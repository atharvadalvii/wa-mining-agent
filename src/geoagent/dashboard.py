"""Streamlit dashboard: chat with the geospatial agent in the sidebar, see the
results (route lines, isochrone polygons, mining deposit points) on a live map.

Reuses the same `agent/`/`tools/` core as `cli.py` and `api.py` — a third thin
front end, no HTTP call to `api.py` involved.

Run with: streamlit run src/geoagent/dashboard.py
"""

from __future__ import annotations

import os

import folium
import streamlit as st
from streamlit_folium import st_folium

from geoagent.agent.conversation import Conversation
from geoagent.agent.loop import run_turn
from geoagent.agent.prompts import system_prompt
from geoagent.config import configure_osmnx, load_settings
from geoagent.limits import check_message
from geoagent.geospatial import local_extract
from geoagent.geospatial.mapping import configure_maps_dir
from geoagent.tools.geo_context import collect_geo_features

import geoagent.tools.wa_mining  # noqa: F401  (import for tool-registration side effects)

st.set_page_config(page_title="WA Mining Assistant", page_icon="⛏️", layout="wide")

st.markdown(
    """
    <style>
    #MainMenu, footer, [data-testid="stToolbar"] {visibility: hidden;}
    .block-container {padding-top: 2rem; padding-bottom: 1.5rem; max-width: 1200px;}
    .hero h1 {font-size: 2.6rem; font-weight: 700; margin: 0 0 .25rem; letter-spacing: -.02em;}
    .hero p.tag {font-size: 1.25rem; color: #3d4350; margin: 0 0 .5rem;}
    .hero p.sub {color: #6b7280; margin: 0 0 1.5rem; max-width: 46rem;}
    .card {border: 1px solid #e7e2da; border-radius: 12px; padding: 1rem 1.1rem;
           background: #faf8f5; height: 100%;}
    .card b {display: block; margin-bottom: .25rem;}
    .card span {color: #6b7280; font-size: .92rem;}
    h3.section {font-size: .8rem; text-transform: uppercase; letter-spacing: .08em;
                color: #8a8f98; margin: 1.75rem 0 .6rem; font-weight: 600;}
    div.stButton > button {border-radius: 10px; text-align: left; padding: .6rem .8rem;}
    [data-testid="stSidebar"] {border-right: 1px solid #e7e2da;}
    .topbar {display: flex; align-items: baseline; gap: .75rem; margin-bottom: .5rem;}
    .topbar h2 {margin: 0; font-size: 1.4rem;}
    .topbar span {color: #6b7280; font-size: .9rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


def _bridge_streamlit_secrets_to_env() -> None:
    """On Streamlit Community Cloud, secrets set in the app's dashboard only
    ever arrive via `st.secrets` — there is no .env file and they are NOT
    injected into os.environ automatically. `load_settings()` below reads
    plain env vars (so it stays usable from the CLI/API/Gradio front ends,
    which know nothing about Streamlit), so mirror any secrets across before
    calling it. A missing secrets.toml (the normal case for local dev, which
    uses .env instead) makes st.secrets behave like an empty mapping rather
    than raising.
    """
    try:
        for key, value in st.secrets.items():
            os.environ.setdefault(key, str(value))
    except Exception:
        pass


@st.cache_resource
def _setup():
    _bridge_streamlit_secrets_to_env()
    settings = load_settings()
    configure_osmnx(
        settings.cache_dir,
        overpass_url=settings.overpass_url,
        overpass_rate_limit=settings.overpass_rate_limit,
    )
    configure_maps_dir(settings.maps_dir)
    if settings.enable_routing:
        import geoagent.tools.routing  # noqa: F401  (registers the routing tools)

        local_extract.warm_up()
    from openai import OpenAI

    return settings, OpenAI(api_key=settings.openai_api_key)


settings, client = _setup()

if "conversation" not in st.session_state:
    st.session_state.conversation = Conversation.start(system_prompt(settings.enable_routing))
if "features" not in st.session_state:
    st.session_state.features = []

_EXAMPLES = [
    "Gold deposits near Kalgoorlie",
    "Pending prospecting licences near Coolgardie",
    "Iron ore mining leases near Newman",
] + (["How far can a crew drive from Leonora in an hour?"] if settings.enable_routing else [])

with st.sidebar:
    st.subheader("Chat")
    if st.button("Clear conversation", use_container_width=True):
        st.session_state.conversation = Conversation.start(system_prompt(settings.enable_routing))
        st.session_state.features = []
        st.rerun()

    for message in st.session_state.conversation.messages:
        if message.get("role") in ("user", "assistant") and message.get("content"):
            with st.chat_message(message["role"]):
                st.write(message["content"])

    prompt = st.session_state.pop("pending_prompt", None) or st.chat_input(
        "Ask about WA mines, tenements, routes, or drive-time areas..."
        if settings.enable_routing
        else "Ask about WA mines, deposits or mining tenements..."
    )
    questions_asked = sum(
        1 for m in st.session_state.conversation.messages if m.get("role") == "user"
    )
    refusal = (
        check_message(
            questions_asked, prompt, settings.max_session_messages, settings.max_input_chars
        )
        if prompt
        else None
    )
    if refusal:
        st.warning(refusal)
    elif prompt:
        checkpoint = len(st.session_state.conversation.messages)
        st.session_state.conversation.add_user(prompt)
        try:
            tools_called: list[str] = []
            with st.spinner("Thinking..."):
                with collect_geo_features() as features:
                    run_turn(
                        client,
                        settings.openai_model,
                        st.session_state.conversation,
                        settings.max_agent_turns,
                        on_tool_call=lambda name, args: tools_called.append(name),
                    )
                # The map always shows the latest query. If this turn ran any tool,
                # replace the map with its results — even an empty set (nothing found,
                # or an error), so a stale earlier result is never shown as the
                # answer. A turn with no tool calls (e.g. "thanks") leaves it alone.
                if tools_called:
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


def _landing() -> None:
    """Shown until the first question: say what this is and how to use it."""
    st.markdown(
        """
        <div class="hero">
          <h1>⛏️ WA Mining Assistant</h1>
          <p class="tag">Ask about Western Australian mining in plain English and see the answer on a map.</p>
          <p class="sub">An LLM agent that queries live government mining data, so you get real
          tenement and deposit records instead of guesses.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<h3 class="section">Try a question</h3>', unsafe_allow_html=True)
    for col, example in zip(st.columns(len(_EXAMPLES)), _EXAMPLES):
        if col.button(example, use_container_width=True):
            st.session_state.pending_prompt = example
            st.rerun()
    st.caption("Or type your own in the chat box on the left.")

    st.markdown('<h3 class="section">What it does</h3>', unsafe_allow_html=True)
    cards = [
        ("Mines and deposits", "Filter by commodity and site type. Source: MINEDEX."),
        ("Mining tenements", "Leases and licences by type and status, with boundaries on the map. Source: TENGRAPH."),
    ]
    if settings.enable_routing:
        cards.append(("Travel planning", "Driving routes, and how far a crew can get in a given time."))
    for col, (title, text) in zip(st.columns(len(cards)), cards):
        col.markdown(
            f'<div class="card"><b>{title}</b><span>{text}</span></div>', unsafe_allow_html=True
        )

    st.caption(
        "Data: Western Australia DMIRS public ArcGIS services · OpenAI tool calling, "
        "GeoPandas/OSMnx, Streamlit · [Source on GitHub](https://github.com/atharvadalvii/wa-mining-agent)"
    )


if not any(m.get("role") == "user" for m in st.session_state.conversation.messages):
    _landing()
    st.stop()

st.markdown(
    '<div class="topbar"><h2>⛏️ WA Mining Assistant</h2>'
    "<span>Answers appear on the map. Chat on the left.</span></div>",
    unsafe_allow_html=True,
)


def _style(feature: dict) -> dict:
    kind = feature["properties"].get("kind")
    if kind == "route":
        return {"color": "#1a73e8", "weight": 5}
    if kind == "isochrone":
        return {"color": "#e8710a", "fillOpacity": 0.25}
    if kind == "mining_tenement":
        return {"color": "#7b1fa2", "weight": 2, "fillOpacity": 0.2}
    return {"color": "#d93025"}


m = folium.Map(location=[-26.0, 121.0], zoom_start=5, tiles="OpenStreetMap")
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

# returned_objects=[]: the dashboard never reads the map's pan/zoom/click events, and
# by default each of them triggers a script rerun. A rerun that lands while the agent
# is mid-answer makes Streamlit abandon the turn silently (the question stays on
# screen with no reply and no error), so visitors who touch the map while waiting
# lose their answer. Returning nothing means the map can't interrupt a turn.
st_folium(m, width=None, height=620, returned_objects=[], key="map")
