---
name: cpu-coin-hunter
description: >
  Discover new CPU-mineable cryptocurrency projects daily from multiple sources.
  Use when: user asks about new CPU mining coins, finding mineable coins, CPU crypto projects,
  mining new altcoins, CPU PoW coins, RandomX coins, or wants automated scanning of
  BitcoinTalk ANN, GitHub, and WhatToMine for fresh CPU mining opportunities.
  Supports: daily scheduled scanning, new project alerts, revenue ranking, multi-source discovery.
---

# CPU Coin Hunter

Automated multi-source scanner for discovering new CPU-mineable cryptocurrency projects.

## Data Sources

1. **BitcoinTalk ANN** — Altcoin Announcements board, filtered for CPU mining keywords
2. **GitHub** — New repositories with CPU mining, RandomX, YesPower, etc.
3. **WhatToMine CPU** — Live CPU coin profitability rankings

## Quick Start

### Run a scan

```bash
python3 scripts/hunter.py
```

Output:
- `data/hunter-YYYY-MM-DD.json` — Full structured data
- `data/hunter-YYYY-MM-DD.txt` — Human-readable report
- `data/known_projects.json` — Historical tracking database

### Run WhatToMine-only profitability check

```bash
python3 scripts/scanner.py
```

## How It Works

1. **First run**: Captures baseline of all known CPU projects across sources
2. **Subsequent runs**: Compares against `known_projects.json`, flags new discoveries
3. **New coins** get marked with 🆕 in the report
4. **CPU-explicit** BitcoinTalk posts tagged with 🔥CPU

## CPU Keywords Tracked

RandomX, CryptoNight, YesPower, YesCrypt, GhostRider, CPUPower, Argon2, MinotaurX,
SHA256mem, AstroBWT, VerusHash, Panthera, Equihash.

## Scheduling

Set up a daily cron job to auto-scan and push alerts:

```
cron: "0 9 * * *" (daily 9 AM)
task: Run hunter.py, report new findings, skip if nothing new
delivery: announce to user's channel
```

## Output Format

Reports include:
- 🆕 New BitcoinTalk announcements (with CPU tag detection)
- 💻 New GitHub repos (stars, language, creation date)
- 📊 WhatToMine profitability top 5
- Summary stats across all sources

## Dependencies

Python 3 standard library only (urllib, json, re, html.parser). No pip installs needed.
