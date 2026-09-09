"""Western Australia mining data (MINEDEX deposits + mining tenements) via DMIRS's
public ArcGIS REST service (SLIP_Public_Services/Industry_and_Mining) — read-only,
no authentication required. Confirmed live at services.slip.wa.gov.au."""

from __future__ import annotations

import re
import time

from geoagent.geospatial.geocode import resolve_point
from geoagent.geospatial.models import MiningDepositsResult, MiningTenementsResult

_BASE_URL = (
    "https://services.slip.wa.gov.au/public/rest/services/"
    "SLIP_Public_Services/Industry_and_Mining/MapServer"
)
_MINEDEX_LAYER = 0
_TENEMENTS_LAYER = 3
_MAX_FEATURES = 25


class MiningDataError(Exception):
    """Raised when the DMIRS mining data service can't be queried."""


def _safe_literal(value: str) -> str:
    """Strips everything but word characters/spaces/hyphens before building a WHERE
    clause. This ArcGIS REST API takes a raw SQL-like expression with no parameter
    binding, so this neutralizes SQL-injection-style characters (quotes, semicolons,
    comment markers) from model/user-supplied filter text."""
    return re.sub(r"[^A-Za-z0-9 \-]", "", value).strip()


def _get_json(url: str, params: dict) -> dict:
    import requests

    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                raise MiningDataError(
                    f"DMIRS mining data service error: {data['error'].get('message', data['error'])}"
                )
            return data
        except MiningDataError:
            raise
        except Exception as exc:
            last_exc = exc
            if attempt == 0:
                time.sleep(1.5)
    raise MiningDataError(
        f"Could not query the DMIRS mining data service: {last_exc}"
    ) from last_exc


def _query(
    layer: int, where: str, lat: float, lon: float, radius_km: float, out_fields: list[str]
) -> tuple[int, list[dict]]:
    url = f"{_BASE_URL}/{layer}/query"
    base_params = {
        "where": where,
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": 4326,
        "distance": radius_km * 1000,
        "units": "esriSRUnit_Meter",
        "spatialRel": "esriSpatialRelIntersects",
        "f": "json",
    }

    count_data = _get_json(url, {**base_params, "returnCountOnly": "true"})
    total = int(count_data.get("count", 0))
    if total == 0:
        return 0, []

    detail_data = _get_json(
        url,
        {
            **base_params,
            "outFields": ",".join(out_fields),
            "returnGeometry": "false",
            "resultRecordCount": _MAX_FEATURES,
        },
    )
    features = [f["attributes"] for f in detail_data.get("features", [])]
    return total, features


def find_mining_deposits(
    location: str,
    radius_km: float = 50.0,
    commodity: str | None = None,
    site_type: str | None = None,
) -> MiningDepositsResult:
    lat, lon, label = resolve_point(location)

    clauses = ["1=1"]
    if commodity:
        clauses.append(f"UPPER(commodity) LIKE '%{_safe_literal(commodity).upper()}%'")
    if site_type:
        clauses.append(f"UPPER(site_type_) = '{_safe_literal(site_type).upper()}'")
    where = " AND ".join(clauses)

    total, sites = _query(
        _MINEDEX_LAYER,
        where,
        lat,
        lon,
        radius_km,
        ["site_title", "commodity", "site_type_", "site_stage", "latitude", "longitude"],
    )
    return MiningDepositsResult(
        location_label=label,
        radius_km=radius_km,
        commodity_filter=commodity,
        site_type_filter=site_type,
        total_count=total,
        sites=sites,
    )


def find_mining_tenements(
    location: str,
    radius_km: float = 50.0,
    tenement_type: str | None = None,
    status: str | None = None,
) -> MiningTenementsResult:
    lat, lon, label = resolve_point(location)

    clauses = ["1=1"]
    if tenement_type:
        clauses.append(f"UPPER(type) LIKE '%{_safe_literal(tenement_type).upper()}%'")
    if status:
        clauses.append(f"UPPER(tenstatus) = '{_safe_literal(status).upper()}'")
    where = " AND ".join(clauses)

    total, tenements = _query(
        _TENEMENTS_LAYER,
        where,
        lat,
        lon,
        radius_km,
        ["tenid", "type", "tenstatus", "holder1", "legal_area", "unit_of_me"],
    )
    return MiningTenementsResult(
        location_label=label,
        radius_km=radius_km,
        type_filter=tenement_type,
        status_filter=status,
        total_count=total,
        tenements=tenements,
    )
