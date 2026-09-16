"""REPL entrypoint for the geospatial AI agent."""

from __future__ import annotations

import argparse

from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel

from geoagent.agent.conversation import Conversation
from geoagent.agent.loop import run_turn
from geoagent.agent.prompts import SYSTEM_PROMPT
from geoagent.config import configure_osmnx, load_settings
from geoagent.geospatial import local_extract
from geoagent.geospatial.mapping import configure_maps_dir

import geoagent.tools.routing  # noqa: F401  (import for tool-registration side effects)
import geoagent.tools.wa_mining  # noqa: F401


def _make_debug_callbacks(console: Console):
    def on_tool_call(name: str, args: dict) -> None:
        console.print(f"[dim]-> calling[/dim] [bold cyan]{escape(name)}[/bold cyan]({escape(str(args))})")

    def on_tool_result(name: str, result: str) -> None:
        console.print(f"[dim]<- {escape(name)} returned:[/dim] {escape(result)}")

    return on_tool_call, on_tool_result


def main() -> None:
    parser = argparse.ArgumentParser(prog="geoagent")
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable OSMnx's disk cache for this run (forces fresh OSM fetches).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show tool calls and results as they happen.",
    )
    args = parser.parse_args()

    console = Console()

    settings = load_settings()
    configure_osmnx(
        settings.cache_dir,
        use_cache=not args.no_cache,
        overpass_url=settings.overpass_url,
        overpass_rate_limit=settings.overpass_rate_limit,
    )
    configure_maps_dir(settings.maps_dir)
    with console.status("[bold green]Loading local WA street data...[/bold green]", spinner="dots"):
        local_extract.warm_up()

    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    conversation = Conversation.start(SYSTEM_PROMPT)

    on_tool_call = on_tool_result = None
    if args.debug:
        on_tool_call, on_tool_result = _make_debug_callbacks(console)

    console.print(
        Panel(
            "Ask about street routing/isochrones. Type 'exit' or Ctrl-D to quit.",
            title="geoagent",
            border_style="cyan",
        )
    )

    while True:
        try:
            line = console.input("[bold cyan]you>[/bold cyan] ")
        except EOFError:
            console.print()
            break
        if line.strip().lower() in {"exit", "quit"}:
            break
        if not line.strip():
            continue

        conversation.add_user(line)
        try:
            with console.status("[bold green]Thinking...[/bold green]", spinner="dots"):
                reply = run_turn(
                    client,
                    settings.openai_model,
                    conversation,
                    settings.max_agent_turns,
                    on_tool_call=on_tool_call,
                    on_tool_result=on_tool_result,
                )
        except Exception as exc:
            console.print(f"[bold red]Something went wrong:[/bold red] {escape(str(exc))}")
            continue
        console.print(Panel(Markdown(reply), title="agent", border_style="green"))


if __name__ == "__main__":
    main()
