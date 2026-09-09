"""Gradio dashboard: chat with the geospatial agent, see results on a live map.

Reuses the same `agent/`/`tools/` core as `cli.py`, `api.py`, and `dashboard.py`
(the Streamlit version) — a fourth thin front end. Gradio has no native
Leaflet/folium component, so the map is embedded as raw HTML via `gr.HTML`.

Run with: python -m geoagent.gradio_app
"""

from __future__ import annotations

import folium
import gradio as gr

from geoagent.agent.conversation import Conversation
from geoagent.agent.loop import run_turn
from geoagent.agent.prompts import SYSTEM_PROMPT
from geoagent.config import configure_osmnx, load_settings
from geoagent.geospatial.mapping import configure_maps_dir
from geoagent.tools.geo_context import collect_geo_features

import geoagent.tools.routing  # noqa: F401  (import for tool-registration side effects)
import geoagent.tools.wa_mining  # noqa: F401

settings = load_settings()
configure_osmnx(
    settings.cache_dir,
    overpass_url=settings.overpass_url,
    overpass_rate_limit=settings.overpass_rate_limit,
)
configure_maps_dir(settings.maps_dir)

from openai import OpenAI  # noqa: E402

client = OpenAI(api_key=settings.openai_api_key)


def _style(feature: dict) -> dict:
    kind = feature["properties"].get("kind")
    if kind == "route":
        return {"color": "#1a73e8", "weight": 5}
    if kind == "isochrone":
        return {"color": "#e8710a", "fillOpacity": 0.25}
    return {"color": "#d93025"}


def _map_html(features: list[dict]) -> str:
    m = folium.Map(location=[10, 20], zoom_start=2, tiles="OpenStreetMap")
    if features:
        layer = folium.GeoJson(
            {"type": "FeatureCollection", "features": features},
            style_function=_style,
            marker=folium.CircleMarker(radius=6, fill=True, color="#d93025"),
            tooltip=folium.GeoJsonTooltip(fields=["kind"], aliases=["Type"]),
        )
        layer.add_to(m)
        bounds = layer.get_bounds()
        if bounds and bounds[0][0] is not None:
            m.fit_bounds(bounds)
    return m._repr_html_()


def respond(message: str, chat_history: list, conversation: Conversation | None):
    if conversation is None:
        conversation = Conversation.start(SYSTEM_PROMPT)
    checkpoint = len(conversation.messages)
    conversation.add_user(message)

    features: list[dict] = []
    try:
        with collect_geo_features() as features:
            run_turn(client, settings.openai_model, conversation, settings.max_agent_turns)
    except Exception as exc:
        # Roll back to before this turn so a failed/interrupted request can't leave
        # a half-appended tool call in history — that would make every subsequent
        # turn fail the same way, since OpenAI rejects a message list with an
        # unanswered tool_call.
        conversation.messages = conversation.messages[:checkpoint]
        display_history = [
            {"role": m["role"], "content": m["content"]}
            for m in conversation.messages
            if m.get("role") in ("user", "assistant") and m.get("content")
        ]
        display_history.append({"role": "assistant", "content": f"Something went wrong: {exc}"})
        return "", display_history, conversation, _map_html([])

    display_history = [
        {"role": m["role"], "content": m["content"]}
        for m in conversation.messages
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    return "", display_history, conversation, _map_html(features)


def _clear():
    return [], None, _map_html([])


with gr.Blocks(title="geoagent") as demo:
    gr.Markdown("# geoagent")
    conversation_state = gr.State(None)
    with gr.Row():
        with gr.Column(scale=2):
            map_html = gr.HTML(_map_html([]))
        with gr.Column(scale=1):
            chatbot = gr.Chatbot(height=550, label="Chat")
            msg = gr.Textbox(
                placeholder="Ask about routing, isochrones, or WA mining data...",
                show_label=False,
            )
            clear = gr.Button("Clear conversation")

    msg.submit(respond, [msg, chatbot, conversation_state], [msg, chatbot, conversation_state, map_html])
    clear.click(_clear, None, [chatbot, conversation_state, map_html])


def main() -> None:
    demo.launch()


if __name__ == "__main__":
    main()
