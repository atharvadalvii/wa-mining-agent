"""WA mining data tool wrappers: MINEDEX deposits + mining tenements (DMIRS)."""

from __future__ import annotations

from geoagent.geospatial.wa_mining import find_mining_deposits, find_mining_tenements
from geoagent.tools.registry import ToolSpec, register


def handle_find_mining_deposits(
    location: str,
    radius_km: float = 50,
    commodity: str | None = None,
    site_type: str | None = None,
) -> str:
    result = find_mining_deposits(
        location=location, radius_km=radius_km, commodity=commodity, site_type=site_type
    )
    return result.to_tool_text()


def handle_find_mining_tenements(
    location: str,
    radius_km: float = 50,
    tenement_type: str | None = None,
    status: str | None = None,
) -> str:
    result = find_mining_tenements(
        location=location, radius_km=radius_km, tenement_type=tenement_type, status=status
    )
    return result.to_tool_text()


register(
    ToolSpec(
        name="find_mining_deposits",
        description=(
            "Find Western Australian mines, mineral deposits, prospects, and related "
            "sites (from DMIRS's MINEDEX dataset) within a radius of a place or "
            "'lat,lon' point. Optionally filter by commodity (e.g. 'iron', 'gold', "
            "'lithium', 'nickel') and/or site type."
        ),
        parameters={
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "Place name OR 'lat,lon' string, e.g. 'Port Hedland, WA'.",
                },
                "radius_km": {
                    "type": "number",
                    "description": "Search radius in kilometers. Default 50.",
                    "default": 50,
                },
                "commodity": {
                    "type": "string",
                    "description": (
                        "Optional commodity substring to filter by, e.g. 'iron', "
                        "'gold', 'lithium', 'nickel', 'base metal', 'precious metal'."
                    ),
                },
                "site_type": {
                    "type": "string",
                    "enum": [
                        "Mine",
                        "Deposit",
                        "Prospect",
                        "Occurrence",
                        "Target",
                        "Infrastructure",
                        "Geological Observation",
                        "Other",
                    ],
                    "description": "Optional exact site type to filter by.",
                },
            },
            "required": ["location"],
        },
        handler=handle_find_mining_deposits,
    )
)

register(
    ToolSpec(
        name="find_mining_tenements",
        description=(
            "Find Western Australian mining tenements (legal mining/exploration titles "
            "from DMIRS's TENGRAPH system) within a radius of a place or 'lat,lon' "
            "point. Optionally filter by tenement type and/or status. Only live and "
            "pending tenements are covered (not historical/dead ones). Tenements have "
            "NO commodity/mineral data attached — 'tenement_type' is a legal title "
            "category only (e.g. mining lease), never a mineral like 'iron' or 'gold'. "
            "To find sites by commodity, use find_mining_deposits instead."
        ),
        parameters={
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "Place name OR 'lat,lon' string, e.g. 'Port Hedland, WA'.",
                },
                "radius_km": {
                    "type": "number",
                    "description": "Search radius in kilometers. Default 50.",
                    "default": 50,
                },
                "tenement_type": {
                    "type": "string",
                    "description": (
                        "Optional LEGAL title type substring to filter by, e.g. "
                        "'mining lease', 'exploration licence', 'prospecting licence'. "
                        "Never a commodity/mineral name — tenements carry no commodity data."
                    ),
                },
                "status": {
                    "type": "string",
                    "enum": ["LIVE", "PENDING"],
                    "description": "Optional tenement status to filter by.",
                },
            },
            "required": ["location"],
        },
        handler=handle_find_mining_tenements,
    )
)
