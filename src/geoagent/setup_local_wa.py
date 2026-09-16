"""One-time setup: download the WA OSM extract and pre-extract driving/walking/
cycling networks for fast, offline local routing (see geospatial/local_extract.py).

Run with: python -m geoagent.setup_local_wa
"""

from __future__ import annotations

import time

from geoagent.geospatial import local_extract


def main() -> None:
    print("Downloading WA OSM extract (if not already present)...")
    start = time.time()
    local_extract.download_extract()
    print(f"  done in {time.time() - start:.0f}s\n")

    for network_type in local_extract.SUPPORTED_NETWORK_TYPES:
        if local_extract.is_extracted(network_type):
            print(f"'{network_type}' network already extracted, skipping.")
            continue
        print(f"Extracting '{network_type}' network (this can take a minute or two)...")
        start = time.time()
        local_extract.extract_network(network_type)
        print(f"  done in {time.time() - start:.0f}s")

    print("\nSetup complete. WA routing/isochrone queries will now use the local extract.")


if __name__ == "__main__":
    main()
