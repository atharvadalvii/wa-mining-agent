"""Optional AWS (S3) integration for hosting the app.

Everything here is off unless configured, so local use is unaffected:

- GEOAGENT_DATA_S3_URI: the offline WA street network is far too big for the repo or a
  container image, so a container downloads it from S3 at startup instead.
- GEOAGENT_MAPS_S3_BUCKET: a hosted container's local disk is private to that one
  container, so a "map saved to /app/maps/..." path is useless to a visitor. Uploading
  each map and linking a presigned URL gives them something they can open.

Requires boto3 (pip install -e ".[aws]"). Credentials come from the usual AWS chain
(on ECS, the task role), never from this code or the repo.

Run `python -m geoagent.cloud sync` to download the data (the container entrypoint does).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from geoagent.geospatial import local_extract

_DEFAULT_NETWORK_TYPES = ("drive", "walk")  # bike is the largest and rarely needed
_MAP_LINK_EXPIRY_S = 6 * 3600  # task-role credentials rotate, capping presigned links


def _split_s3_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("s3://"):
        raise ValueError(f"Expected an s3:// URI, got {uri!r}")
    bucket, _, prefix = uri[5:].partition("/")
    if not bucket:
        raise ValueError(f"No bucket in S3 URI {uri!r}")
    return bucket, prefix.strip("/")


def _client(client=None):
    if client is not None:
        return client
    import boto3

    return boto3.client("s3")


def sync_data_from_s3(
    s3_uri: str,
    dest: Path | None = None,
    network_types: tuple[str, ...] = _DEFAULT_NETWORK_TYPES,
    pbf_dest: Path | None = None,
    client=None,
) -> list[str]:
    """Downloads the offline WA street data from under `s3_uri`, skipping any file
    already present at the same size. Returns the names of the files fetched.

    Expected layout under the prefix (what the README's upload commands produce):
      local_network/<type>_nodes.parquet, <type>_edges.parquet  -> `dest`
      osm_extracts/*.osm.pbf                                    -> `pbf_dest`
    Only the parquet tables for `network_types` are fetched. The .pbf is also needed:
    pyrosm opens it to build each query's graph from the tables.
    """
    dest = dest if dest is not None else local_extract.CACHE_DIR
    pbf_dest = pbf_dest if pbf_dest is not None else local_extract.DATA_DIR
    bucket, prefix = _split_s3_uri(s3_uri)
    s3 = _client(client)

    fetched: list[str] = []
    pages = s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix)
    for page in pages:
        for obj in page.get("Contents", []):
            name = obj["Key"].rsplit("/", 1)[-1]
            if name.endswith(".parquet") and name.split("_", 1)[0] in network_types:
                target_dir = dest
            elif name.endswith(".osm.pbf"):
                target_dir = pbf_dest
            else:
                continue
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / name
            if target.exists() and target.stat().st_size == obj["Size"]:
                continue
            s3.download_file(bucket, obj["Key"], str(target))
            fetched.append(name)
    return fetched


def publish_map(path: Path, bucket: str | None = None, client=None) -> str:
    """Uploads a saved map and returns a presigned URL for it. With no bucket
    configured (or if the upload fails) returns the local path, so a map export
    problem never costs the visitor the actual answer."""
    bucket = bucket or os.environ.get("GEOAGENT_MAPS_S3_BUCKET")
    if not bucket:
        return str(path)
    try:
        s3 = _client(client)
        key = f"maps/{path.name}"
        s3.upload_file(
            str(path), bucket, key, ExtraArgs={"ContentType": "text/html; charset=utf-8"}
        )
        return s3.generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=_MAP_LINK_EXPIRY_S
        )
    except Exception:  # noqa: BLE001 - fall back to the local path
        return str(path)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args != ["sync"]:
        print("usage: python -m geoagent.cloud sync", file=sys.stderr)
        return 2
    uri = os.environ.get("GEOAGENT_DATA_S3_URI")
    if not uri:
        print("GEOAGENT_DATA_S3_URI is not set; nothing to sync.")
        return 0
    types = tuple(
        t.strip()
        for t in os.environ.get("GEOAGENT_DATA_NETWORK_TYPES", "").split(",")
        if t.strip()
    ) or _DEFAULT_NETWORK_TYPES
    fetched = sync_data_from_s3(uri, network_types=types)
    print(f"synced {len(fetched)} file(s) from {uri}: {', '.join(fetched) or 'already up to date'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
