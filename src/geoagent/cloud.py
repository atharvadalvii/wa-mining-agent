"""Optional hosting integration: where a container gets its offline street data, and
where it publishes map exports. Supports AWS S3 and (free) Hugging Face datasets.

Everything here is off unless configured, so local use is unaffected:

- GEOAGENT_DATA_S3_URI or GEOAGENT_DATA_HF_REPO: the offline WA street network is far
  too big for the repo or a container image, so a container downloads it at startup
  instead, from an S3 prefix or from a public Hugging Face dataset repo.
- GEOAGENT_MAPS_S3_BUCKET: a hosted container's local disk is private to that one
  container, so a "map saved to /app/maps/..." path is useless to a visitor. Uploading
  each map and linking a presigned URL gives them something they can open.

S3 needs boto3 (pip install -e ".[aws]") and credentials from the usual AWS chain (on
ECS, the task role), never from this code or the repo. Hugging Face needs
huggingface_hub (pip install -e ".[hf]"); a public dataset needs no token.

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


def sync_data_from_hf(
    repo_id: str,
    dest: Path | None = None,
    network_types: tuple[str, ...] = _DEFAULT_NETWORK_TYPES,
    pbf_dest: Path | None = None,
    api=None,
    download=None,
) -> list[str]:
    """Same job as sync_data_from_s3, from a Hugging Face *dataset* repo laid out as
    local_network/<type>_nodes.parquet (and _edges) and osm_extracts/*.osm.pbf."""
    dest = dest if dest is not None else local_extract.CACHE_DIR
    pbf_dest = pbf_dest if pbf_dest is not None else local_extract.DATA_DIR
    if api is None:
        from huggingface_hub import HfApi

        api = HfApi()
    if download is None:
        from huggingface_hub import hf_hub_download

        download = hf_hub_download

    fetched: list[str] = []
    for folder, target_dir, wanted in (
        ("local_network", dest, lambda n: n.endswith(".parquet") and n.split("_", 1)[0] in network_types),
        ("osm_extracts", pbf_dest, lambda n: n.endswith(".osm.pbf")),
    ):
        for entry in api.list_repo_tree(repo_id, path_in_repo=folder, repo_type="dataset"):
            name = entry.path.rsplit("/", 1)[-1]
            if not wanted(name):
                continue
            target = target_dir / name
            if target.exists() and target.stat().st_size == entry.size:
                continue
            # hf_hub_download keeps the repo-relative path under local_dir, so pointing
            # local_dir at the parent of target_dir lands the file in target_dir.
            download(
                repo_id=repo_id,
                repo_type="dataset",
                filename=entry.path,
                local_dir=str(target_dir.parent),
            )
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
    types = tuple(
        t.strip()
        for t in os.environ.get("GEOAGENT_DATA_NETWORK_TYPES", "").split(",")
        if t.strip()
    ) or _DEFAULT_NETWORK_TYPES
    uri = os.environ.get("GEOAGENT_DATA_S3_URI")
    hf_repo = os.environ.get("GEOAGENT_DATA_HF_REPO")
    if uri:
        source, fetched = uri, sync_data_from_s3(uri, network_types=types)
    elif hf_repo:
        source, fetched = f"huggingface dataset {hf_repo}", sync_data_from_hf(hf_repo, network_types=types)
    else:
        print("Neither GEOAGENT_DATA_S3_URI nor GEOAGENT_DATA_HF_REPO is set; nothing to sync.")
        return 0
    print(f"synced {len(fetched)} file(s) from {source}: {', '.join(fetched) or 'already up to date'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
