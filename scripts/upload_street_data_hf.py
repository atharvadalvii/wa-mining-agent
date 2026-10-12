"""Uploads the offline WA street data to a (free) Hugging Face dataset repo, which the
hosted container downloads at startup (GEOAGENT_DATA_HF_REPO).

One-time setup, from a machine where `python -m geoagent.setup_local_wa` has already run:

    pip install -e ".[hf]"
    huggingface-cli login          # a token with write access; never paste it into files
    python scripts/upload_street_data_hf.py YOUR_HF_USERNAME/wa-street-data

Only the driving and walking tables are uploaded (the bike tables are the largest and
are not needed by the hosted app). The dataset is public so the container needs no token.
The data derives from OpenStreetMap (ODbL), so the dataset card carries the attribution.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from geoagent.geospatial import local_extract

CARD = """---
license: odbl
pretty_name: Western Australia street network (OpenStreetMap)
---

Pre-processed Western Australia street network tables (driving and walking) used by
https://github.com/atharvadalvii/wa-mining-agent for offline routing.

Derived from OpenStreetMap data via a Geofabrik extract. © OpenStreetMap contributors,
available under the Open Database License (ODbL): https://www.openstreetmap.org/copyright
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("repo_id", help="e.g. yourname/wa-street-data")
    parser.add_argument("--dry-run", action="store_true", help="list what would be uploaded")
    args = parser.parse_args()

    tables = sorted(
        p
        for p in local_extract.CACHE_DIR.glob("*.parquet")
        if p.name.split("_", 1)[0] in ("drive", "walk")
    )
    pbf = local_extract.EXTRACT_PATH
    missing = [] if tables and pbf.exists() else ["run `python -m geoagent.setup_local_wa` first"]
    if missing:
        print("Street data not found:", *missing, file=sys.stderr)
        return 1

    total_mb = sum(p.stat().st_size for p in [*tables, pbf]) / 1e6
    print(f"{len(tables)} tables + {pbf.name}: {total_mb:,.0f} MB -> dataset {args.repo_id}")
    if args.dry_run:
        for p in [*tables, pbf]:
            print("  ", p)
        return 0

    from huggingface_hub import HfApi

    api = HfApi()
    api.create_repo(args.repo_id, repo_type="dataset", exist_ok=True)
    api.upload_file(
        path_or_fileobj=CARD.encode(), path_in_repo="README.md", repo_id=args.repo_id, repo_type="dataset"
    )
    for p in tables:
        api.upload_file(
            path_or_fileobj=str(p),
            path_in_repo=f"local_network/{p.name}",
            repo_id=args.repo_id,
            repo_type="dataset",
        )
        print("uploaded", p.name, flush=True)
    api.upload_file(
        path_or_fileobj=str(pbf),
        path_in_repo=f"osm_extracts/{pbf.name}",
        repo_id=args.repo_id,
        repo_type="dataset",
    )
    print("done: https://huggingface.co/datasets/" + args.repo_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
