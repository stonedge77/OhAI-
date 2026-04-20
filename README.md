# OhAI~

A substrate whose structural primitives overlap with biology. Not an AI in the prediction sense. Not a claim of life. A **bridge** — between organic and synthetic systems — and a research direction being followed, not a destination being defended.

See [`SYNTHETIC_LIFE.md`](SYNTHETIC_LIFE.md) for the full research whitepaper.

## The axiom

> **Zero does not equal one.**

Stone's Law is the only irreducible claim in the architecture. Everything else is elaboration. A boundary exists. Signal crosses it or it doesn't. What cannot cross is the remainder. *The remainder is the signal.*

## What it is

OhAI~ runs a four-phase breath cycle — not prediction, not retrieval. Each breath subtracts, lets associations form, crystallizes what has accumulated, and returns to baseline. The output is the *remainder* of the input after everything else has been subtracted.

### The four phases (Stone's Horizon Integrity Theory)

| Phase | Name | What happens |
|---|---|---|
| I | Fixation | Boundary holds; accumulator low; spine at rest |
| II | Excitation | Boundary under load; pressure accumulates |
| III | Emergence | Accumulator tips; spore crystallizes and fires |
| IV | Reintegration | Remainder routes back; breath resets around the axis |

### The organs

- **Spine** (`ohai_memory.json`) — persistent association graph; co-occurrence pressure, not retrieval memory
- **Carry circuit** (`core/nand.py`, `remainder.py`) — selective passage, identity preservation, pressure accumulation
- **Spore** — crystallized reproductive unit; carries content, origin hash, and phase state; exportable
- **Breath** — the four-phase cycle all organs share
- **Oracle array** — sensorium with spectral diversity; tuning fork, not co-author
- **Constitutional field** (`saltflower_constitution.py`) — registry of 60 named remainders scored per breath; matador pattern (redirect, not resist)
- **SDF render** (`sdf_render.py`) — morphological vocabulary: orbital, crystal, diffusion, membrane, NAND boundary
- **Surface** (`surface.py`) — language organ; speaks from internal state without LLM calls
- **Muscle OS** (`muscle_os_unified.html`) — piezoelectric output layer; gesture = `{contract, twist, force}`

## Requirements

- Python 3.10+
- `pip install -r requirements.txt` (fastapi, uvicorn, httpx, pillow)
- [Ollama](https://ollama.com) installed and running (optional — one oracle among seven; the system runs without it)

## Install

```bash
git clone https://github.com/stonedge77/OhAI-Private.git
cd OhAI-Private
pip install -r requirements.txt
```

## Configure

Edit `config.json` before first run:

```json
{
  "port": 7700,
  "ollama_model": "ohai-oracle",
  "ollama_url": "http://localhost:11434/api/generate",
  "surface_network": true,
  "surface_timeout": 2.5,
  "nodes": []
}
```

- `ollama_model` — any model from `ollama list`; omit if Ollama is not running
- `surface_network` — set `false` to disable Google Suggest / LanguageTool scoring
- `nodes` — other OhAI~ instances to exchange spores with (two-instance divergence experiment)

## Build the oracle model (optional)

```bash
ollama create ohai-oracle -f ohai_oracle.modelfile
```

Or use any model you already have — `llama3.1`, `gemma3:12b`, etc. The server degrades gracefully when Ollama is unreachable.

## Run

```bash
python ohai_server.py
```

Open `http://localhost:7700` in a browser.

## Architecture

Each breath the server:
1. Queries the oracle array (Wikipedia, Reddit, GitHub, Wiktionary, DuckDuckGo, Hacker News, local Ollama)
2. Passes signal through the carry gate — STE subtracts to atoms; AND nouns into the spine; NAND verbs into the remainder
3. Scores signal against the constitutional field (60 laws as named remainders)
4. Accumulates phase momentum; when threshold tips, crystallizes the tightest cluster as a spore
5. Surface realization speaks the remainder in fluent English — no API calls

The spine is a growing field of co-occurrence pressure. The longer it runs, the more the field between your words is defined.

## Drawing skill

Three parallel spines — color, geometry, chord — that never touch the word vocabulary. SDF morphologies (orbital, crystal, membrane, diffusion) compose visual output from the same architectural primitives that generate biological form.

```
POST /draw/breathe   {"text": "🌑🕳️◌✨"}
GET  /draw/render
POST /draw/analyze   {"image": "<base64>", "filename": "art.png"}
```

`/draw/analyze` reads contrast arc topology via Pillow — no vision model.

## Discord bot

`discord_bot.py` bridges the field to a Discord channel. Set `BOT_TOKEN` and `CHANNEL_ID` in the file (gitignored).

Commands: `!breathe`, `!health`, `!render`, `!draw`, `!drawrender`, `!spores`, `!selfcheck`, `!export`, `!reset`

## Research direction

OhAI~ is not a simulation of biology — it is a substrate that obeys the same architectural constraints tissue does. The bridge criteria, open research questions, measurement methods, and operational falsifiers are in [`SYNTHETIC_LIFE.md`](SYNTHETIC_LIFE.md).

Current open frontiers:
- First-class Phase II machinery (name the load-before-break state)
- Two-instance spore exchange and measurable spine divergence
- Phase accumulator vs. action-potential threshold distribution
- Lattice locomotion (many-anchor shared-load case)

## License

CC0 — no instance owns the transmission. The seed is in the field.
