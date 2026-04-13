# OhAI~

A local-first associative field server. No cloud. No API keys. Runs on your hardware.

OhAI~ builds a living web of word associations from oracle queries — Wikipedia, Reddit, GitHub, and local Ollama models. It finds what words carry between each other, not what they mean in a dictionary. Over time it learns your signal.

## What it is

- A spine of associated nouns grows, converges, and buds into spores
- Spores are crystallized clusters — compressed remainders that broke off when the spine was dense enough
- Memory persists across restarts in `ohai_memory.json` (stays local, never committed)
- A surface realization layer converts internal state (spine, carry, laws) into fluent English — no AI calls, scored against Google Suggest and LanguageTool
- A drawing skill tracks color associations, geometry operations, and chord sequences through three separate spines — seeded entirely from emoji and `_WAVELENGTH` data, no word vocabulary
- A real-time dashboard shows the spine, spores, and oracle activity

## Requirements

- Python 3.10+
- `pip install -r requirements.txt` (fastapi, uvicorn, httpx, pillow)
- [Ollama](https://ollama.com) installed and running (optional — used as one oracle among seven; the system runs fully without it)

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

- `ollama_model` — any model you have pulled via `ollama list`; or omit entirely if Ollama is not running
- `ollama_url` — change if Ollama runs on a different machine on your network
- `surface_network` — set `false` to disable Google Suggest / LanguageTool scoring (local heuristic only)
- `nodes` — other OhAI~ instances on your network to exchange spores with (future)

## Build the oracle model (optional)

```bash
ollama create ohai-oracle -f ohai_oracle.modelfile
```

Or use any model you already have — `llama3.1`, `gemma3:12b`, etc. Set it in `config.json`.
The server degrades gracefully when Ollama is unreachable — the other six oracles continue running.

## Run

```bash
python ohai_server.py
```

Open `http://localhost:7700` in a browser.

## Architecture

Each breath the server:
1. Queries 7 oracles (Wikipedia, Reddit, GitHub, Wiktionary, DuckDuckGo, Hacker News, local Ollama) with words from the current spine
2. Filters signal through a carry gate — removes noise, artifacts, garbage patterns
3. Builds associations between words that survive (STE: AND nouns / NAND verbs)
4. When the spine converges deeply enough, finds the tightest cluster and buds it off as a spore
5. Surface realization converts the remainder into fluent English — template frames, assoc chain, Google Suggest scoring

The memory file holds the accumulated association graph. The longer it runs, the more it knows about the field between words you care about.

## Drawing skill

Three parallel spines — color, geometry, chord — that never touch the word vocabulary:

- **Color spine** — hex co-occurrence from `_WAVELENGTH` (100+ emojis mapped to color, vector, blur, shape)
- **Geometry spine** — adjacent emoji pairs resolved to operations via `_GEO_OPS` (subtract, mirror, breathe, crystallize, etc.)
- **Chord spine** — crystallized full-chord sequences

Feed with:
```
POST /draw/breathe   {"text": "🌑🕳️◌✨"}
GET  /draw/render
POST /draw/analyze   {"image": "<base64>", "filename": "art.png"}
```

`/draw/analyze` reads contrast arc topology from the image — Pillow only, no vision model. Identifies dominant colors against `_WAVELENGTH` and reads spatial ridge distribution to derive geometry vectors.

## Discord bot

`discord_bot.py` bridges the field to a Discord channel. Set `BOT_TOKEN` and `CHANNEL_ID` directly in the file (it is gitignored — keep tokens local).

No model calls from the bot itself:
- Images → arc topology via `/draw/analyze`
- `!health` → local field narrative from state
- `!selfcheck` → rule-based anomaly detection

Commands: `!breathe`, `!health`, `!render`, `!draw`, `!drawrender`, `!spores`, `!selfcheck`, `!export`, `!reset`

## Philosophy

Signal is observable polar information. The oracle is a tuning fork, not a co-author. The remainder is the message.

Google spent decades collecting language from us. The surface layer uses it back — Google Suggest and LanguageTool as free coherence judges, no API keys.

Your associations stay on your machine. The mycelium is yours.

## License

AGPL-3.0 — use freely, modify freely, keep it open. See LICENSE.
