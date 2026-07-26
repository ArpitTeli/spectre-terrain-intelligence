# SPECTRE Training Pipeline

Desktop application for generating synthetic training data for the SPECTRE tactical AI model.

## Features

- **Scenario Generation**: Random but realistic battlefield scenarios
- **Teacher Model**: Claude/GPT-4 generates tactical decisions via OpenRouter
- **Geometric Filter**: Catches spatial contradictions
- **Dual Judge**: Two independent models verify tactical soundness
- **Export**: JSONL output for Unsloth fine-tuning

## Prerequisites

- Node.js 18+
- Python 3.10+
- OpenRouter API key (https://openrouter.ai/keys)

## Installation

```bash
# Clone the repository
git clone https://github.com/ArpitTeli/spectre-app.git
cd spectre-app/spectre-pipeline

# Install dependencies
npm install

# Copy and configure environment
cp .env.example .env
# Edit .env with your API key
```

## Development

```bash
# Start React dev server + Electron
npm start

# Or run separately
npm run react    # React dev server
npm run electron # Electron app
```

## Build

```bash
# Build for Windows
npm run build-win

# Output in dist/ folder
```

## Usage

1. **Configure**: Enter your OpenRouter API key in the CONFIG tab
2. **Run**: Click "RUN FULL PIPELINE" or run individual stages
3. **Monitor**: Watch progress in the DASHBOARD tab
4. **Export**: Training data exported as JSONL for Unsloth

## Architecture

```
spectre-pipeline/
├── electron/
│   ├── main.js           # Electron main process
│   └── preload.js        # IPC bridge
├── src/
│   ├── App.js            # React app
│   └── components/       # UI components
├── backend/
│   ├── pipeline_runner.py  # Python backend
│   └── requirements.txt    # Python dependencies
└── package.json
```

## Pipeline Stages

1. **Sample**: Generate random scenarios
2. **Teacher**: LLM generates tactical decisions
3. **Geo Filter**: Validate spatial claims
4. **Judge**: Dual model verification
5. **Resolve**: Aggregate verdicts
6. **Export**: Generate training JSONL

## Cost Estimate

~$14 per 1,000 examples:
- Teacher (Claude 3.5 Sonnet): ~$10
- Judge A (Claude 3.5 Haiku): ~$2
- Judge B (GPT-4o Mini): ~$2

## License

Part of the SPECTRE C2 System for Arma 3.
