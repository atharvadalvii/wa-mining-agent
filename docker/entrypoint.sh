#!/bin/sh
set -e

# Fetch the offline street data first (no-op unless GEOAGENT_DATA_S3_URI is set), so the
# first visitor isn't the one who waits for it.
python -m geoagent.cloud sync

exec streamlit run src/geoagent/dashboard.py \
    --server.port=8501 \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --browser.gatherUsageStats=false
