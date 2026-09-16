"""Structured domain results and their lossy, model-facing text summaries."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NetworkSummary:
    place_or_point: str
    network_type: str
    n_nodes: int
    n_edges: int
    bbox: tuple[float, float, float, float]  # north, south, east, west

    def to_tool_text(self) -> str:
        north, south, east, west = self.bbox
        return (
            f"Street network ({self.network_type}) for '{self.place_or_point}': "
            f"{self.n_nodes} nodes, {self.n_edges} edges. "
            f"Bounding box: north={north:.5f}, south={south:.5f}, east={east:.5f}, west={west:.5f}."
        )


@dataclass
class RouteResult:
    origin_label: str
    destination_label: str
    network_type: str
    optimized_for: str  # "length" | "travel_time"
    length_m: float
    estimated_time_min: float | None
    coordinates: list[tuple[float, float]] = field(default_factory=list)

    @property
    def n_waypoints(self) -> int:
        return len(self.coordinates)

    def to_tool_text(self) -> str:
        time_part = (
            f", ~{self.estimated_time_min:.1f} min" if self.estimated_time_min is not None else ""
        )
        return (
            f"Route from '{self.origin_label}' to '{self.destination_label}' "
            f"({self.network_type}, optimized for {self.optimized_for}): "
            f"{self.length_m / 1000:.2f} km{time_part}, {self.n_waypoints} waypoints."
        )

    def to_geojson_feature(self) -> dict:
        return {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[lon, lat] for lat, lon in self.coordinates],
            },
            "properties": {
                "kind": "route",
                "origin": self.origin_label,
                "destination": self.destination_label,
                "network_type": self.network_type,
                "optimized_for": self.optimized_for,
                "length_m": self.length_m,
                "estimated_time_min": self.estimated_time_min,
            },
        }


@dataclass
class IsochroneResult:
    center_label: str
    minutes: float
    network_type: str
    n_reachable_nodes: int
    area_km2: float
    approx_radius_m: float
    center_point: tuple[float, float] = (0.0, 0.0)
    hull_coords: list[tuple[float, float]] = field(default_factory=list)

    def to_tool_text(self) -> str:
        return (
            f"Isochrone from '{self.center_label}' within {self.minutes:.0f} min "
            f"({self.network_type}): reaches {self.n_reachable_nodes} network nodes, "
            f"covering approximately {self.area_km2:.2f} km^2 "
            f"(approx radius {self.approx_radius_m:.0f} m)."
        )

    def to_geojson_feature(self) -> dict:
        coords = [[lon, lat] for lat, lon in self.hull_coords]
        return {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [coords]} if coords else None,
            "properties": {
                "kind": "isochrone",
                "center": self.center_label,
                "minutes": self.minutes,
                "network_type": self.network_type,
                "area_km2": self.area_km2,
                "n_reachable_nodes": self.n_reachable_nodes,
            },
        }


_MAX_LISTED = 15


@dataclass
class MiningDepositsResult:
    location_label: str
    radius_km: float
    commodity_filter: str | None
    site_type_filter: str | None
    total_count: int
    sites: list[dict] = field(default_factory=list)

    def to_tool_text(self) -> str:
        filters = []
        if self.commodity_filter:
            filters.append(f"commodity~'{self.commodity_filter}'")
        if self.site_type_filter:
            filters.append(f"type='{self.site_type_filter}'")
        filter_note = f" ({', '.join(filters)})" if filters else ""

        if self.total_count == 0:
            return (
                f"No MINEDEX mining sites found within {self.radius_km:.0f} km of "
                f"'{self.location_label}'{filter_note}."
            )

        lines = [
            f"{s.get('site_title', '?')} — {s.get('target_com') or s.get('commodity', '?')}, "
            f"{s.get('site_type_', '?')} ({s.get('site_stage', '?')})"
            for s in self.sites[:_MAX_LISTED]
        ]
        more = f" (+{self.total_count - len(lines)} more not shown)" if self.total_count > len(lines) else ""
        return (
            f"Found {self.total_count} MINEDEX mining site(s) within {self.radius_km:.0f} km "
            f"of '{self.location_label}'{filter_note}:\n- " + "\n- ".join(lines) + more
        )

    def to_geojson_features(self) -> list[dict]:
        """One Point feature per fetched site (not per total_count — only sites
        actually returned by the capped detail query have coordinates available)."""
        features = []
        for site in self.sites:
            lat, lon = site.get("latitude"), site.get("longitude")
            if lat is None or lon is None:
                continue
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {
                        "kind": "mining_deposit",
                        "site_title": site.get("site_title"),
                        "commodity": site.get("target_com") or site.get("commodity"),
                        "commodity_category": site.get("commodity"),
                        "site_type": site.get("site_type_"),
                        "site_stage": site.get("site_stage"),
                    },
                }
            )
        return features


@dataclass
class MiningTenementsResult:
    location_label: str
    radius_km: float
    type_filter: str | None
    status_filter: str | None
    total_count: int
    tenements: list[dict] = field(default_factory=list)

    def to_tool_text(self) -> str:
        filters = []
        if self.type_filter:
            filters.append(f"type~'{self.type_filter}'")
        if self.status_filter:
            filters.append(f"status='{self.status_filter}'")
        filter_note = f" ({', '.join(filters)})" if filters else ""

        if self.total_count == 0:
            return (
                f"No mining tenements found within {self.radius_km:.0f} km of "
                f"'{self.location_label}'{filter_note}."
            )

        lines = [
            f"{t.get('tenid', '?')} — {t.get('type', '?')}, {t.get('tenstatus', '?')}, "
            f"holder: {t.get('holder1', '?')}, area: {t.get('legal_area', '?')} {t.get('unit_of_me', '')}"
            for t in self.tenements[:_MAX_LISTED]
        ]
        more = f" (+{self.total_count - len(lines)} more not shown)" if self.total_count > len(lines) else ""
        return (
            f"Found {self.total_count} mining tenement(s) within {self.radius_km:.0f} km "
            f"of '{self.location_label}'{filter_note}:\n- " + "\n- ".join(lines) + more
        )
