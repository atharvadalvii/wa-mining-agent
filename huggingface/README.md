---
title: WA Mining Agent
emoji: ⛏️
colorFrom: yellow
colorTo: red
sdk: docker
app_port: 8501
pinned: false
short_description: Natural-language assistant for Western Australian mining data
---

# WA Mining Agent

Ask in plain English about Western Australian mines, mineral deposits and mining
tenements (live DMIRS data), plus routes and drive-time areas over a Western Australian
street network. Results appear on a live map.

- Source code and documentation: https://github.com/atharvadalvii/wa-mining-agent
- Mining data: DMIRS MINEDEX and TENGRAPH (Government of Western Australia)
- Street data: © OpenStreetMap contributors (ODbL)

Each visitor session is limited in length to keep the shared model usage small.
