# geoagent

A CLI geospatial AI agent that answers natural-language street-routing questions by
having an LLM call out to OSMnx/GeoPandas-backed tools via OpenAI's native tool
(function) calling — no agent framework involved.

Given a place name or coordinates, it can:

- fetch/summarize a street network graph (`get_street_network`)
- compute shortest-path routes by distance or travel time (`shortest_route`)
- compute reachable-area isochrones (`isochrone`)

## Requirements

- Python 3.10+
- An OpenAI API key with available credits

## Setup

```bash
python3.10 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Edit `.env` and set `OPENAI_API_KEY` to your real key.

## Running

```bash
geoagent
# or: python -m geoagent.cli
```

Type a question at the `you>` prompt, e.g.:

```
you> what's the shortest driving route from Times Square, New York to Central Park, New York?
you> how far can I walk from Times Square, New York in 15 minutes?
```

Flags:

- `--debug` — echo tool calls/results to stderr as they happen
- `--no-cache` — disable OSMnx's disk cache for this run (forces fresh OSM fetches)

Type `exit`, `quit`, or Ctrl-D to leave the REPL.

## Configuration

All settings are read from environment variables (via `.env`):

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | *(required)* | OpenAI API key |
| `GEOAGENT_MODEL` | `gpt-4o-mini` | OpenAI model to use |
| `GEOAGENT_CACHE_DIR` | `.cache/osmnx` | OSMnx disk cache directory |
| `GEOAGENT_MAX_TURNS` | `8` | Safety cap on tool-call loop iterations per user message |
| `GEOAGENT_OVERPASS_URL` | *(unset, use OSMnx default)* | Override the Overpass API mirror |
| `GEOAGENT_OVERPASS_RATE_LIMIT` | `true` | Set `false` to disable OSMnx's Overpass rate-limit slot check |

The last two are only needed if your network can't reach OSMnx's default Overpass
mirror (`overpass-api.de`) — leave them unset to get OSMnx's normal, usage-policy-
respecting behavior. If routing/isochrone tool calls fail with connection errors,
try setting `GEOAGENT_OVERPASS_URL=https://overpass.kumi.systems/api` and
`GEOAGENT_OVERPASS_RATE_LIMIT=false`.

## Testing

```bash
pytest              # unit tests only (fast, no network calls)
pytest -m integration  # also hits real OSM/Overpass data
```

## Project layout

```
src/geoagent/
├── config.py       # env/settings loading, OSMnx cache configuration
├── cli.py          # REPL entrypoint
├── agent/          # OpenAI tool-calling loop, conversation state, system prompt
├── tools/          # OpenAI tool schemas + dispatch registry (extension point)
└── geospatial/      # OSMnx/GeoPandas domain logic (routing, isochrones, geocoding)
```

`geospatial/` has no knowledge of OpenAI; `tools/` adapts domain calls into OpenAI
tool schemas and model-readable text; `agent/` only talks to the tool registry's
generic interface. To add a new capability (e.g. POI search), add a
`geospatial/<feature>.py` module and a `tools/<feature>.py` that registers its own
tool specs — no changes needed to `agent/`.
