# SPECTRE Training Pipeline

Desktop app (Electron + React, with a Python backend) that generates synthetic
training data for the SPECTRE Tasking Layer, the tactical AI model behind
[SPECTRE C2](https://github.com/ArpitTeli/spectre-app) for Arma 3.

It is one of three SPECTRE repos:

| Repo | Role |
|---|---|
| [spectre-app](https://github.com/ArpitTeli/spectre-app) | The C2 desktop app. Also holds the terrain tooling (cost grid, path planner, OAKOC extractor) in `scripts/`. |
| [spectre-mod](https://github.com/ArpitTeli/spectre-mod) | The Arma 3 mod that bridges the game to the app. |
| **spectre-terrain-intelligence** (this repo) | Generates and filters the training data for the Tasking Layer model. |

> The terrain tooling (cost grid, path planner, OAKOC feature extractor) is **not** in this
> repo. It lives in `spectre-app/scripts/`. This repo uses its output (the map files under
> `public/maps/` in spectre-app) as scenario input.

## What it does

- **Scenario generation:** random but realistic battlefield scenarios.
- **Teacher model:** an LLM, called through OpenRouter, writes tactical decisions.
- **Guardrail filter:** a shared, versioned guardrail kernel (`backend/guardrails/`) rejects
  geometrically or doctrinally invalid examples. The same logic backs the live command
  check in the C2 app, so the model is never trained on an order the runtime would refuse.
- **Judge:** a single Gemini judge, called directly through the Google Generative Language
  API, checks tactical soundness.
- **Export:** JSONL output for Unsloth fine-tuning.

## Pipeline stages

1. **Sample:** generate random scenarios (`sampler.py`).
2. **Teacher:** the LLM generates tactical decisions (`teacher.py`).
3. **Geo filter:** kernel-backed validation of spatial and doctrinal claims (`geo_filter.py`).
4. **Judge:** Gemini verification (`judge.py`).
5. **Resolve:** aggregate the verdicts (`resolver.py`).
6. **Export:** write the training JSONL (`export.py`).

State is stored in a local SQLite database (`backend/pipeline/spectre_training.db`, created on first run).

## Prerequisites

- Node.js 18+
- Python 3.10+
- An [OpenRouter API key](https://openrouter.ai/keys) (teacher)
- A [Gemini API key](https://aistudio.google.com/apikey) (judge)

## Setup

```bash
git clone https://github.com/ArpitTeli/spectre-terrain-intelligence.git
cd spectre-terrain-intelligence

# Frontend / Electron
npm install

# Python backend
python -m venv .venv
.venv\Scripts\activate            # Windows (macOS/Linux: source .venv/bin/activate)
pip install -r backend/requirements.txt

# Configuration
copy .env.example .env            # macOS/Linux: cp .env.example .env
# edit .env and add your keys
```

## Run

```bash
npm start            # React dev server + Electron
# or separately
npm run react
npm run electron
```

Usage: enter the keys in the **CONFIG** tab, then click **RUN FULL PIPELINE** or run
individual stages. Progress shows in the **DASHBOARD** tab.

## Build

```bash
npm run build-win    # Windows installer in dist/
```

Only Windows packaging is configured.

## Configuration

Set in `.env` (see `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | (required) | Teacher model calls |
| `GEMINI_API_KEY` | (required) | Judge calls |
| `TEACHER_MODEL` | `kimi-k3` | Teacher model id |
| `JUDGE_MODEL` | `gemini-2.5-pro` | Judge model id |
| `TARGET_EXAMPLES` | `1000` | Examples to generate |
| `MAP_NAME` | `stratis` | Map used for scenarios |

## Repository layout

```
├── electron/               Electron main process and IPC bridge
├── src/                    React UI (CONFIG, DASHBOARD, stage runner, log console)
├── public/                 React static assets
├── backend/
│   ├── pipeline_runner.py  Entry point the Electron app drives over stdin/stdout
│   ├── requirements.txt
│   ├── pipeline/           sampler, teacher, geo_filter, judge, resolver, export, db, config
│   └── guardrails/         Shared Guardrail Kernel (see backend/guardrails/README.md)
├── .env.example
└── package.json
```

## Cost

Cost depends on the models you set. The old estimate of about $14 per 1,000 examples
assumed three paid models (a teacher and two judges). The pipeline now uses one judge, so
check your provider's current pricing for the two models you configure.

## Known issues

- `backend/pipeline_runner.py` still imports `JUDGE_A_MODEL` and `JUDGE_B_MODEL` from
  `pipeline/config.py`, which now defines only `JUDGE_MODEL`. Fixing it needs a code change.
- `build/` (a compiled React bundle) and `backend/pipeline/spectre_training.db` are tracked in git.

## License

All rights reserved. Part of the SPECTRE C2 system for Arma 3.
