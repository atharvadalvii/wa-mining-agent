"""Local, offline street network for Western Australia.

Built once from a downloaded Geofabrik OSM extract via pyrosm, then served
from an in-memory node/edge table with sub-second bounding-box queries — no
network dependency at query time. This exists because the free public
Overpass API this project otherwise relies on turned out to be unreliable
(backend IPs whose reachability flaps within seconds, not hours) — for WA,
where this project's actual use cases concentrate, an offline extract sidesteps
that entirely.

Falls back to live OSMnx/Overpass fetches (see geospatial/network.py) for
anything outside WA, or before the extract has been prepared.

One-time setup (~3-5 minutes total): python -m geoagent.setup_local_wa
"""

from __future__ import annotations

from pathlib import Path

import networkx as nx

EXTRACT_URL = (
    "https://download.geofabrik.de/australia-oceania/australia/western-australia-latest.osm.pbf"
)
DATA_DIR = Path("data/osm_extracts")
EXTRACT_PATH = DATA_DIR / "western-australia-latest.osm.pbf"
CACHE_DIR = Path(".cache/local_network")

# Generous WA bounding box (real border is irregular; this is a coarse
# rectangle with margin, just enough to decide "try the local extract first").
WA_NORTH, WA_SOUTH, WA_EAST, WA_WEST = -13.0, -36.0, 130.0, 112.0

# geoagent network_type -> pyrosm network_type
_PYROSM_NETWORK_TYPE = {"drive": "driving", "walk": "walking", "bike": "cycling"}

SUPPORTED_NETWORK_TYPES = tuple(_PYROSM_NETWORK_TYPE)


def is_within_wa(lat: float, lon: float) -> bool:
    return WA_SOUTH <= lat <= WA_NORTH and WA_WEST <= lon <= WA_EAST


def bbox_within_wa(north: float, south: float, east: float, west: float) -> bool:
    return is_within_wa(north, east) and is_within_wa(south, west)


def _parquet_paths(network_type: str) -> tuple[Path, Path]:
    return (
        CACHE_DIR / f"{network_type}_nodes.parquet",
        CACHE_DIR / f"{network_type}_edges.parquet",
    )


def is_extracted(network_type: str) -> bool:
    nodes_path, edges_path = _parquet_paths(network_type)
    return nodes_path.exists() and edges_path.exists()


def download_extract() -> Path:
    if EXTRACT_PATH.exists():
        return EXTRACT_PATH

    import requests

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Downloading WA OSM extract from {EXTRACT_URL} (~110 MB)...")
    tmp_path = EXTRACT_PATH.with_suffix(".tmp")
    with requests.get(EXTRACT_URL, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        with open(tmp_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    tmp_path.rename(EXTRACT_PATH)
    return EXTRACT_PATH


def extract_network(network_type: str) -> None:
    """One-time (per network_type): parse the PBF and save the filtered
    node/edge tables to parquet for fast bbox-filtered reloading later."""
    from pyrosm import OSM

    pyrosm_type = _PYROSM_NETWORK_TYPE[network_type]
    osm = OSM(str(download_extract()))
    nodes, edges = osm.get_network(network_type=pyrosm_type, nodes=True)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    nodes_path, edges_path = _parquet_paths(network_type)
    nodes.to_parquet(nodes_path)
    edges.to_parquet(edges_path)


class LocalNetworkStore:
    """In-memory cache of the parsed WA node/edge tables, per network_type."""

    def __init__(self) -> None:
        self._tables: dict[str, tuple] = {}
        self._osm = None

    def _load_tables(self, network_type: str):
        if network_type not in self._tables:
            import geopandas as gpd

            nodes_path, edges_path = _parquet_paths(network_type)
            nodes = gpd.read_parquet(nodes_path)
            edges = gpd.read_parquet(edges_path)
            self._tables[network_type] = (nodes, edges)
        return self._tables[network_type]

    def _get_osm(self):
        if self._osm is None:
            from pyrosm import OSM

            self._osm = OSM(str(EXTRACT_PATH))
        return self._osm

    def get_subgraph(
        self, north: float, south: float, east: float, west: float, network_type: str
    ) -> nx.MultiDiGraph:
        nodes, edges = self._load_tables(network_type)
        bbox_ids = set(nodes.cx[west:east, south:north]["id"])
        # An edge is kept if EITHER endpoint is in the bbox, not just both. A
        # strict both-endpoints filter silently drops any road that crosses the
        # boundary entirely, which can strand the node nearest to a query point
        # sitting right at the box's edge — nearest_nodes() then snaps to
        # whatever's left, which can be far away, producing a silently wrong
        # (too-short) route. This intentionally pulls in nodes just outside the
        # box so no real connectivity near the edge gets cut.
        sub_edges = edges[edges["u"].isin(bbox_ids) | edges["v"].isin(bbox_ids)]
        involved_ids = set(sub_edges["u"]) | set(sub_edges["v"])
        sub_nodes = nodes[nodes["id"].isin(involved_ids)]

        pyrosm_type = _PYROSM_NETWORK_TYPE[network_type]
        return self._get_osm().to_graph(
            sub_nodes,
            sub_edges,
            graph_type="networkx",
            osmnx_compatible=True,
            network_type=pyrosm_type,
            # Default (False) silently keeps only the largest connected
            # component. Near a bbox edge, the road segment nearest a query
            # point can end up in a smaller disconnected piece — dropping it
            # doesn't error, it just makes nearest_nodes() snap to a distant
            # node instead, producing a silently wrong (too-short) route. Keep
            # everything; a genuinely unreachable snap should fail loudly via
            # "no path found", not succeed with a wrong answer.
            retain_all=True,
        )


default_store = LocalNetworkStore()
