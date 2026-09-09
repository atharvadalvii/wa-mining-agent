"""REPL entrypoint for the geospatial AI agent."""

from __future__ import annotations

import argparse
import sys

from geoagent.agent.conversation import Conversation
from geoagent.agent.loop import run_turn
from geoagent.agent.prompts import SYSTEM_PROMPT
from geoagent.config import configure_osmnx, load_settings

import geoagent.tools.routing  # noqa: F401  (import for tool-registration side effects)


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
        help="Echo tool calls and results to stderr as they happen.",
    )
    args = parser.parse_args()

    settings = load_settings()
    configure_osmnx(
        settings.cache_dir,
        use_cache=not args.no_cache,
        overpass_url=settings.overpass_url,
        overpass_rate_limit=settings.overpass_rate_limit,
    )

    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    conversation = Conversation.start(SYSTEM_PROMPT)

    print("geoagent REPL — ask about street routing/isochrones. Ctrl-D or 'exit' to quit.")
    while True:
        try:
            line = input("you> ")
        except EOFError:
            print()
            break
        if line.strip().lower() in {"exit", "quit"}:
            break
        if not line.strip():
            continue

        conversation.add_user(line)
        try:
            reply = run_turn(
                client,
                settings.openai_model,
                conversation,
                settings.max_agent_turns,
                debug=args.debug,
            )
        except Exception as exc:
            print(f"agent> Something went wrong: {exc}", file=sys.stderr)
            continue
        print(f"agent> {reply}")


if __name__ == "__main__":
    main()
