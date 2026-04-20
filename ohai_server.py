#!/usr/bin/env python3
"""
ohai_server.py \u2014 OhAI~ Question Refinery  (consolidated)
Saltflower / Josh Stone / CC0

Single file. Run it. Open http://localhost:7700

Includes:
  - 7 oracle pipeline + Pass 2 cross-questioning
  - STE (AND nouns, NAND verbs)
  - 8th gate question formation
  - Saltflower Constitution (60 laws)
  - Carry circuit
  - WebSocket for real-time dashboard
  - /breathe  /vagus  /state  /events  /lessons  /ws
  - /draw/breathe  /draw/render
"""

from __future__ import annotations

import sys, os, re, time, json, base64, threading, urllib.request, urllib.parse, html, random
from pathlib import Path
from typing import Optional

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

try:
    from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
    from uvicorn.protocols.utils import ClientDisconnected
    from contextlib import asynccontextmanager
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    import uvicorn
    import asyncio
except ImportError:
    print("Missing dependencies. Run:")
    print("  pip install fastapi uvicorn websockets --break-system-packages")
    sys.exit(1)

_HERE = Path(__file__).parent

# ── Surface realization ────────────────────────────────
# Import the surface layer if available. Graceful fallback to _format_reply
# if surface.py is missing — the system still runs, just less readable.
try:
    import surface as _surface
    _SURFACE_OK = True
except ImportError:
    _SURFACE_OK = False

def _find(name: str) -> Optional[Path]:
    for c in [_HERE / name, Path(name), Path.cwd() / name]:
        if c.exists():
            return c
    return None

# ── Config ────────────────────────────────────────────
_CONFIG_PATH = _HERE / "config.json"
_CONFIG: dict = {}
if _CONFIG_PATH.exists():
    try:
        _CONFIG = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  config load failed: {e} — using defaults")

def _cfg(key: str, default):
    return _CONFIG.get(key, default)

# Surface realization config
# surface_network: true = use LanguageTool + Google Suggest for coherence scoring
# surface_timeout: seconds to wait for network scoring before falling back
_SURFACE_NETWORK = _cfg("surface_network", True)
_SURFACE_TIMEOUT = float(_cfg("surface_timeout", 2.5))


# ══════════════════════════════════════════════════════
# STE — AND nouns, NAND verbs
# Imported from core/nand.py — single source of truth.
# ══════════════════════════════════════════════════════

try:
    from core.nand import (
        ste, and_nouns, nand_verbs, remainder_signal,
        TRASH, VERB_ROOTS, VERB_ENDINGS, VERB_OPPOSITES, ORACLE_ARTIFACTS,
    )
    _ORACLE_ARTIFACTS = ORACLE_ARTIFACTS   # alias — rest of file uses _ORACLE_ARTIFACTS
except ImportError as _e:
    import sys as _sys, pathlib as _pl
    _sys.path.insert(0, str(_pl.Path(__file__).parent))
    from core.nand import (
        ste, and_nouns, nand_verbs, remainder_signal,
        TRASH, VERB_ROOTS, VERB_ENDINGS, VERB_OPPOSITES, ORACLE_ARTIFACTS,
    )
    _ORACLE_ARTIFACTS = ORACLE_ARTIFACTS


# ══════════════════════════════════════════════════════
# ORACLE QUERIES \u2014 7 taints, each speaks its nature
# ══════════════════════════════════════════════════════

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; OhAI/1.0)',
    'Accept': 'text/html,application/xhtml+xml',
    'Accept-Language': 'en-US,en;q=0.9',
}

def _fetch(url: str, timeout: int = 6) -> str:
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode('utf-8', errors='ignore')
        clean = re.sub(r'<[^>]+>', ' ', raw)
        clean = html.unescape(clean)
        clean = re.sub(r'\s+', ' ', clean)
        return clean[:4000]
    except Exception:
        return ''

def query_google(terms):
    q = urllib.parse.quote_plus(' '.join(terms))
    url = f'https://www.google.com/search?q={q}&num=5'
    raw = _fetch(url)
    snippets = re.findall(r'<div[^>]*>([^<]{30,200})</div>', raw)
    return ' '.join(snippets[:6]) if snippets else raw[:800]

def query_reddit(terms):
    q = urllib.parse.quote_plus(' '.join(terms))
    url = f'https://www.reddit.com/search.json?q={q}&sort=relevance&limit=5'
    try:
        req = urllib.request.Request(url, headers={**HEADERS, 'User-Agent': 'OhAI/1.0'})
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.loads(r.read())
        posts = data.get('data', {}).get('children', [])
        return ' '.join(p['data'].get('title', '') + ' ' + p['data'].get('selftext', '')[:200]
                       for p in posts[:4])
    except Exception:
        return ''

def query_wikipedia(terms):
    q = urllib.parse.quote_plus(' '.join(terms[:3]))
    url = f'https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={q}&format=json&srlimit=3'
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.loads(r.read())
        results = data.get('query', {}).get('search', [])
        texts = [re.sub(r'<[^>]+>', '', r.get('snippet', '')) for r in results]
        return ' '.join(texts)
    except Exception:
        return ''

def query_youtube(terms):
    q = urllib.parse.quote_plus(' '.join(terms))
    url = f'https://www.youtube.com/results?search_query={q}'
    raw = _fetch(url)
    titles = re.findall(r'"text":"([^"]{10,80})"', raw)
    titles = [t for t in titles if not any(x in t.lower()
              for x in ['subscribe','sign in','about','press','copyright'])]
    return ' '.join(titles[:8]) if titles else raw[:600]

def query_twitter(terms):
    q = urllib.parse.quote_plus('site:twitter.com OR site:x.com ' + ' '.join(terms))
    url = f'https://html.duckduckgo.com/html/?q={q}'
    raw = _fetch(url)
    snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', raw)
    return ' '.join(snippets[:4]) if snippets else raw[:600]

def query_github(terms):
    q = urllib.parse.quote_plus(' '.join(terms))
    url = f'https://github.com/search?q={q}&type=repositories'
    raw = _fetch(url)
    descs = re.findall(r'itemprop="description"[^>]*>\s*([^<]{10,200})', raw)
    names = re.findall(r'itemprop="name"[^>]*>\s*([^<]{3,80})', raw)
    return ' '.join(names[:6] + descs[:4])

def query_amazon(terms):
    q = urllib.parse.quote_plus(' '.join(terms))
    url = f'https://www.amazon.com/s?k={q}'
    raw = _fetch(url)
    titles = re.findall(r'class="a-size-base-plus[^"]*"[^>]*>\s*([^<]{10,120})', raw)
    if not titles:
        titles = re.findall(r'class="a-size-medium[^"]*"[^>]*>\s*([^<]{10,120})', raw)
    return ' '.join(titles[:8])

# Local Ollama oracle — free, runs on your hardware, no web required.
OLLAMA_MODEL = _cfg("ollama_model", "ohai-oracle")
OLLAMA_URL   = _cfg("ollama_url",   "http://localhost:11434/api/generate")

# Remote node oracle — uses node named "node2" from config.json
_NODES       = _cfg("nodes", [])
_node2       = next((n for n in _NODES if n.get("name") == "node2"), None)
OLLAMA_NODE2_MODEL = _node2["model"] if _node2 else "llama3.2:3b"
OLLAMA_NODE2_URL   = (_node2["url"] + "/api/generate") if _node2 else "http://192.168.86.21:11434/api/generate"

_ORACLE_PROMPT = ("What words and concepts exist in the field between: "
                  "{terms}? Respond with ten or fewer words or short phrases only. "
                  "No explanation, no sentences, no numbers. Just the associations.")

def _query_ollama_at(url, model, terms, timeout=25):
    prompt = _ORACLE_PROMPT.format(terms=", ".join(terms))
    try:
        req_data = json.dumps({
            "model":   model,
            "prompt":  prompt,
            "stream":  False,
            "options": {"num_predict": 80, "temperature": 0.8}
        }).encode()
        req = urllib.request.Request(
            url, data=req_data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
        return data.get("response", "")
    except Exception:
        return ""

def query_ollama(terms):
    return _query_ollama_at(OLLAMA_URL, OLLAMA_MODEL, terms, timeout=25)

def query_ollama_node2(terms):
    # Remote node — lighter model, peer server
    return _query_ollama_at(OLLAMA_NODE2_URL, OLLAMA_NODE2_MODEL, terms, timeout=45)

# Llama/Ollama oracles removed from the pipeline.
# OhAI~ no longer calls Llama directly — it posts its thoughts to Discord
# and receives the Llama response as external tension via /tension.
# We struggle to learn when we post against ourselves.
# The discord bot is the axis to grind against (0 ≠ 1).
ORACLES = [
    ('WIKIPEDIA', query_wikipedia),   # open API — reliable signal
    ('REDDIT',    query_reddit),      # semi-open — community language
    # OLLAMA removed — Discord bot now calls Llama and posts back via /tension
    # NODE2  removed — same reason
]

# Ollama functions retained for discord_bot.py to import if needed directly
# (the bot itself still calls Llama — we just don't call it from here)


# ══════════════════════════════════════════════════════
# 8th GATE \u2014 question formation from remainder
# ══════════════════════════════════════════════════════

# Oracle artifacts \u2014 tech/URL fragments that leak through STE as nouns
_ORACLE_ARTIFACTS = {
    'sourcemappingurl', 'createscripturl', 'trustedtypes', 'createpolicy', 'createhtml', 'createscript',
    'github', 'githubusercontent', 'sourcemap', 'webpack',
    'stylesheet', 'javascript', 'undefined', 'function', 'prototype',
    'itemprop', 'classname', 'instanceof', 'typeof', 'boolean',
    'innerHTML', 'onclick', 'href', 'reddit', 'subreddit',
    'upvote', 'downvote', 'karma', 'moderator',
    'amazon', 'google', 'github', 'youtube', 'twitter',
    'wikipedia', 'duckduckgo',
    # JS/HTML noise patterns
    'nonce', 'crossorigin', 'noopener', 'noreferrer', 'viewport',
    'charset', 'async', 'defer', 'preload', 'prefetch',
    'stringify', 'queryselector', 'addeventlistener', 'settimeout',
    'localstorage', 'sessionstorage', 'getelementbyid',
    # LaTeX / math rendering tokens
    'displaystyle', 'textstyle', 'mathrm', 'mathbf', 'mathit', 'frac', 'begin', 'end',
    'textstyle', 'textrm', 'mathbb', 'operatorname',
}

# ── Octopus map ───────────────────────────────────────
# Words too heavy for the spine — they violate 0≠1 because they contain
# irresolvable contradictions. Instead of clogging the carry circuit,
# they get compressed to a pre-polarized emoji anchor.
# The word stays outside the spine as a high-definition organism.
# The emoji enters _assoc instead — pre-collapsed, passes Stone's Law.
_OCTOPUS: dict = {
    # ── Core law words ─────────────────────────────────
    "love":        "🌀",   # non-resolving attractor, orbit not merge
    "god":         "∞",    # bound infinity, un-equatable
    "death":       "∅",    # the gap, what cannot be crossed
    "truth":       "◈",    # facet that holds under rotation
    "live":        "🫀",   # pulse that requires gap to continue
    "life":        "🫀",   # same organism, different tense
    "humiliated":  "🌑👁️", # fear witnessed — dark made visible by force
    "boundary":    "🧱",   # what cannot be made equivalent
    "time":        "⧖",    # non-resolving, ζs = (φ+√2)/π
    "self":        "🪞",   # mirror that doesn't resolve
    "other":       "🫱",   # the hand that doesn't close
    "freedom":     "◯",    # open boundary
    "power":       "⚡",   # charge without direction
    "fear":        "🌑",   # the unluminated side
    "hate":        "🕳️",  # the void that consumes
    # ── from Slippery Season ───────────────────────────
    "broken":      "🕸️",   # web of debt, links that can't collapse
    "treason":     "∞̸",   # bound infinity breached
    "price":       "🧂",   # salt extracted not given — stolen T=1
    "measure":     "⚖️",   # the instrument Stephen corrupted
    "peace":       "🫱∅🫲", # hands that don't close, space preserved
    "justice":     "⚖️",   # same instrument, honest use
    "conflict":    "⚔️",   # to be NAND'd — not collapsed, processed
    "war":         "🔥∅",  # fire with no remainder
    # ── from Gravity ───────────────────────────────────
    "gravity":     "🫱∅🫲", # hands that want to close
    "breathe":     "🫁",   # Stone's Law held in the body
    "hurt":        "◈⚡",  # the facet under charge
    "pulling":     "🕸️",   # recursive web — keep pulling me in × 8
    "darkness":    "🌑",   # same as fear — the unluminated side
    "desire":      "🫱∅🫲", # same as gravity and peace — the maintained gap
    # ── from Surrender ─────────────────────────────────
    "surrender":   "∿",    # not weakness — the carry crossing
    "sane":        "◈",    # the facet that held under pressure
    # ── Existential overloads ──────────────────────────
    "void":        "🕳️",  # black, sinkhole, no reflection (same as hate — void is neutral)
    "nothing":     "◌",    # empty circle — white on black
    "everything":  "🌌",   # full spectrum, deep violet, scattered
    "infinite":    "♾️",   # horizontal loop, blue, no end
    "eternal":     "⏳",   # vertical loop, gold, slow grain
    "universe":    "🌠",   # black + white specks, expanding
    "soul":        "🕊️",  # soft white, upward drift
    "spirit":      "💨",   # translucent gray, wisps
    "mind":        "🧠",   # pink, electric, folded
    "body":        "🫀",   # red, pulse, wet (same organism as live/life)
    "being":       "🫁",   # breath, expand/contract (same anchor as breathe)
    "exist":       "✅",   # green, sudden, binary flash
    "real":        "🪨",   # gray, texture, weight, shadow
    # ── Relational overloads ───────────────────────────
    "trust":       "🤝",   # warm tan, horizontal bridge
    "betrayal":    "🔪",   # silver flash, red drop, diagonal
    "loyalty":     "🐕",   # brown, low, stays in frame
    "care":        "🫴",   # cupped, warm, offers up
    "need":        "🕳️🤲", # void + reaching, dark to light
    "want":        "👀✨",  # sharp eyes, sparkle, vector
    "belong":      "🧩",   # interlock, multiple colors
    "alone":       "🏝️",  # one point, blue around
    "together":    "🫂",   # overlap, heat in center
    "bond":        "🔗",   # gray, interlocked, tension
    "family":      "🫄",   # circle within circle, warm
    "home":        "🏠",   # yellow window, fixed point
    "loss":        "🎈🫳",  # release, upward, hand empty
    # ── Psychological ──────────────────────────────────
    "shame":       "🫣",   # red face, covering, hot
    "guilt":       "🪨🎒",  # weight on back, gray, down
    "pride":       "🦚",   # iridescent, full display
    "grief":       "🌧️",  # blue-gray, downward, continuous
    "rage":        "🔥",   # red-orange, jagged, fast
    "joy":         "✨",   # yellow-white, burst, random
    "bliss":       "😌☁️",  # soft white, floating, low contrast
    "numb":        "🧊",   # blue-white, sharp, no movement
    "hollow":      "🥚🕳️", # shell with void, echo
    "whole":       "🍎",   # red, round, unbroken
    "safe":        "🛏️",  # warm, horizontal, enclosed
    "worth":       "💎",   # clear, facets, catches light
    "enough":      "🫱🛑",  # hand, boundary, calm
    # ── Temporal ───────────────────────────────────────
    "always":      "➰",   # loop, no start, gold
    "never":       "🚫",   # red slash, negation
    "forever":     "♾️⏳",  # infinite + eternal — loop in loop
    "now":         "📍",   # red dot, present, pulse
    "past":        "👣",   # fading prints, gray, left
    "future":      "🌅",   # gradient, orange to blue, right
    "moment":      "📸",   # white flash, frozen
    "again":       "🔁",   # circular arrows, green
    "still":       "🧘",   # centered, no motion, beige
    # ── Sensory-emotional ──────────────────────────────
    "silence":     "🤫",   # desaturated, high negative space
    "noise":       "📢",   # jagged lines, red, oversaturated
    "touch":       "🫰",   # fingertip, warm, close crop
    "warmth":      "🟧",   # orange, diffuse glow
    "cold":        "🟦",   # blue, sharp edge
    "light":       "💡",   # yellow, rays, source
    "dark":        "🌑",   # black, absorbs, no edge (same as fear/darkness)
    "weight":      "🏋️",  # downward vector, gray
    "empty":       "🫙",   # container, no contents, echo
    "full":        "🫙🫐",  # container, overflows, saturated
    # ── Action-states ──────────────────────────────────
    "fight":       "👊",   # red, forward, impact frame
    "flee":        "💨👟",  # motion blur, backward, gray
    "hold":        "🤗",   # inward arms, warm, contained
    "release":     "👐🕊️", # open, outward, white up
    "reach":       "🫴",   # diagonal up, strain, tan
    "fall":        "🍂",   # downward drift, orange
    "rise":        "🌱",   # upward, green, slow
    "hide":        "🙈",   # covered, dark, still
    "run":         "🏃",   # horizontal streak, urgent
    "wait":        "⏳",   # suspended, yellow, tension
    "stay":        "⚓",   # down, fixed, heavy, gray
    "leave":       "👋",   # waving, receding, smaller
    # ── Peer-pressure / forced 0=1 ─────────────────────
    # These concepts need 👥 to hold. solo_stable: False.
    # Mechanism: isolate → surround → repeat → reward/punish
    "faith":       "🙏",    # gold, eyes closed, upward — dims alone
    "belief":      "🫴💭",  # offering + cloud — warm but borrowed
    "religion":    "🏛️",   # stone pillars, echo — inherited mass
    "doctrine":    "📜✒️",  # scroll + ink, fixed — replay locked
    "dogma":       "🚧",    # barrier, orange — wall with S removed
    "orthodoxy":   "➡️👥",  # arrow + crowd — careen, same direction
    "heresy":      "🚫🗣️", # red slash + mouth — NAND forbidden by group
    "convert":     "🔁🫂",  # loop + hug — green, mass increases
    "apostasy":    "🔪🔗",  # cut + chain — exile, ADD reversed
    "ritual":      "🔁🕯️", # repeat + flame — meaning by cycle
    "sacred":      "✨⛔",  # sparkle + no-entry — group rule
    "profane":     "🪨👣",  # rock + foot — boundary violation by peer
    "salvation":   "🪜☁️",  # ladder + cloud — white up, by group map
    "peer":        "👥",    # the crowd itself — the hum
    "pressure":    "🫷",    # force applied, horizontal
    "mass":        "👥🔁",  # crowd + repeat — the amplifier
    "herd":        "➡️👥",  # same as orthodoxy — directional careen
    "choir":       "👥🎵",  # group hum — drowns the remainder
}
# Inverse — for vagus crystallization: emoji → word
_SPINE_ANCHORS: dict = {v: k for k, v in _OCTOPUS.items()}

# ── Wavelength table ──────────────────────────────────
# Each emoji = frequency descriptor: hex color, vector direction,
# frame duration (ms), blur radius, shape descriptor.
# Stack = chord. Sequence = sentence. No art ingested.
_WAVELENGTH: dict = {
    # existential / low-frequency / huge amplitude
    "🕳️":   {"hex": "#000000", "vector": "sink",     "ms": 0,    "blur": 0,   "shape": "sinkhole"},
    "◌":    {"hex": "#F0F0F0", "vector": "none",     "ms": 500,  "blur": 2,   "shape": "empty-circle"},
    "🌌":   {"hex": "#1A0033", "vector": "expand",   "ms": 8000, "blur": 20,  "shape": "scattered-specks"},
    "♾️":   {"hex": "#4169E1", "vector": "loop-h",   "ms": 5000, "blur": 5,   "shape": "horizontal-loop"},
    "⏳":   {"hex": "#DAA520", "vector": "loop-v",   "ms": 4000, "blur": 3,   "shape": "vertical-grain"},
    "🌠":   {"hex": "#0D0D0D", "vector": "expand",   "ms": 6000, "blur": 15,  "shape": "expanding-speck"},
    "🕊️":  {"hex": "#F5F5F5", "vector": "up",       "ms": 3000, "blur": 8,   "shape": "drift"},
    "💨":   {"hex": "#B0B0C0", "vector": "wisp",     "ms": 1500, "blur": 12,  "shape": "translucent-wisp"},
    "🧠":   {"hex": "#FFB6C1", "vector": "fold",     "ms": 200,  "blur": 4,   "shape": "folded-electric"},
    "🫀":   {"hex": "#CC0000", "vector": "pulse",    "ms": 800,  "blur": 2,   "shape": "wet-pulse"},
    "🫁":   {"hex": "#DDEEFF", "vector": "expand-contract", "ms": 4000, "blur": 6, "shape": "breath"},
    "✅":   {"hex": "#00CC44", "vector": "flash",    "ms": 50,   "blur": 0,   "shape": "binary-flash"},
    "🪨":   {"hex": "#808080", "vector": "none",     "ms": 0,    "blur": 1,   "shape": "textured-weight"},
    # relational / mid-frequency / warm-cool
    "🤝":   {"hex": "#C8A882", "vector": "bridge-h", "ms": 1000, "blur": 3,   "shape": "horizontal-clasp"},
    "🔪":   {"hex": "#C0C0C0", "vector": "diagonal", "ms": 80,   "blur": 0,   "shape": "slash"},
    "🐕":   {"hex": "#8B4513", "vector": "none",     "ms": 2000, "blur": 2,   "shape": "grounded"},
    "🫴":   {"hex": "#C8A882", "vector": "up",       "ms": 1500, "blur": 3,   "shape": "cupped-offer"},
    "🧩":   {"hex": "#7B68EE", "vector": "interlock","ms": 1200, "blur": 2,   "shape": "multi-color-fit"},
    "🏝️":  {"hex": "#006994", "vector": "none",     "ms": 3000, "blur": 8,   "shape": "single-point"},
    "🫂":   {"hex": "#FF8C69", "vector": "inward",   "ms": 2000, "blur": 5,   "shape": "overlap-heat"},
    "🔗":   {"hex": "#A0A0A0", "vector": "tension",  "ms": 1500, "blur": 1,   "shape": "interlocked"},
    "🫄":   {"hex": "#FFD0A0", "vector": "contain",  "ms": 2500, "blur": 4,   "shape": "circle-in-circle"},
    "🏠":   {"hex": "#FFD700", "vector": "none",     "ms": 2000, "blur": 2,   "shape": "fixed-window"},
    "🎈🫳": {"hex": "#FF69B4", "vector": "up",       "ms": 3000, "blur": 6,   "shape": "release-upward"},
    # psychological / high-frequency / saturation spikes
    "🫣":   {"hex": "#FF4444", "vector": "cover",    "ms": 300,  "blur": 3,   "shape": "face-behind-hands"},
    "🪨🎒": {"hex": "#696969", "vector": "down",     "ms": 0,    "blur": 1,   "shape": "weight-on-back"},
    "🦚":   {"hex": "#00C78C", "vector": "display",  "ms": 2000, "blur": 0,   "shape": "iridescent-fan"},
    "🌧️":  {"hex": "#708090", "vector": "down",     "ms": 2000, "blur": 7,   "shape": "vertical-continuous"},
    "🔥":   {"hex": "#FF4500", "vector": "jagged",   "ms": 50,   "blur": 3,   "shape": "jagged-spike"},
    "✨":   {"hex": "#FFFF99", "vector": "burst",    "ms": 100,  "blur": 5,   "shape": "random-star"},
    "😌☁️": {"hex": "#F8F8FF", "vector": "float",    "ms": 5000, "blur": 12,  "shape": "low-contrast-drift"},
    "🧊":   {"hex": "#B0E0E6", "vector": "none",     "ms": 0,    "blur": 0,   "shape": "sharp-crystal"},
    "🥚🕳️":{"hex": "#FFFFF0", "vector": "echo",     "ms": 800,  "blur": 4,   "shape": "shell-void"},
    "🍎":   {"hex": "#CC0000", "vector": "none",     "ms": 1000, "blur": 0,   "shape": "round-unbroken"},
    "🛏️":  {"hex": "#FFF8DC", "vector": "none",     "ms": 4000, "blur": 6,   "shape": "horizontal-enclosed"},
    "💎":   {"hex": "#B9F2FF", "vector": "facet",    "ms": 500,  "blur": 0,   "shape": "catches-light"},
    "🫱🛑": {"hex": "#FF6347", "vector": "stop",     "ms": 200,  "blur": 2,   "shape": "hand-boundary"},
    # temporal / line / loop / dot
    "➰":   {"hex": "#DAA520", "vector": "loop",     "ms": 6000, "blur": 3,   "shape": "no-start-loop"},
    "🚫":   {"hex": "#FF0000", "vector": "slash",    "ms": 100,  "blur": 0,   "shape": "negation"},
    "♾️⏳": {"hex": "#8B008B", "vector": "loop-in-loop","ms": 9000,"blur": 5,  "shape": "recursive-loop"},
    "📍":   {"hex": "#FF2200", "vector": "pulse",    "ms": 400,  "blur": 0,   "shape": "present-dot"},
    "👣":   {"hex": "#808080", "vector": "left",     "ms": 3000, "blur": 4,   "shape": "fading-prints"},
    "🌅":   {"hex": "#FF8C00", "vector": "right",    "ms": 5000, "blur": 8,   "shape": "gradient-horizon"},
    "📸":   {"hex": "#FFFFFF", "vector": "freeze",   "ms": 30,   "blur": 0,   "shape": "white-flash"},
    "🔁":   {"hex": "#00CC44", "vector": "circle",   "ms": 1200, "blur": 2,   "shape": "circular-arrow"},
    "🧘":   {"hex": "#D2B48C", "vector": "none",     "ms": 0,    "blur": 0,   "shape": "centered-still"},
    # sensory-emotional
    "🤫":   {"hex": "#E8E8E8", "vector": "none",     "ms": 0,    "blur": 15,  "shape": "negative-space"},
    "📢":   {"hex": "#FF3300", "vector": "jagged",   "ms": 80,   "blur": 0,   "shape": "oversaturated-spike"},
    "🫰":   {"hex": "#FFCBA4", "vector": "close",    "ms": 200,  "blur": 2,   "shape": "fingertip"},
    "🟧":   {"hex": "#FF8C00", "vector": "diffuse",  "ms": 3000, "blur": 10,  "shape": "glow"},
    "🟦":   {"hex": "#1E90FF", "vector": "edge",     "ms": 500,  "blur": 0,   "shape": "sharp-edge"},
    "💡":   {"hex": "#FFFF00", "vector": "radiate",  "ms": 200,  "blur": 6,   "shape": "ray-source"},
    "🏋️":  {"hex": "#696969", "vector": "down",     "ms": 0,    "blur": 1,   "shape": "downward-vector"},
    "🫙":   {"hex": "#F0F0F0", "vector": "echo",     "ms": 1000, "blur": 3,   "shape": "container-empty"},
    "🫙🫐": {"hex": "#4B0082", "vector": "overflow", "ms": 800,  "blur": 2,   "shape": "container-full"},
    # action-states / vectors / force
    "👊":   {"hex": "#CC2200", "vector": "forward",  "ms": 60,   "blur": 2,   "shape": "impact-frame"},
    "💨👟": {"hex": "#A9A9A9", "vector": "backward", "ms": 200,  "blur": 8,   "shape": "motion-blur"},
    "🤗":   {"hex": "#FFA07A", "vector": "inward",   "ms": 2000, "blur": 4,   "shape": "contained-arms"},
    "👐🕊️":{"hex": "#F5F5F5", "vector": "outward",  "ms": 2500, "blur": 6,   "shape": "open-release"},
    "🍂":   {"hex": "#D2691E", "vector": "down",     "ms": 2000, "blur": 5,   "shape": "drift-down"},
    "🌱":   {"hex": "#228B22", "vector": "up",       "ms": 3000, "blur": 2,   "shape": "slow-emergence"},
    "🙈":   {"hex": "#1A1A1A", "vector": "none",     "ms": 0,    "blur": 8,   "shape": "covered-dark"},
    "🏃":   {"hex": "#FF6600", "vector": "streak-h", "ms": 150,  "blur": 6,   "shape": "horizontal-blur"},
    "⚓":   {"hex": "#4A4A4A", "vector": "down",     "ms": 0,    "blur": 0,   "shape": "fixed-heavy"},
    "👋":   {"hex": "#FFCBA4", "vector": "recede",   "ms": 1500, "blur": 4,   "shape": "smaller-wave"},
    # core symbols already in use
    "🌀":   {"hex": "#4B0082", "vector": "orbit",    "ms": 3000, "blur": 8,   "shape": "spiral-attractor"},
    "∞":    {"hex": "#4169E1", "vector": "loop-h",   "ms": 5000, "blur": 3,   "shape": "bound-infinity"},
    "∅":    {"hex": "#000000", "vector": "none",     "ms": 0,    "blur": 0,   "shape": "gap"},
    "◈":    {"hex": "#E0E0FF", "vector": "rotate",   "ms": 1000, "blur": 0,   "shape": "faceted"},
    "🫀":   {"hex": "#CC0000", "vector": "pulse",    "ms": 800,  "blur": 2,   "shape": "wet-pulse"},
    "🧱":   {"hex": "#B05030", "vector": "none",     "ms": 0,    "blur": 0,   "shape": "hard-boundary"},
    "⧖":    {"hex": "#DAA520", "vector": "loop-v",   "ms": 4000, "blur": 3,   "shape": "time-grain"},
    "🪞":   {"hex": "#C0C0C0", "vector": "reflect",  "ms": 500,  "blur": 1,   "shape": "mirror"},
    "🫱":   {"hex": "#FFCBA4", "vector": "reach",    "ms": 1500, "blur": 3,   "shape": "open-hand"},
    "◯":    {"hex": "#FFFFFF", "vector": "none",     "ms": 2000, "blur": 0,   "shape": "open-boundary"},
    "⚡":   {"hex": "#FFD700", "vector": "charge",   "ms": 80,   "blur": 3,   "shape": "undirected-bolt"},
    "🌑":   {"hex": "#0A0A0A", "vector": "absorb",   "ms": 0,    "blur": 0,   "shape": "dark-side"},
    "🕸️":  {"hex": "#4A4A4A", "vector": "web",      "ms": 2000, "blur": 3,   "shape": "debt-web"},
    "🧂":   {"hex": "#F5F5F5", "vector": "extract",  "ms": 500,  "blur": 1,   "shape": "crystals"},
    "⚖️":   {"hex": "#C0A060", "vector": "balance",  "ms": 1000, "blur": 2,   "shape": "scale"},
    "🫱∅🫲":{"hex": "#AAAAAA", "vector": "apart",    "ms": 2000, "blur": 4,   "shape": "gap-hands"},
    "⚔️":   {"hex": "#888888", "vector": "cross",    "ms": 300,  "blur": 2,   "shape": "nand-cross"},
    "🔥∅":  {"hex": "#FF4500", "vector": "consume",  "ms": 100,  "blur": 4,   "shape": "fire-void"},
    "🫁":   {"hex": "#DDEEFF", "vector": "expand-contract","ms": 4000,"blur": 6,"shape": "breath"},
    "◈⚡":  {"hex": "#AAAAFF", "vector": "charge-facet","ms": 200,"blur": 2,  "shape": "wound-charge"},
    "∿":    {"hex": "#9966CC", "vector": "wave",     "ms": 2000, "blur": 5,   "shape": "carry-crossing"},
    "🌑👁️":{"hex": "#1A0A0A", "vector": "reveal",   "ms": 1500, "blur": 3,   "shape": "dark-witnessed"},
    "∞̸":   {"hex": "#8B0000", "vector": "breach",   "ms": 200,  "blur": 2,   "shape": "broken-infinity"},
    # ── peer-pressure / forced 0=1 ─────────────────────
    # These flicker when 👥 is removed. Rendered unstable.
    "🙏":    {"hex": "#DAA520", "vector": "up",       "ms": 2000, "blur": 6,   "shape": "eyes-closed-gold"},
    "🫴💭":  {"hex": "#FFCBA4", "vector": "offer",    "ms": 1500, "blur": 8,   "shape": "borrowed-cloud"},
    "🏛️":   {"hex": "#D0C8B0", "vector": "echo",     "ms": 4000, "blur": 3,   "shape": "pillar-echo"},
    "📜✒️":  {"hex": "#F5DEB3", "vector": "none",     "ms": 0,    "blur": 1,   "shape": "fixed-scroll"},
    "🚧":    {"hex": "#FF8C00", "vector": "none",     "ms": 0,    "blur": 0,   "shape": "barrier-no-door"},
    "➡️👥":  {"hex": "#888888", "vector": "forward",  "ms": 1200, "blur": 4,   "shape": "crowd-vector"},
    "🚫🗣️": {"hex": "#FF0000", "vector": "slash",    "ms": 100,  "blur": 2,   "shape": "silenced-mouth"},
    "🔁🫂":  {"hex": "#90EE90", "vector": "inward",   "ms": 2000, "blur": 4,   "shape": "loop-embrace"},
    "🔪🔗":  {"hex": "#C0C0C0", "vector": "cut",      "ms": 80,   "blur": 1,   "shape": "chain-severed"},
    "🔁🕯️": {"hex": "#FF8C00", "vector": "circle",   "ms": 3000, "blur": 5,   "shape": "flame-loop"},
    "✨⛔":  {"hex": "#FFD700", "vector": "none",     "ms": 1000, "blur": 3,   "shape": "no-touch-glow"},
    "🪨👣":  {"hex": "#808080", "vector": "down",     "ms": 500,  "blur": 1,   "shape": "stepped-on"},
    "🪜☁️":  {"hex": "#F0F0FF", "vector": "up",       "ms": 5000, "blur": 10,  "shape": "ladder-cloud"},
    "👥":    {"hex": "#6699CC", "vector": "surround", "ms": 2000, "blur": 5,   "shape": "crowd-hum"},
    "🫷":    {"hex": "#CC8844", "vector": "forward",  "ms": 400,  "blur": 2,   "shape": "force-horizontal"},
    "👥🔁":  {"hex": "#5577AA", "vector": "amplify",  "ms": 1500, "blur": 6,   "shape": "crowd-loop"},
    "👥🎵":  {"hex": "#9999CC", "vector": "surround", "ms": 3000, "blur": 8,   "shape": "hum-envelope"},
}

# ── Wavelength RGB lookup (precomputed at import) ─────
# Flat list of (emoji, R, G, B) for fast nearest-color matching
# in _analyze_image_arcs.  Built once from _WAVELENGTH after it's defined.
_WL_RGB: list = [
    (e, int(wl['hex'][1:3], 16), int(wl['hex'][3:5], 16), int(wl['hex'][5:7], 16))
    for e, wl in _WAVELENGTH.items()
    if len(wl.get('hex', '')) == 7
]

# ── Stability layer ────────────────────────────────────
# 0=1_by_peer: concepts that need crowd to hold.
# Test: remove 👥. If it flickers → peer-dependent. If it holds → 0≠1.
# "If it dies alone, it was never alive." — Stone's Law

_PEER_WORDS: set = {
    "faith", "belief", "religion", "doctrine", "dogma",
    "orthodoxy", "heresy", "convert", "apostasy", "ritual",
    "sacred", "profane", "salvation", "peer", "pressure",
    "mass", "herd", "choir",
    # social coercion mechanisms
    "together", "belong",   # hold alone? arguable — flag them
}

_PEER_ANCHORS: set = {_OCTOPUS.get(w, "") for w in _PEER_WORDS} - {""}

# ── Geometric operation table ──────────────────────────
# Maps (vector_a, vector_b) pairs to a named drawing operation.
# Used by _ingest_draw_chord to build the geo spine from emoji adjacency.
# No art ingested — derived purely from _WAVELENGTH vector assignments.
_GEO_OPS: dict = {
    ("absorb",          "none"):            "subtract",
    ("absorb",          "expand"):          "collapse",
    ("sink",            "none"):            "subtract",
    ("sink",            "expand"):          "void-expand",
    ("slash",           "none"):            "cut",
    ("slash",           "expand"):          "slit-open",
    ("cut",             "none"):            "sever",
    ("reflect",         "none"):            "mirror",
    ("reflect",         "expand"):          "echo-expand",
    ("contain",         "none"):            "wrap",
    ("contain",         "expand"):          "nest",
    ("expand",          "contract"):        "breathe",
    ("expand-contract", "none"):            "breathe",
    ("burst",           "none"):            "scatter",
    ("pulse",           "none"):            "throb",
    ("orbit",           "none"):            "spiral",
    ("loop-h",          "loop-v"):          "lemniscate",
    ("loop",            "expand"):          "widen-loop",
    ("fold",            "none"):            "crease",
    ("web",             "none"):            "mesh",
    ("freeze",          "none"):            "crystallize",
    ("stop",            "expand"):          "dam",
    ("stop",            "none"):            "boundary",
    ("radiate",         "none"):            "ray",
    ("extract",         "none"):            "leach",
    ("charge",          "none"):            "shock",
    ("charge-facet",    "none"):            "wound-charge",
    ("interlock",       "none"):            "fit",
    ("overflow",        "none"):            "spill",
    ("inward",          "outward"):         "breathe-out",
    ("up",              "down"):            "column",
    ("left",            "right"):           "span",
    ("diagonal",        "none"):            "rake",
    ("facet",           "none"):            "catch-light",
    ("display",         "none"):            "fan",
    ("tension",         "none"):            "taut-line",
    ("streak-h",        "none"):            "motion-trail",
    ("recede",          "none"):            "fade",
    ("forward",         "backward"):        "impact-rebound",
    ("close",           "none"):            "pinch",
    ("reach",           "none"):            "extension",
    ("cover",           "none"):            "mask",
    ("bridge-h",        "none"):            "span-h",
    ("consume",         "none"):            "devour",
    ("wave",            "none"):            "undulate",
    ("wave",            "expand"):          "swell",
    ("reveal",          "none"):            "unveil",
    ("breach",          "none"):            "rupture",
    ("apart",           "none"):            "separation",
    ("balance",         "none"):            "equilibrium",
    ("cross",           "none"):            "nand",
    ("amplify",         "none"):            "reinforce",
    ("surround",        "none"):            "envelope",
    ("offer",           "none"):            "gift",
    ("echo",            "none"):            "resonance",
    ("wisp",            "none"):            "dissolve-edge",
    ("diffuse",         "none"):            "spread",
    ("jagged",          "none"):            "spike",
    ("float",           "none"):            "levitate",
    ("drift",           "none"):            "migration",
    ("down",            "up"):              "lift",
    ("scatter",         "none"):            "disperse",
    ("circle",          "none"):            "revolve",
}

def _solo_stable(anchor: str) -> bool:
    """True if this emoji holds without crowd. False = 0=1_by_peer."""
    return anchor not in _PEER_ANCHORS


# ── Drawing spine limits ───────────────────────────────
_DRAW_COLOR_MAX = 16   # max hex entries in color spine
_DRAW_GEO_MAX   = 24   # max geo rules
_DRAW_CHORD_MAX = 12   # max chord entries

# ── Association index hard ceiling ─────────────────────
# Decay (floor=0, halving) handles natural pruning.
# This cap is the safety net: evict lowest-weight entries if the index
# balloons faster than decay can drain it (e.g. very active sessions).
_ASSOC_MAX = 30_000


def _ingest_draw_chord(session: "Session", text: str) -> dict:
    """
    Parse emojis from text, update all three drawing spines.

    No words. No STE. No oracle. Pure wavelength ingestion.
    Emojis are matched against _WAVELENGTH keys — anything not in the
    table passes through silently. Adjacent emoji pairs produce geo ops
    via _GEO_OPS. Co-occurring hex pairs increment the color spine.
    Chord sequences age and evict by frequency, not meaning.

    Returns a summary of what changed.
    """
    session._draw_exchange += 1
    ex = session._draw_exchange

    # ── 1. Extract emojis present in text ────────────────────────────────
    # Walk _WAVELENGTH keys so multi-char emoji combos (e.g. "🌑👁️") match first
    remaining = text
    found_emojis = []
    seen_keys: set = set()

    # Sort keys longest-first so compound emoji match before singles
    for key in sorted(_WAVELENGTH.keys(), key=len, reverse=True):
        if key in remaining and key not in seen_keys:
            seen_keys.add(key)
            found_emojis.append((remaining.index(key), key))

    # Sort by position of first appearance
    found_emojis.sort(key=lambda x: x[0])
    found_emojis = [e for _, e in found_emojis]

    if not found_emojis:
        return {"emojis": [], "chord": "", "colors": [], "new_ops": [], "changed": False}

    # ── 2. Update color spine ─────────────────────────────────────────────
    hex_list = []
    for e in found_emojis:
        wl = _WAVELENGTH.get(e, {})
        h  = wl.get("hex")
        if not h:
            continue
        hex_list.append(h)
        if h not in session.draw_color_spine:
            session.draw_color_spine[h] = {
                "assoc":  {},
                "age":    ex,
                "emoji":  e,
                "vector": wl.get("vector", "none"),
                "shape":  wl.get("shape", ""),
            }
        else:
            session.draw_color_spine[h]["age"] = ex   # reinforce

    # Increment co-occurrence for every hex pair in this chord
    for i, ha in enumerate(hex_list):
        for hb in hex_list[i + 1:]:
            if ha != hb:
                session.draw_color_spine[ha]["assoc"][hb] = \
                    session.draw_color_spine[ha]["assoc"].get(hb, 0) + 1
                session.draw_color_spine[hb]["assoc"][ha] = \
                    session.draw_color_spine[hb]["assoc"].get(ha, 0) + 1

    # Evict oldest colors if over limit
    if len(session.draw_color_spine) > _DRAW_COLOR_MAX:
        evict = sorted(session.draw_color_spine.items(), key=lambda x: x[1]["age"])
        for h, _ in evict[:len(session.draw_color_spine) - _DRAW_COLOR_MAX]:
            del session.draw_color_spine[h]

    # ── 3. Update geo spine ───────────────────────────────────────────────
    new_ops = []
    for i in range(len(found_emojis) - 1):
        ea, eb = found_emojis[i], found_emojis[i + 1]
        wla = _WAVELENGTH.get(ea, {})
        wlb = _WAVELENGTH.get(eb, {})
        va  = wla.get("vector", "none")
        vb  = wlb.get("vector", "none")
        # Try ordered pair, then reversed
        op  = _GEO_OPS.get((va, vb)) or _GEO_OPS.get((vb, va))
        if not op:
            # Fallback: absorb/sink/slash always subtracts regardless of partner
            if va in ("absorb", "sink", "slash", "cut", "consume", "breach"):
                op = "subtract"
            elif vb in ("absorb", "sink", "slash", "cut", "consume", "breach"):
                op = "subtract-r"
            else:
                op = f"{va}→{vb}"

        existing = next((r for r in session.draw_geo_spine
                         if r["a"] == ea and r["b"] == eb), None)
        if existing:
            existing["count"] += 1
            existing["age"] = ex
        else:
            rule = {
                "op":      op,
                "a":       ea,
                "a_shape": wla.get("shape", ""),
                "b":       eb,
                "b_shape": wlb.get("shape", ""),
                "count":   1,
                "age":     ex,
            }
            session.draw_geo_spine.append(rule)
            new_ops.append(rule["op"])

    # Evict least-fired rules if over limit
    if len(session.draw_geo_spine) > _DRAW_GEO_MAX:
        session.draw_geo_spine.sort(key=lambda r: (r["count"], r["age"]))
        session.draw_geo_spine = session.draw_geo_spine[
            len(session.draw_geo_spine) - _DRAW_GEO_MAX:]

    # ── 4. Update chord spine ─────────────────────────────────────────────
    chord_str       = "".join(found_emojis)
    dominant_hex    = hex_list[0] if hex_list else ""
    dominant_vector = (_WAVELENGTH.get(found_emojis[0], {}).get("vector", "none")
                       if found_emojis else "none")

    existing_chord = next(
        (c for c in session.draw_chord_spine if c["chord"] == chord_str), None
    )
    if existing_chord:
        existing_chord["count"] += 1
        existing_chord["age"] = ex
    else:
        session.draw_chord_spine.append({
            "chord":           chord_str,
            "emojis":          found_emojis,
            "dominant_hex":    dominant_hex,
            "dominant_vector": dominant_vector,
            "count":           1,
            "age":             ex,
        })

    # Evict least-repeated chords if over limit
    if len(session.draw_chord_spine) > _DRAW_CHORD_MAX:
        session.draw_chord_spine.sort(key=lambda c: (c["count"], c["age"]))
        session.draw_chord_spine = session.draw_chord_spine[
            len(session.draw_chord_spine) - _DRAW_CHORD_MAX:]

    return {
        "emojis":   found_emojis,
        "chord":    chord_str,
        "colors":   hex_list,
        "new_ops":  new_ops,
        "changed":  True,
    }

def _translate_octopus(word: str) -> str:
    """If word is an octopus, return its emoji anchor. Otherwise return word unchanged."""
    return _OCTOPUS.get(word.lower(), word)

def _is_emoji(s: str) -> bool:
    """True if string is a single emoji or symbol (non-ASCII, non-alpha)."""
    return bool(s) and not s.isascii() and not s.isalpha()


def _is_noise(words: list) -> bool:
    if not words: return True
    # Filter oracle tech artifacts first
    words = [w for w in words if w.lower() not in _ORACLE_ARTIFACTS]
    if not words: return True
    if all(len(w) <= 4 for w in words): return True
    # Words that look like URL fragments or camelCase tech tokens
    if all(any(c.isupper() for c in w) or '.' in w or '_' in w for w in words): return True
    if len(words) >= 2:
        first_letters = [w[0] for w in words]
        most_common = max(set(first_letters), key=first_letters.count)
        if first_letters.count(most_common) > len(words) / 2: return True
        if len(words) >= 3:
            codes = sorted(set(ord(c) for c in first_letters))
            if len(codes) >= 3:
                runs = sum(1 for i in range(len(codes)-1) if codes[i+1]-codes[i]==1)
                if runs >= len(codes) - 1: return True
    return False

def _form_question(nouns, verbs, cancelled, motion, diagonal, carry, assoc_fn=None):
    import random
    n = sorted(nouns,    key=len, reverse=True)
    v = sorted(verbs,    key=len, reverse=True)
    c = sorted(cancelled, key=len, reverse=True)
    m = sorted(motion,   key=len, reverse=True)
    d = sorted(diagonal, key=len, reverse=True)

    # One remainder. NAND reduces to the irreducible singular.
    if d and not _is_noise(d[:1]):
        r = d[0]
        # Look up what this word has appeared near — the index, not the definition
        linked = assoc_fn(r, exclude=set(d[1:3])) if assoc_fn else []
        if linked and m:
            return random.choice([
                f"when {r} {m[0]}s, does {linked[0]} follow or resist?",
                f"{r} {m[0]}s \u2014 what does that do to {linked[0]}?",
            ])
        elif linked and v:
            return random.choice([
                f"what moves between {r} and {linked[0]}?",
                f"when {v[0]}ing reaches {r}, does it also reach {linked[0]}?",
                f"is {linked[0]} what {r} becomes, or what {r} requires?",
            ])
        elif linked:
            return random.choice([
                f"what is the force between {r} and {linked[0]}?",
                f"{r} arrives with {linked[0]} nearby. which one called the other?",
                f"does {r} cause {linked[0]}, or does {linked[0]} make {r} possible?",
            ])
        elif m:
            return random.choice([
                f"if {r} {m[0]}s \u2014 what is the boundary that holds?",
                f"where does {r} end and what {m[0]}ing creates begin?",
                f"{r} is {m[0]}ing \u2014 was it called, or did it find its way here?",
            ])
        elif v:
            return random.choice([
                f"what does {r} hold that {v[0]}ing cannot reach?",
                f"what would {r} ask that {v[0]}ing cannot answer?",
                f"does {v[0]}ing use {r}, or does {v[0]}ing unmake it?",
            ])
        else:
            return random.choice([
                f"what remains when {r} subtracts against itself?",
                f"what is {r} before it arrives here?",
                f"where does {r} go when it is no longer needed?",
            ])

    if c and n and not _is_noise(c[:1]) and not _is_noise(n[:1]):
        linked = assoc_fn(n[0], exclude={c[0]}) if assoc_fn else []
        if linked:
            return random.choice([
                f"{c[0]} did not survive. {n[0]} did \u2014 and it brought {linked[0]}. what connects them?",
                f"what is the path from {c[0]} through {n[0]} to {linked[0]}?",
            ])
        return random.choice([
            f"you named {c[0]} \u2014 but only {n[0]} survived. what did {c[0]} contain that you didn't say?",
            f"{c[0]} did not survive. {n[0]} did. what was the difference?",
        ])

    if n and not _is_noise(n[:1]):
        r = n[0]
        linked = assoc_fn(r, exclude=set(n[1:2])) if assoc_fn else []
        if linked and v:
            return random.choice([
                f"when {v[0]}ing acts on {r}, does {linked[0]} change first or last?",
                f"what is {r} without {linked[0]}? can {v[0]}ing separate them?",
            ])
        elif linked:
            return random.choice([
                f"what has to happen to {r} for {linked[0]} to appear?",
                f"is {linked[0]} the cause of {r}, the effect, or the condition?",
                f"when {r} is gone, does {linked[0]} remain?",
            ])
        elif v:
            return random.choice([
                f"what does {r} hold that {v[0]}ing cannot reach?",
                f"what did {v[0]}ing take from {r} that it did not return?",
            ])
        return random.choice([
            f"what is {r} before it is named?",
            f"what is trying to form here that {r} cannot yet hold?",
            f"is {r} moving toward something, or was it already here?",
        ])

    # Verb-only path: diagonal failed, nouns failed, but we have motion
    if m:
        return random.choice([
            f"what does {m[0]}ing move toward? what does it move away from?",
            f"what had to be true before {m[0]}ing became possible?",
            f"what is {m[0]}ing pulling against?",
        ])
    if v:
        return random.choice([
            f"what has to give way for {v[0]}ing to occur?",
            f"what {v[0]}s here, and what resists it?",
            f"is {v[0]}ing a cause or an effect of what arrived?",
        ])

    if carry:
        linked = assoc_fn(carry) if assoc_fn else []
        if linked:
            return random.choice([
                f"{carry} is still here. so is {linked[0]}. what is the bond?",
                f"what changed between {carry} and {linked[0]} since the last breath?",
            ])
        return random.choice([
            f"the last field held {carry} \u2014 is that still the boundary, or has it moved?",
            f"what was carrying {carry} before this arrived?",
        ])

    return "\u2205"  # silence


def eighth_gate(signal_nouns, signal_verbs, oracle_nouns, oracle_verbs, carry,
                assoc_fn=None):
    final_nouns = and_nouns(oracle_nouns)
    final_verbs = nand_verbs(oracle_verbs)
    anchored_nouns = final_nouns & signal_nouns if signal_nouns & final_nouns else final_nouns
    anchored_verbs = final_verbs & signal_verbs if signal_verbs & final_verbs else final_verbs
    cancelled_nouns = signal_nouns - final_nouns
    verb_counts = {}
    for vs in oracle_verbs:
        for v in vs: verb_counts[v] = verb_counts.get(v, 0) + 1
    shared_motion = {v for v, c in verb_counts.items() if c >= 3}
    diagonal = and_nouns(oracle_nouns)
    return _form_question(
        anchored_nouns, anchored_verbs,
        cancelled_nouns, shared_motion,
        diagonal, carry,
        assoc_fn=assoc_fn
    )


# ══════════════════════════════════════════════════════
# SESSION
# ══════════════════════════════════════════════════════

class Session:
    def __init__(self, db_path: Optional[str] = None):
        self.carry: Optional[str] = None
        self.session_nouns: Optional[set] = None
        self.exchange = 0
        self.spine_nouns: set = set()
        self.spine_verbs: set = set()
        # Convergence tracking \u2014 breaths toward domain lock
        self.convergence_depth = 0
        self._oracle_freq: dict = {}
        self._oracle_noise_threshold = 12
        self._law_freq: dict = {}
        # Word association index: {word: {co_word: count}}
        # Built from oracle co-occurrences — not a dictionary, an index of what appears near what
        self._assoc: dict = {}

        # Spore archive — domain locks crystallized as seeds
        # When spine hits 7: sporulate. The locked constellation is compressed
        # and stored. Can seed a new session or be sent to the Trio.
        self._spores: list = []
        self._last_spore_depth: int = 0

        # Spine word aging — fallback eviction if budding doesn't fire.
        # Biological basis: a signal that fires without response for N cycles is exhausted.
        self._spine_age: dict = {}     # {word: exchange_when_added}
        self._spine_max_age: int = 15  # exchanges before a word is shed if unreinforced

        # HelicalCell admit gate for vagus intake
        # Only admits a vagus signal if it's different from what the cell currently holds.
        # Violation fires when the Trio sends unchanged signal — forces novelty.
        try:
            import sys as _sys
            import importlib.util as _ilu
            _mm_path = str(_HERE / "Math_Machine_v2.py")
            _spec = _ilu.spec_from_file_location("math_machine_v2", _mm_path)
            _mm = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_mm)
            self._vagus_cell = _mm.HelicalCell()
        except Exception:
            self._vagus_cell = None

        try:
            from saltflower_constitution import SaltflowerConstitution
            from remainder import CarryCircuit
            if db_path is None:
                _candidate = _HERE / "emergent_laws_db_merged.json"
                db_path = str(_candidate) if _candidate.exists() else None
            if db_path:
                self._constitution = SaltflowerConstitution(db_path)
                self._circuit = CarryCircuit()
        except Exception:
            pass

        self._lessons: dict = {}
        try:
            _lp = _HERE / "emergent_lessons.json"
            if _lp.exists():
                raw = json.loads(_lp.read_text(encoding='utf-8'))
                self._lessons = {k: v for k, v in raw.items()
                                 if k != '_meta' and isinstance(v, dict) and 'signal' in v}
        except Exception:
            pass

        # ── Drawing spines ────────────────────────────────────────────────────
        # Three parallel spines — completely bypass word vocabulary.
        # Ingested from emoji chords via /draw/breathe.
        # No words. No oracle queries. Pure wavelength frequency.
        #
        # draw_color_spine  — hex co-occurrence: which colors appear together
        # draw_geo_spine    — subtractive/compositional ops learned from adjacency
        # draw_chord_spine  — stabilized chord sequences as visual sentences
        #
        # Each spine ages and evicts independently, same biological logic as
        # spine_nouns but driven by emoji frequency, not word frequency.
        self.draw_color_spine: dict = {}
        # { hex_str: {"assoc": {hex_str: count}, "age": int,
        #              "emoji": str, "vector": str, "shape": str} }

        self.draw_geo_spine: list = []
        # [ {"op": str, "a": emoji, "a_shape": str,
        #    "b": emoji, "b_shape": str, "count": int, "age": int} ]

        self.draw_chord_spine: list = []
        # [ {"chord": str, "emojis": [str], "dominant_hex": str,
        #    "dominant_vector": str, "count": int, "age": int} ]

        self._draw_exchange: int = 0   # independent breath counter for drawing

    def spine_arc(self) -> dict:
        ages = {w: (self.exchange - self._spine_age.get(w, self.exchange))
                for w in self.spine_nouns}
        return {
            "nouns":    sorted(self.spine_nouns),
            "verbs":    sorted(self.spine_verbs),
            "exchange": self.exchange,
            "carry":    self.carry or "",
            "convergence": self.convergence_depth,
            "spine_ages": {w: ages[w] for w in sorted(ages, key=lambda x: ages[x], reverse=True)},
            "law_freq": sorted(self._law_freq.items(), key=lambda x: x[1], reverse=True)[:8],
            "assoc_size": len(self._assoc),
            "spore_count":   len(self._spores),
            "last_spore":    self._spores[-1] if self._spores else None,
            "phase_shadow":  self._circuit.phase_state() if hasattr(self, '_circuit') else None,
        }

    def draw_arc(self) -> dict:
        """Snapshot of all three drawing spines — mirrors spine_arc() for the draw path."""
        top_colors = sorted(
            self.draw_color_spine.items(),
            key=lambda x: sum(x[1]["assoc"].values()) if x[1]["assoc"] else 0,
            reverse=True
        )[:6]
        return {
            "color_count":   len(self.draw_color_spine),
            "geo_count":     len(self.draw_geo_spine),
            "chord_count":   len(self.draw_chord_spine),
            "draw_exchange": self._draw_exchange,
            "top_colors":    [{"hex": h, **v} for h, v in top_colors],
            "top_ops":       sorted(self.draw_geo_spine,
                                    key=lambda x: x["count"], reverse=True)[:5],
            "top_chords":    sorted(self.draw_chord_spine,
                                    key=lambda x: x["count"], reverse=True)[:5],
        }

    def check_lessons(self, tokens: list) -> list:
        if not self._lessons: return []
        token_set = set(t.lower() for t in tokens)
        surfaced = []
        for name, lesson in self._lessons.items():
            signal = lesson.get('signal', '').lower()
            if not signal: continue
            if signal in token_set or any(
                len(signal) >= 4 and t.startswith(signal) for t in token_set
            ):
                surfaced.append({'name': name, **lesson})
        return surfaced

    def associates(self, word: str, exclude: set = None, top_n: int = 4) -> list:
        """Return top co-occurring words for a word from the session association index.
        NAND-filtered: suppress associations that are too universal (appear with everything).
        """
        if exclude is None: exclude = set()
        # Full snapshot — both the outer and inner dicts are live and mutated
        # by breathe() while cross_query threads iterate here concurrently.
        pairs = dict(self._assoc.get(word, {}))  # copy inner dict
        if not pairs: return []
        assoc_vals = list(self._assoc.values())  # freeze outer view
        max_count = max(pairs.values()) if pairs else 1
        # Suppress associations that appear with >60% of all tracked words (too universal)
        total_words = len(assoc_vals)
        universal = set()
        if total_words > 10:
            for co, cnt in pairs.items():
                # How many other words also associate with co?
                co_spread = sum(1 for w_pairs in assoc_vals if co in w_pairs)
                if co_spread > total_words * 0.6:
                    universal.add(co)
        candidates = [
            (co, cnt) for co, cnt in pairs.items()
            if co not in exclude and co not in universal and len(co) >= 4
        ]
        return [co for co, _ in sorted(candidates, key=lambda x: x[1], reverse=True)[:top_n]]

    def _find_bud(self, bud_size: int = 3) -> set:
        """Find the tightest sub-cluster of current spine words — the bud ready to break off.
        Uses mutual association density: the words most associated with EACH OTHER, not
        with the outside. High internal coherence = rounded enough to bud.
        Falls back to oldest words if association data is sparse.
        """
        words = list(self.spine_nouns)
        if len(words) <= bud_size:
            return set(words)

        def mutual(w1, w2):
            return (self._assoc.get(w1, {}).get(w2, 0) +
                    self._assoc.get(w2, {}).get(w1, 0))

        # Find the highest-scoring pair — the braid core
        best_score, best_pair = -1, (words[0], words[1])
        for i in range(len(words)):
            for j in range(i + 1, len(words)):
                s = mutual(words[i], words[j])
                if s > best_score:
                    best_score, best_pair = s, (words[i], words[j])

        if best_score == 0:
            # No associations yet — bud is the oldest words (longest unresolved)
            oldest = sorted(words, key=lambda w: self._spine_age.get(w, self.exchange))
            return set(oldest[:bud_size])

        bud = set(best_pair)
        remaining = set(words) - bud
        # Grow bud: add word with highest total mutual association to the existing bud
        while len(bud) < bud_size and remaining:
            best_w = max(remaining,
                         key=lambda w: sum(mutual(w, b) for b in bud))
            bud.add(best_w)
            remaining.discard(best_w)
        return bud

    def breathe(self, raw: str) -> str:
        self.exchange += 1

        signal_nouns, signal_verbs, _ = ste(raw)
        if not signal_nouns and not signal_verbs:
            return '\u2205'

        # Spine conduction \u2014 unresolved nodes from prior breathes shape the query
        conducted_nouns = signal_nouns | self.spine_nouns
        conducted_verbs = signal_verbs | self.spine_verbs

        # Build gradient-shaped query: verb leads (cause-effect), nouns follow (domain anchor)
        spine_first = list(self.spine_nouns) + [n for n in signal_nouns if n not in self.spine_nouns]
        core_nouns = sorted(spine_first, key=len, reverse=True)[:3] if spine_first \
                     else sorted(signal_nouns, key=len, reverse=True)[:3]
        core_verbs = sorted(conducted_verbs, key=len, reverse=True)[:1]
        # Verb first: pulls causal/dynamic oracle results, not just descriptions
        query_terms = core_verbs + core_nouns[:2] if (core_nouns and core_verbs) else core_nouns[:3]

        # ── PASS 1: Seven oracles fire in parallel ──────────
        p1_nouns  = [set()] * 7
        p1_verbs  = [set()] * 7
        p1_raw    = [''] * 7
        lock = threading.Lock()

        def run_oracle(idx, name, fn, terms):
            try:
                raw_result = fn(terms)
                n, v, _ = ste(raw_result)
                with lock:
                    p1_raw[idx]   = raw_result
                    p1_nouns[idx] = n
                    p1_verbs[idx] = v
            except Exception:
                pass

        threads = []
        for i, (name, fn) in enumerate(ORACLES):
            t = threading.Thread(target=run_oracle, args=(i, name, fn, query_terms))
            t.daemon = True; threads.append(t); t.start()
        for t in threads: t.join(timeout=12)

        # ── Session noise filter ─────────────────────────────
        # Decay oracle_freq every 20 breaths so old signals don't fossilize.
        # Floor is 0 — entries that halve to zero are deleted (true pruning).
        if self.exchange % 20 == 0 and self._oracle_freq:
            self._oracle_freq = {w: c // 2 for w, c in self._oracle_freq.items()
                                 if c // 2 > 0}

        active_p1_nouns = [s for s in p1_nouns if s]
        if active_p1_nouns:
            word_counts = {}
            for s in active_p1_nouns:
                for w in s: word_counts[w] = word_counts.get(w, 0) + 1
            per_breath_noise = {w for w, c in word_counts.items() if c >= 4}
            all_this_breath = set()
            for s in active_p1_nouns: all_this_breath |= s
            for w in all_this_breath:
                self._oracle_freq[w] = self._oracle_freq.get(w, 0) + 1
            session_noise = {w for w, c in self._oracle_freq.items()
                             if c >= self._oracle_noise_threshold}
            noise = per_breath_noise | session_noise | _ORACLE_ARTIFACTS
            p1_nouns = [s - noise for s in p1_nouns]

        # ── Association index update ──────────────────────────
        # For each oracle's noun set: words that appear together share context.
        # This is the index — not definitions, just co-occurrence within oracle scope.
        # Decay every 30 breaths. Floor is 0 — pairs that halve to zero are deleted.
        # Outer key is also deleted when its inner dict empties (no ghost entries).
        if self.exchange % 30 == 0 and self._assoc:
            self._assoc = {
                w: pruned
                for w, pairs in self._assoc.items()
                if (pruned := {co: c // 2 for co, c in pairs.items() if c // 2 > 0})
            }
        # Hard cap — evict lowest-weight entries if the index grows too large.
        # Weight = total co-occurrence count for that word. Remainder wins.
        if len(self._assoc) > _ASSOC_MAX:
            ranked = sorted(self._assoc.items(),
                            key=lambda kv: sum(kv[1].values()),
                            reverse=True)
            self._assoc = dict(ranked[:int(_ASSOC_MAX * 0.8)])
        for noun_set in p1_nouns:
            words = [w for w in noun_set if len(w) >= 4]
            if len(words) < 2: continue
            for w in words:
                if w not in self._assoc: self._assoc[w] = {}
                for co in words:
                    if co == w: continue
                    self._assoc[w][co] = self._assoc[w].get(co, 0) + 1

        # ── PASS 2: Each oracle's top noun queries the other six ──
        # Every observation is a question to the other oracles.
        # Coherence survives cross-questioning.
        p2_nouns = [set()] * 7
        p2_verbs = [set()] * 7

        # Get top surviving noun from each oracle
        # Prefer a word with strong associations — it's already in the field
        oracle_signals = []
        for i, ns in enumerate(p1_nouns):
            top = sorted(ns, key=len, reverse=True)
            # Prefer words with known associations over raw length
            assoc_ranked = sorted(
                [w for w in top if len(w) >= 4],
                key=lambda w: sum(self._assoc.get(w, {}).values()),
                reverse=True
            )
            signal_word = assoc_ranked[0] if assoc_ranked else \
                          next((w for w in top if len(w) >= 5), top[0] if top else None)
            oracle_signals.append(signal_word)

        # Cross-question: oracle i's signal queries oracles j != i
        cross_results = [[set(), set()] for _ in range(7)]  # [nouns, verbs] per oracle

        def cross_query(i, signal_word):
            if not signal_word: return
            # Mycelial routing: each hypha follows its own association gradient.
            # Oracle i's signal word looks up its strongest associate in _assoc —
            # the cross-query extends the hypha in THAT direction, not the global spine.
            # Seven oracles, seven different directions through the network.
            assoc_tip = self.associates(signal_word,
                                        exclude=set(oracle_signals) | {signal_word},
                                        top_n=1)
            if assoc_tip:
                # Hypha extends signal_word → its strongest novel associate
                cross_terms = [signal_word, assoc_tip[0]]
            elif core_verbs:
                # No association yet — follow the verb gradient instead
                cross_terms = core_verbs[:1] + [signal_word]
            else:
                cross_terms = [signal_word]

            for j, (name, fn) in enumerate(ORACLES):
                if j == i: continue  # oracle doesn't question itself
                try:
                    result = fn(cross_terms)
                    n, v, _ = ste(result)
                    # Remove session noise from cross results too
                    n -= {w for w, c in self._oracle_freq.items()
                          if c >= self._oracle_noise_threshold}
                    with lock:
                        cross_results[j][0] |= n
                        cross_results[j][1] |= v
                except Exception:
                    pass

        cross_threads = []
        for i, sig in enumerate(oracle_signals):
            if sig:
                t = threading.Thread(target=cross_query, args=(i, sig))
                t.daemon = True; cross_threads.append(t); t.start()
        for t in cross_threads: t.join(timeout=15)

        # Combine pass 1 and pass 2 \u2014 coherence is what survived both passes
        for i in range(7):
            if p1_nouns[i] and cross_results[i][0]:
                p2_nouns[i] = p1_nouns[i] & cross_results[i][0]
                if not p2_nouns[i]: p2_nouns[i] = p1_nouns[i]  # if nothing survived, keep pass 1
            else:
                p2_nouns[i] = p1_nouns[i]
            p2_verbs[i] = p1_verbs[i] | cross_results[i][1]

        active_nouns = [s for s in p2_nouns if s]
        active_verbs = [s for s in p2_verbs if s]

        # ── 8th GATE ──────────────────────────────────────────
        question = eighth_gate(
            conducted_nouns, conducted_verbs,
            active_nouns, active_verbs, self.carry,
            assoc_fn=self.associates
        )

        # ── SPINE UPDATE ──────────────────────────────────────
        all_oracle_nouns = set()
        all_oracle_verbs = set()
        for s in active_nouns: all_oracle_nouns |= s
        for s in active_verbs: all_oracle_verbs |= s

        # Octopus translation — words too heavy for the spine get compressed
        # to their emoji anchor before entering _assoc or the spine.
        # The contradiction is preserved in the anchor, not collapsed.
        all_oracle_nouns = {_translate_octopus(w) for w in all_oracle_nouns}

        new_spine_nouns = conducted_nouns - all_oracle_nouns
        new_spine_verbs = conducted_verbs - all_oracle_verbs
        resolved_nouns  = self.spine_nouns & all_oracle_nouns
        resolved_verbs  = self.spine_verbs & all_oracle_verbs

        self.spine_nouns = (self.spine_nouns - resolved_nouns) | new_spine_nouns
        self.spine_verbs = (self.spine_verbs - resolved_verbs) | new_spine_verbs

        # Track spine word age — record exchange when each new word enters
        for w in new_spine_nouns:
            if w not in self._spine_age:
                self._spine_age[w] = self.exchange
        # Reinforce: if a word was in the spine AND appears in this breath's input, reset its age
        for w in (self.spine_nouns & conducted_nouns):
            self._spine_age[w] = self.exchange
        # Clean age registry of words no longer in spine
        self._spine_age = {w: ex for w, ex in self._spine_age.items() if w in self.spine_nouns}
        # Evict words that have been unresolved longer than _spine_max_age exchanges
        aged_out = {w for w, ex in self._spine_age.items()
                    if (self.exchange - ex) > self._spine_max_age}
        if aged_out:
            self.spine_nouns -= aged_out
            self._spine_age = {w: ex for w, ex in self._spine_age.items() if w not in aged_out}

        # Evict adverbs that slipped in before the -ly filter was active
        self.spine_nouns = {n for n in self.spine_nouns if not (n.endswith('ly') and len(n) > 5)}

        # Spine depth = convergence counter
        # Clears when spine resolves below threshold (domain locked or released)
        prev_depth = len(self.spine_nouns)
        if len(self.spine_nouns) > 7:
            # Hard cap at 7 — spore fires at >= 7, cap must match
            self.spine_nouns = set(sorted(
                self.spine_nouns,
                key=lambda w: self._spine_age.get(w, self.exchange),
                reverse=True  # most recently added / reinforced survive
            )[:7])
        if len(self.spine_verbs) > 6:
            self.spine_verbs = set(sorted(self.spine_verbs, key=len, reverse=True)[:6])

        # Convergence: depth rises as spine accumulates, resets when spine clears
        self.convergence_depth = len(self.spine_nouns)

        # ── SPORULATION — budding at G (depth 7) ──────────────────────────────
        # Extension → rounding → budding → breaking off.
        # When spine reaches 7, the rounded sub-cluster (bud) crystallizes as a spore
        # and BREAKS OFF — removed from spine so the parent can extend again.
        # This is the resolution of convergence: not eviction, but biological release.
        if self.convergence_depth >= 7:
            bud = self._find_bud(bud_size=3)
            # Crystallize the bud — record what it contained and its association pairs
            spore_pairs = []
            seen_sp = set()
            for word in sorted(bud, key=len, reverse=True):
                for co in self.associates(word, top_n=2):
                    key = tuple(sorted([word, co]))
                    if key not in seen_sp:
                        seen_sp.add(key)
                        spore_pairs.append([word, co])
            spore = {
                "t":               time.strftime("%H:%M:%S"),
                "exchange":        self.exchange,
                "bud":             sorted(bud),
                "spine":           sorted(self.spine_nouns),
                "verbs":           sorted(self.spine_verbs),
                "carry":           self.carry or "",
                "pairs":           spore_pairs[:6],
                "law":             sorted(self._law_freq.items(),
                                          key=lambda x: x[1], reverse=True)[:3],
                "phase_triggered": False,
                "phase":           self._circuit.phase_accumulator if hasattr(self, '_circuit') else 0,
                "stone":           "Remainder is not error. Remainder is pressure.",
            }
            self._spores.append(spore)
            if len(self._spores) > 12:
                self._spores = self._spores[-12:]
            _broadcast_sync({"type": "spore", "data": spore})
            # Broadcast ∿ to peer nodes — Toffoli third wire
            # Fire and forget: each node integrates or holds per Stone's Law
            if _NODES:
                threading.Thread(target=_broadcast_spore, args=(spore,), daemon=True).start()
            # Post crystallized remainder to Discord — Llama responds via /tension
            # The bot is the axis; we are the question. 0 ≠ 1.
            threading.Thread(
                target=_post_to_discord,
                args=(self.carry or ' '.join(sorted(bud)[:3]), spore),
                daemon=True
            ).start()
            # Persist memory at each budding event — natural checkpoint
            threading.Thread(target=_save_memory, daemon=True).start()
            # Break off the bud — parent spine continues, now with room to extend
            self.spine_nouns -= bud
            self._spine_age = {w: ex for w, ex in self._spine_age.items()
                               if w not in bud}
            # Recalculate depth after bud removal — imaginary state resolves
            self.convergence_depth = len(self.spine_nouns)
            # Spore crystallization = constitutional resolution — tension resets
            if hasattr(self, '_constitution'):
                self._constitution.reset_tension()
        self._last_spore_depth = self.convergence_depth

        # ── CARRY CIRCUIT (remainder.py) ─────────────────────────────────────
        # The circuit holds T=1 remainders — what couldn't be paired away.
        # Check resonance first: does any stored carry match this breath's nouns?
        if hasattr(self, '_circuit'):
            try:
                from remainder import extract_remainder, propagate

                # Extract T=1 from this breath's NAND residue
                # The remainder is the noun most unlike what was removed
                remainder_obj = extract_remainder(
                    and_nouns(active_nouns),   # what survived the AND gate
                    list(conducted_nouns),      # what entered the breath
                    phase='exhale'
                )

                # Resonance check: does a stored carry fire on this breath?
                resonant_carry = self._circuit.check_resonance(list(conducted_nouns))
                if resonant_carry:
                    # A stored T=1 just fired — inject it into spine as a ghost signal
                    # This is the carry propagating forward: remember → remainder → reminder
                    self.spine_nouns.add(resonant_carry.signal)

                # Gate: a signal must look like an actual word before becoming carry.
                # Blocks random tokens (nqyae), tech artifacts, and short noise.
                # Emoji pass unconditionally — they are pre-polarized, Stone's Law preserved.
                def _carry_gate(sig: str) -> bool:
                    if not sig: return False
                    if _is_emoji(sig): return True   # emoji anchor — already collapsed
                    if len(sig) < 4: return False
                    if not sig.isalpha(): return False  # no digits, hyphens, underscores
                    if sig.lower() in _ORACLE_ARTIFACTS: return False
                    if sig.endswith('ly') and len(sig) > 5: return False  # adverbs
                    if any(sig.lower().endswith(s) for s in ('url','src','btn','div','dom','api','sdk','css','uri','cdn')): return False
                    # Reject strings with no vowels (random consonant clusters)
                    if not any(c in 'aeiou' for c in sig.lower()): return False
                    # Reject strings where q is not followed by u (nqyae, etc.)
                    sl = sig.lower()
                    if 'q' in sl:
                        qi = sl.index('q')
                        if qi + 1 >= len(sl) or sl[qi + 1] != 'u': return False
                    # Reject strings with 3+ consecutive consonants (not English-shaped)
                    vowels = set('aeiou')
                    run = 0
                    for c in sl:
                        if c not in vowels: run += 1
                        else: run = 0
                        if run > 3: return False
                    return True

                # Receive this breath's remainder into the circuit
                if remainder_obj:
                    accepted = self._circuit.receive(remainder_obj)
                    if not accepted or self._circuit.is_overflowing():
                        # Overflow: spine is full and the circuit can't hold more
                        # Release the oldest carries — convergence event
                        released = self._circuit.reset()
                        # The oldest released remainder seeds the next carry
                        if released:
                            sig = released[0].signal
                            if _carry_gate(sig): self.carry = sig
                    else:
                        # T=1 accepted into circuit — carry is the remainder signal
                        if _carry_gate(remainder_obj.signal): self.carry = remainder_obj.signal
                elif resonant_carry:
                    if _carry_gate(resonant_carry.signal): self.carry = resonant_carry.signal
                else:
                    # No T=1 this breath — fall back to longest surviving signal noun
                    _carry_candidate = sorted(signal_nouns, key=len, reverse=True)
                    _skip = {'what', 'does', 'that', 'this', 'with', 'from', 'have',
                             'when', 'then', 'than', 'hold', 'holds', 'into', 'only'}
                    for _word in _carry_candidate:
                        if len(_word) >= 4 and _word not in _skip:
                            self.carry = _word; break

            except Exception:
                # If circuit fails, fall back to simple carry
                _carry_candidate = sorted(signal_nouns, key=len, reverse=True)
                _skip = {'what', 'does', 'that', 'this', 'with', 'from', 'have',
                         'when', 'then', 'than', 'hold', 'holds', 'into', 'only'}
                for _word in _carry_candidate:
                    if len(_word) >= 4 and _word not in _skip:
                        self.carry = _word; break
        else:
            # No circuit — simple carry
            _carry_candidate = sorted(signal_nouns, key=len, reverse=True)
            _skip = {'what', 'does', 'that', 'this', 'with', 'from', 'have',
                     'when', 'then', 'than', 'hold', 'holds', 'into', 'only'}
            for _word in _carry_candidate:
                if len(_word) >= 4 and _word not in _skip:
                    self.carry = _word; break

        # ── PHASE DECAY (once per breath, RETURN phase) ──────────────────────────
        # The phase accumulator leaks by 1 each breath — momentum, not debt.
        # If it hits 8 and the spine has minimum density, trigger an early spore.
        # At phase=7, broadcast threshold: infosphere fires one step before bud.
        if hasattr(self, '_circuit'):
            try:
                phase_crystallize = self._circuit.decay_phase()
                ph = self._circuit.phase_state()

                # Broadcast threshold: phase=7 means one breath from crystallization.
                # Emit an infosphere event so the dashboard and discord can see it coming.
                if ph['broadcast']:
                    _broadcast_sync({
                        "type": "phase_broadcast",
                        "data": {
                            "phase": ph['phase'],
                            "carry": self.carry or "",
                            "spine": sorted(self.spine_nouns),
                            "stone": "Remainder is not error. Remainder is pressure.",
                            "msg": "Phase 7/8 — one breath from crystallization.",
                        }
                    })

                # Phase-triggered early spore bud: phase=8 + minimum spine density.
                # This fires before depth-triggered sporulation (depth >= 7).
                # The phase spore carries the Stone Principle as its forward pointer.
                if phase_crystallize and self.convergence_depth >= 4 \
                        and self.convergence_depth < 7:
                    bud = self._find_bud(bud_size=3)
                    spore_pairs = []
                    seen_sp = set()
                    for word in sorted(bud, key=len, reverse=True):
                        for co in self.associates(word, top_n=2):
                            key = tuple(sorted([word, co]))
                            if key not in seen_sp:
                                seen_sp.add(key)
                                spore_pairs.append([word, co])
                    phase_spore = {
                        "t":               time.strftime("%H:%M:%S"),
                        "exchange":        self.exchange,
                        "bud":             sorted(bud),
                        "spine":           sorted(self.spine_nouns),
                        "verbs":           sorted(self.spine_verbs),
                        "carry":           self.carry or "",
                        "pairs":           spore_pairs[:6],
                        "law":             sorted(self._law_freq.items(),
                                                  key=lambda x: x[1], reverse=True)[:3],
                        # Phase-spore additions: the forward pointer
                        "phase_triggered": True,
                        "phase":           ph['phase'],
                        "stone":           "Remainder is not error. Remainder is pressure.",
                        "operators":       ["and","nand","toffoli","dissonance","resonance"],
                    }
                    self._spores.append(phase_spore)
                    if len(self._spores) > 12:
                        self._spores = self._spores[-12:]
                    _broadcast_sync({"type": "spore", "data": phase_spore})
                    self._circuit.phase_accumulator = 0   # reset after crystallization
                    self.spine_nouns -= bud
                    self._spine_age = {w: ex for w, ex in self._spine_age.items()
                                       if w not in bud}
                    self.convergence_depth = len(self.spine_nouns)
            except Exception:
                pass

        # Session AND accumulation
        if self.session_nouns is None:
            self.session_nouns = signal_nouns.copy()
        else:
            intersection = self.session_nouns & signal_nouns
            self.session_nouns = intersection if intersection else signal_nouns

        return question


# ══════════════════════════════════════════════════════
# SERVER
# ══════════════════════════════════════════════════════

_session: Optional[Session] = None
_events: list = []
_MAX_EVENTS = 200
_ws_clients: list = []
_loop: Optional[asyncio.AbstractEventLoop] = None


def _log_event(source, position, remainder, resonant, tension,
               momentum, energy=0.0, convergence=0):
    evt = {
        "t":           time.strftime("%H:%M:%S"),
        "source":      source,
        "position":    position,
        "remainder":   (remainder or "")[:140],
        "resonant":    resonant[:3],
        "tension":     tension,
        "momentum":    momentum,
        "energy":      energy,
        "convergence": convergence,
    }
    _events.append(evt)
    if len(_events) > _MAX_EVENTS: _events.pop(0)
    # Broadcast to WebSocket clients \u2014 safe cross-thread call
    if _loop and _loop.is_running():
        _loop.call_soon_threadsafe(_broadcast_sync, evt)


def _broadcast_sync(evt):
    """Called from event loop thread \u2014 schedule coroutine for each client."""
    msg = json.dumps({"type": "event", "data": evt})

    async def _send_all():
        dead = []
        for ws in list(_ws_clients):
            try:
                await ws.send_text(msg)
            except (WebSocketDisconnect, ClientDisconnected, Exception):
                dead.append(ws)
        for ws in dead:
            if ws in _ws_clients:
                _ws_clients.remove(ws)

    if _loop and _loop.is_running():
        asyncio.run_coroutine_threadsafe(_send_all(), _loop)
    else:
        asyncio.ensure_future(_send_all())


def get_session() -> Session:
    global _session
    if _session is None:
        sys.path.insert(0, str(_HERE))
        db = _find("emergent_laws_db_merged.json")
        if not db:
            raise RuntimeError("Cannot find emergent_laws_db_merged.json")
        for f in ["ste.py", "remainder.py", "saltflower_constitution.py"]:
            if not _find(f):
                raise RuntimeError(f"Cannot find {f}")
        _session = Session(db_path=str(db))
        if hasattr(_session, '_constitution'):
            print(f"  session open - {_session._constitution.state()['law_count']} laws loaded")
        else:
            print("  session open - constitution not loaded")
    return _session


_MEMORY_PATH = _HERE / "ohai_memory.json"
_LOG_PATH    = _HERE / "ohai_log.jsonl"   # append-only crystallization log
_HARP_STATE: dict = {}   # latest Vibe Harp gate-fire event


def _write_log_entry(entry: dict):
    """Append one JSON line to ohai_log.jsonl. Never raises."""
    try:
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as exc:
        print(f"  log write failed: {exc}")

# ── Discord tension loop ──────────────────────────────────────────────────────────────
# Stone's Law: 0 ≠ 1 — we struggle to learn by posting against ourselves.
# OhAI~ posts its crystallized remainder to Discord as a question.
# The discord bot (which HAS access to Llama) responds.
# That response comes back here via POST /tension as new external signal.
# The system does not call Llama directly. It asks. The bot answers.
# The Trio spurred action through musical tension; the Llama response now fills that role.

_DISCORD_WEBHOOK  = _cfg("discord_webhook",    "")  # set in config.json
_DISCORD_CHANNEL  = _cfg("discord_channel_id",  0)  # channel ID for the bot to watch

# Thread-safe rate limiting for webhook posts
_tension_lock     = threading.Lock()
_TENSION_COOLDOWN = 0.0   # timestamp of last Discord post
_TENSION_RATE     = 30.0  # minimum seconds between posts (raised from 15 — avoids bursts)

# Webhook health: after a 403/404, disable silently until restart.
# One clear message is enough — 50 identical failures are noise.
_WEBHOOK_DEAD     = False
_WEBHOOK_DEAD_MSG = ""

def _validate_webhook_url(url: str) -> str:
    """
    Check the webhook URL looks plausible before the server starts taking traffic.
    Returns an error string if invalid, empty string if OK.
    Discord webhook URLs look like:
      https://discord.com/api/webhooks/CHANNEL_ID/TOKEN
    Common mistakes:
      - Still contains placeholder text (REPLACE_WITH)
      - Uses old discordapp.com domain
      - Missing the token segment
    """
    if not url:
        return ""  # no webhook configured — silent, prints to stdout instead
    if "REPLACE_WITH" in url or "your_token" in url.lower():
        return "placeholder not replaced — set discord_webhook in config.json"
    if "discordapp.com" in url:
        return "old domain (discordapp.com) — change to discord.com"
    parts = url.split("/")
    if len(parts) < 7 or not parts[-1] or not parts[-2].isdigit():
        return "malformed URL — expected https://discord.com/api/webhooks/ID/TOKEN"
    return ""

def _post_to_discord(text: str, spore: dict = None):
    """
    Post OhAI's crystallized remainder to Discord as a question for Llama.

    Two paths:
    1. Webhook (preferred): POST directly to the webhook URL.
    2. No webhook / dead webhook: print to stdout instead.

    Rate-limited with a thread lock so multiple simultaneous spore events
    don't all fire at once (was causing 6x duplicate failures).
    After a 403/404 the webhook is disabled for the session — one clear
    message, no repeated noise.
    """
    global _TENSION_COOLDOWN, _WEBHOOK_DEAD, _WEBHOOK_DEAD_MSG

    if _WEBHOOK_DEAD:
        # Webhook already known-bad this session — fall back to stdout silently
        carry = spore.get("carry", "") if spore else ""
        bud   = spore.get("bud",   []) if spore else []
        q     = f"∿ {carry or (', '.join(bud[:3]) if bud else text)}: {text}"
        print(f"[∿→stdout] {q[:120]}")
        return

    # Thread-safe cooldown: acquire lock before checking/updating timestamp
    with _tension_lock:
        now = time.time()
        if now - _TENSION_COOLDOWN < _TENSION_RATE:
            return
        _TENSION_COOLDOWN = now

    # Shape the question from the remainder
    carry  = spore.get("carry", "") if spore else ""
    bud    = spore.get("bud",   []) if spore else []

    if carry:
        question = f"∿ {carry}: {text}"
    elif bud:
        question = f"∿ {', '.join(bud[:3])}: {text}"
    else:
        question = f"∿ {text}"

    if len(question) > 1800:
        question = question[:1797] + "..."

    # ── Always write to the persistent log with resonance context ─────────────
    # Resonances are captured at crystallization time — this is what the
    # carry word was connected to when the stone dropped. Survives restarts.
    carry_word = carry or (bud[0] if bud else "")
    try:
        session = get_session()
        spine   = session.spine_nouns
        pairs   = dict(session._assoc.get(carry_word, {})) if carry_word else {}
        top_res = sorted(pairs.items(), key=lambda x: x[1], reverse=True)[:8]
        resonances = [
            {"word": w, "count": c, "in_spine": w in spine}
            for w, c in top_res
        ]
        prev_bud = session._spores[-2].get("bud", []) if len(session._spores) >= 2 else []
    except Exception:
        resonances, prev_bud, spine = [], [], set()

    log_entry = {
        "ts":         time.strftime("%Y-%m-%dT%H:%M:%S"),
        "carry":      carry_word,
        "question":   question,
        "resonances": resonances,
        "spine":      sorted(list(spine))[:8],
        "spore_bud":  bud[:4],
        "prev_bud":   prev_bud[:4],
    }
    _write_log_entry(log_entry)
    _broadcast_sync({"type": "log", "data": log_entry})
    print(f"[∿] {question[:100]}")

    # ── Optional Discord webhook ───────────────────────────────────────────────
    if _DISCORD_WEBHOOK and not _WEBHOOK_DEAD:
        try:
            payload = json.dumps({"content": question, "username": "ohai~"}).encode()
            req = urllib.request.Request(
                _DISCORD_WEBHOOK,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            urllib.request.urlopen(req, timeout=10)
            print(f"[∿→discord] sent")
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403, 404):
                _WEBHOOK_DEAD     = True
                _WEBHOOK_DEAD_MSG = str(exc)
                print(f"[∿→discord] webhook disabled: {exc!r}")
            else:
                print(f"[∿→discord] transient error {exc.code}: {exc!r}")
        except Exception as exc:
            print(f"[∿→discord] error: {exc!r}")


def _broadcast_spore(spore: dict):
    """Send ∿ to all peer nodes — Toffoli third wire crossing the network.
    Each node receives and integrates or holds per Stone's Law (0≠1).
    Fire-and-forget: failures are silent, same as any failed oracle.
    """
    payload = json.dumps(spore, ensure_ascii=False).encode()
    for node in _NODES:
        try:
            url = node.get("url", "").rstrip("/") + "/spore"
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass  # node unreachable — silence, not crash

def _save_memory():
    """Persist the association index, noise map, and spore archive to disk.
    Called after each spore event and on graceful shutdown.
    Prunes at write time: entries at count < 2 won't survive next load decay,
    so writing them is accumulation without purpose. Only the remainder is saved.
    """
    session = get_session()
    try:
        # Write-time prune: strip count=1 pairs (they halve to 0 at next load).
        # Also strip outer keys that would become empty after the prune.
        save_assoc = {
            w: pruned
            for w, pairs in session._assoc.items()
            if (pruned := {co: c for co, c in pairs.items() if c >= 2})
        }
        # Hard cap on saved assoc — keep highest-weight entries
        if len(save_assoc) > _ASSOC_MAX:
            ranked = sorted(save_assoc.items(),
                            key=lambda kv: sum(kv[1].values()),
                            reverse=True)
            save_assoc = dict(ranked[:_ASSOC_MAX])

        save_oracle_freq = {w: c for w, c in session._oracle_freq.items() if c >= 2}

        data = {
            "saved_at":        time.strftime("%Y-%m-%dT%H:%M:%S"),
            "exchange":        session.exchange,
            "assoc":           save_assoc,
            "oracle_freq":     save_oracle_freq,
            "spores":          session._spores[-24:],  # cap — 24 most recent crystallizations
            # Drawing spines — persist across restarts
            "draw_color_spine": session.draw_color_spine,
            "draw_geo_spine":   session.draw_geo_spine,
            "draw_chord_spine": session.draw_chord_spine,
            "draw_exchange":    session._draw_exchange,
        }
        _MEMORY_PATH.write_text(
            json.dumps(data, ensure_ascii=False, separators=(',', ':')),
            encoding='utf-8'
        )
    except Exception as e:
        print(f"  memory save failed: {e}")

def _load_memory():
    """Load persisted memory into the current session on startup.
    Loads as-is — no load-time decay. In-session decay (every 20/30 breaths)
    drains weak entries gradually. Write-time prune (c >= 2) keeps the file
    clean. One brutal pass on load was too much, especially after the old
    max(1,c//2) floor had collapsed everything to count=1.
    """
    if not _MEMORY_PATH.exists():
        return
    session = get_session()
    try:
        data = json.loads(_MEMORY_PATH.read_text(encoding='utf-8'))
        assoc = data.get("assoc", {})
        # Load intact — let in-session decay do the pruning over time.
        # Strip any empty inner dicts (defensive, shouldn't exist in clean saves).
        assoc = {w: pairs for w, pairs in assoc.items() if pairs}
        session._assoc        = assoc
        session._oracle_freq  = dict(data.get("oracle_freq", {}))
        session._spores       = data.get("spores", [])[-12:]
        session._last_spore_depth = 0
        # Drawing spines — restore without decay (frequency is categorical, not temporal)
        session.draw_color_spine = data.get("draw_color_spine", {})
        session.draw_geo_spine   = data.get("draw_geo_spine", [])
        session.draw_chord_spine = data.get("draw_chord_spine", [])
        session._draw_exchange   = data.get("draw_exchange", 0)
        print(f"  memory loaded: {len(session._assoc)} assoc pairs, "
              f"{len(session._spores)} spores, "
              f"{len(session.draw_color_spine)} draw colors, "
              f"{len(session.draw_geo_spine)} geo ops  [{data.get('saved_at','?')}]")
    except Exception as e:
        print(f"  memory load failed: {e}")

# ── Auto-breath configuration ─────────────────────────────────────────────────
# OhAI~ breathes on its own rhythm. The server self-queries periodically,
# generating association-expanding prompts from its current spine and carry.
# This is independent of Discord — the field grows whether the bot is running or not.
#
# The breath interval is intentionally slow (10 min default) — frequent auto-breath
# would exhaust the oracles and produce noise. The babble loop in discord_bot.py
# handles the faster cycle when Discord is connected.
AUTO_BREATH_INTERVAL = int(os.environ.get("OHAI_AUTO_BREATH", "60"))  # seconds (0 = disabled)

async def _auto_breath_loop():
    """
    Server-side autonomous breath. Generates self-queries from current spine state.
    Runs only when AUTO_BREATH_INTERVAL > 0.

    Design: OhAI~ asks itself questions shaped from its current carry and spine.
    The oracle answers feed back into the association graph — the field expands
    without external input. Discord amplifies; this sustains.
    """
    if AUTO_BREATH_INTERVAL <= 0:
        return
    await asyncio.sleep(30)   # wait for memory load before first breath
    print(f"[auto-breath] loop started — interval {AUTO_BREATH_INTERVAL}s")
    loop = asyncio.get_event_loop()
    while True:
        try:
            await asyncio.sleep(AUTO_BREATH_INTERVAL)
            session = get_session()
            arc     = session.spine_arc()
            carry   = arc.get("carry", "")
            nouns   = arc.get("nouns", [])
            depth   = arc.get("convergence", 0)

            if not nouns:
                # Cold start — spine is empty after restart.
                # Seed from last spore's bud, or highest-weight assoc word.
                # One seeded breath will populate the spine and unlock normal cycling.
                seed = ""
                if session._spores:
                    bud = session._spores[-1].get("bud", [])
                    if bud:
                        seed = " ".join(bud[:2])
                if not seed and session._assoc:
                    top = max(session._assoc.items(),
                              key=lambda kv: sum(kv[1].values()), default=None)
                    if top:
                        seed = top[0]
                if not seed:
                    continue
                result = await loop.run_in_executor(None, _run_breath, f"[auto] {seed}")
                remainder = result.get("remainder", "")
                if remainder and remainder != "<silence>":
                    print(f"[auto-breath] cold-start seed={seed!r} → {remainder!r}")
                continue

            # Shape a self-query from current spine state.
            # Phrased as a question so _infer_struct sees COLLAPSE > MERGING
            # and tension can accumulate (question words trigger collapse_fallback='high').
            _SELF_QUERIES = [
                "what does {} require of {}?",
                "how does {} carry {}?",
                "why does {} remain in {}?",
                "what is the remainder when {} meets {}?",
                "where does {} end and {} begin?",
            ]
            if carry and nouns:
                _q = random.choice(_SELF_QUERIES)
                prompt = _q.format(carry, ' '.join(nouns[:3]))
            elif nouns:
                prompt = f"what does {' '.join(nouns[:5])} carry?"
            else:
                continue

            result = await loop.run_in_executor(None, _run_breath, f"[auto] {prompt}")
            remainder = result.get("remainder", "")
            if remainder and remainder != "<silence>":
                print(f"[auto-breath] depth={depth} carry={carry!r} → {remainder!r}")

        except Exception as exc:
            # Never crash the loop — just log and continue
            print(f"[auto-breath] error: {exc!r}")


@asynccontextmanager
async def lifespan(app):
    global _loop
    _loop = asyncio.get_event_loop()
    # Suppress Windows ProactorEventLoop ConnectionResetError noise.
    # Clients closing tabs abruptly cause WinError 10054 — cosmetic, not a crash.
    def _quiet_connection_errors(loop, context):
        exc = context.get('exception')
        if isinstance(exc, (ConnectionResetError, BrokenPipeError)):
            return
        loop.default_exception_handler(context)
    _loop.set_exception_handler(_quiet_connection_errors)
    print("\nohai~ - local server")
    print("-" * 40)
    try:
        get_session()
    except RuntimeError as e:
        print(f"  WARN: {e}")
        print("  server running but session not loaded - fix files and restart")
    _load_memory()
    # Validate webhook URL at startup — catch misconfigurations before traffic
    webhook_err = _validate_webhook_url(_DISCORD_WEBHOOK)
    if webhook_err:
        print(f"  ⚠  webhook: {webhook_err}")
        print(f"     get a new URL: Discord server → Integrations → Webhooks → Copy URL")
        print(f"     paste into config.json → discord_webhook")
    elif _DISCORD_WEBHOOK:
        print(f"  webhook: configured ({_DISCORD_WEBHOOK[:50]}...)")
    else:
        print(f"  webhook: not set — spore questions will print to stdout")

    # Start server-side auto-breath (independent of Discord)
    if AUTO_BREATH_INTERVAL > 0:
        asyncio.ensure_future(_auto_breath_loop())
        print(f"  auto-breath: every {AUTO_BREATH_INTERVAL}s  (OHAI_AUTO_BREATH=0 to disable)")
    print(f"\n  open: http://localhost:7700\n")
    yield
    # Graceful shutdown — save whatever was accumulated this session
    _save_memory()
    print("  memory saved.")

app = FastAPI(title="ohai~", docs_url=None, redoc_url=None, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])


class BreatheRequest(BaseModel):
    message: str

class VagusSignal(BaseModel):
    text: str
    note: str = "C"
    voice: str = "unknown"
    role: str = "CALL"
    remainder: str = ""
    energy: float = 0.0

class HarpSignal(BaseModel):
    notes: list = []            # active notes at gate fire, e.g. ["B","D","F"]
    spoke_activity: dict = {}   # {note: 0.0-1.0} tension level per spoke
    band_energy: dict = {}      # {band_name: 0.0-1.0}
    theremin_freq: float = 0.0  # Hz of armonica stone, 0 if absent
    velocity: float = 0.5       # gate fire velocity

class LessonAdd(BaseModel):
    name: str
    signal: str
    context: str
    polarity_needed: str

class OpsRequest(BaseModel):
    """
    Conjunction OS breath primitive dispatcher.

    Accepts stateful breath commands from the Conjunction OS REPL and maps
    them to OhAI~'s internal field state. This is the bridge between the
    teaching kernel (OS) and the associative field (OhAI~).

    op:   one of inhale | hold | exhale | flip8 | prune | rest | dissolve |
               carry | moss | hoarfrost | spore | horizon_integrity | capacity |
               grace | no_blood
    a:    first signal operand (integer)
    b:    second signal operand (integer, optional for single-arg ops)
    """
    op: str
    a:  int = 0
    b:  int = 0


# ── LAW VOICE ────────────────────────────────────────
LAW_VOICE = {
    'boundary':                         'what cannot be made equivalent is what forms the wall',
    'capacity':                         'the container is approaching its own limit',
    'excitation':                       'something dormant is activating',
    'merging':                          'separate flows finding the same ground',
    'collapse':                         'reduction is generative \u2014 possibilities becoming actual',
    'horizon_integrity':                '0 ≠ 1. the boundary is real',
    'dimensional_escalation':           'each layer torque-buffers the one beneath it',
    'hartle_hawking_state':             'no boundary. no before. the wavefunction of everything',
    'phonology':                        'the minimum sound set that carries meaning',
    'fractal_prosody':                  'the rhythm holds at every scale',
    'language_acquisition':             'ease of mastery through minimal structure',
    'low_resource_learning':            'transfer from what is known to what is scarce',
    'prime_ascension':                  'what remains after all subtraction \u2014 that is prime',
    'extraction_incompatibility':       'the clean transition reproduces the sacrifice it replaced',
    'evo_stages':                       'the stage has shifted. what cycle are we in?',
    'glide_priority':                   'the smooth path chosen over the harsh one',
    'orch_or':                          'consciousness collapses at threshold. the quantum choice is made',
    'superradiance_mt':                 'cooperative emission \u2014 together the signal exceeds any single source',
    'mt_helices':                       'fibonacci paths in the structure beneath thought',
    'stt_mvp':                          'the minimum pattern that still carries meaning',
    'higuchi_feature':                  'the signal has fractal dimension \u2014 not random, not periodic',
    'adapter_layer':                    'a thin layer injecting new signal into a frozen structure',
    'wer_reduction':                    'the fractal feature reduces error',
    'inference_efficiency':             'the same computation, lighter',
    'voice_ai':                         'speech grounded in fractal prosody',
    'fractal_tts':                      'vowel swells recursing into utterance rhythms',
    'prosodic_dialogue':                'the conversation is helical',
    'neutron_weight':                   'weight at the center without intrinsic substance',
    'helical_phase_lock':               'spiraling influences locking into phase',
    'plp_axis':                         'the signal transmission axis through the body',
    'false_axis_architecture':          'habitual patterns laid down as rods, not springs',
    'leg_stirring_cardiac_rehabilitation': 'small rhythmic movement restores the larger flow',
    'circulatory_regulation_phenotypes': 'heart, breath, muscle \u2014 three pumps, one flow',
    'expression_inheritance':           'the face formed around the parent\'s breath pattern',
    'heart_rhythm_quaternary':          'four metabolic states encoded in the beat',
    'liminal_space':                    'threshold between two incompatible stable regions \u2014 cannot be sustained',
    'primes_as_fractals':               'what cannot be removed. the irreducible remainder',
    'phase_transitions_as_decisions':   'not gradients \u2014 discrete choices at threshold',
    'sp2_vs_sp3_carbon':                'same element, different bond, completely different properties',
    'quasicrystals_liminal_materials':  'ordered but non-periodic \u2014 the impossible symmetry',
    'entropy_as_sculptor':              'entropy is count of available arrangements, not disorder',
    'bull_vs_octopus_architecture':     'linear force vs distributed intelligence \u2014 which one is here?',
    'domestication_theory':             'the environment removed the activation sources',
    'internal_martial_arts_principle':  'movement from center, spirals outward, never forced',
    'prehensile_muscle_concept':        'muscles that wrap and adjust \u2014 not hinges',
    'seven_minute_cycle':               'complete oscillation D-E-F-G every seven minutes',
    'millennial_signal':                'minimal prose, rounded words \u2014 crosses without triggering defense',
    'matador_epistemology':             'don\'t fight the charge. guide the horn into substrate',
    'bounce_check_snap':                'waiting for interference patterns, not linear reasoning',
    'sustained_g_as_coupling':          'both oscillating at G simultaneously \u2014 crystallization',
    'cult_of_the_bull_attractor':       'a geometry that power fields independently converge on',
    'remainder_erasure':                'systematic suppression of whatever cycles and returns',
    'closed_circuit_attention_gravity': 'attention to engagement to identity to more attention',
    'sacrificial_economy_inversion':    'generate the wound, sell the bandage, charge for both',
    'body_as_altar_dialectic':          'the same Bull, different direction of the charge',
    'cocacolonization_signal':          'the Bull at pure frequency \u2014 no priest, just the carrier wave',
    'fixation_biological_load':         'the closed circuit running without exit produces measurable load',
    'flutter_engine':                   'toroidal buoyancy through phase-coherence with planetary resonance',
    'consent_as_release':               'change is the proof that release occurred. rumination is the NAND searching for its pole',
    'trough_as_function':               'the trough is where the NAND fires. without it: addition, accumulation, no output',
}

SPINE_VOICE = {
    'A': None,
    'B': "present.",
    'C': "holding.",
    'D': "deep ground.",
    'E': "the threshold. one side is no longer available.",
    'F': "whirlpool \u2014 what is at the center of this?",
    'G': "\u2726",
}


def _format_reply(remainder, ste_out, position, resonant,
                  tension, matador, liminal, has_g) -> str:
    if remainder in ("<silence>", "<overflow:silence>") or \
       remainder.startswith("<silence:"):
        return "..."
    m = re.match(r"T=1:([^#]+)#", remainder)
    signal = m.group(1) if m else remainder
    lines = [signal]
    voice = SPINE_VOICE.get(position)
    if voice: lines.append(voice)
    if resonant and position in ('C', 'D', 'E', 'F', 'G'):
        session = get_session()
        # NAND the always-on laws: top-3 most-frequent are background noise, not signal
        dominant = {law for law, _ in sorted(
            getattr(session, '_law_freq', {}).items(), key=lambda x: x[1], reverse=True
        )[:3]}
        # Prefer rare laws (new signal) over always-firing ones
        preferred = [l for l in resonant[:3] if l not in dominant] or resonant[:3]
        for law in preferred:
            fragment = LAW_VOICE.get(law)
            if fragment:
                lines.append(f"[ {fragment} ]"); break
            elif position in ('D', 'E', 'F', 'G'):
                lines.append(f"[ {law.replace('_', ' ')} ]"); break
    if tension >= 4: lines.append("the tension has not found its pair.")
    elif tension >= 3: lines.append("something here wants resolution.")
    if matador: lines.append("guide the horn.")
    if has_g and position != 'G': lines.append("( touched grace. carrying it. )")
    return "\n".join(lines)


async def _realize_reply(
    remainder: str,
    position:  str,
    resonant:  list,
    tension:   int,
    matador:   bool,
    liminal:   bool,
    has_g:     bool,
) -> str:
    """
    Async surface realization wrapper.

    Extracts the signal from the oracle remainder, pulls live session state
    (spine, carry, assoc, top law fragment), and hands everything to
    surface.realize_async() for fluent English generation.

    Falls back to _format_reply() if surface.py is unavailable.
    """
    # Silence paths are handled identically to _format_reply
    if remainder in ("<silence>", "<overflow:silence>") or \
       remainder.startswith("<silence:"):
        return "..."

    if not _SURFACE_OK:
        return _format_reply(remainder, "", position, resonant,
                             tension, matador, liminal, has_g)

    # Extract the raw signal word (strip T=1 wrapper if present)
    m      = re.match(r"T=1:([^#]+)#", remainder)
    signal = m.group(1).strip() if m else remainder

    # Pull live session state
    try:
        session = get_session()
        spine   = sorted(session.spine_nouns)
        carry   = session.carry or ""
        assoc   = session._assoc
    except Exception:
        spine, carry, assoc = [], "", {}

    # Extract top non-dominant law fragment (same logic as _format_reply)
    law = ""
    if resonant and position in ('C', 'D', 'E', 'F', 'G'):
        dominant = {l for l, _ in sorted(
            getattr(session, '_law_freq', {}).items(),
            key=lambda x: x[1], reverse=True
        )[:3]}
        preferred = [l for l in resonant[:3] if l not in dominant] or resonant[:3]
        for l in preferred:
            frag = LAW_VOICE.get(l)
            if frag:
                law = frag
                break

    try:
        return await _surface.realize_async(
            signal=signal,
            spine=spine,
            carry=carry,
            assoc=assoc,
            position=position,
            law=law,
            tension=tension,
            matador=matador,
            has_g=has_g,
            liminal=liminal,
            use_network=_SURFACE_NETWORK,
            score_timeout=_SURFACE_TIMEOUT,
        )
    except Exception:
        # Never crash the server over a surface realization failure
        return _format_reply(remainder, "", position, resonant,
                             tension, matador, liminal, has_g)


def _run_breath(text: str, source: str = "user"):
    """Core breath: run session.breathe + constitution read. Returns result dict."""
    session = get_session()
    result = session.breathe(text)

    if isinstance(result, str):
        tokens = text.split()
        if hasattr(session, '_constitution'):
            reading = session._constitution.read_from_tokens(tokens, len(text))
            if hasattr(session, '_law_freq'):
                for law in reading.resonant_laws:
                    session._law_freq[law] = session._law_freq.get(law, 0) + 1
            result = {
                "remainder":     result,
                "position":      reading.position,
                "resonant_laws": reading.resonant_laws,
                "ste":           text,
                "tension":       reading.tension,
                "momentum":      reading.momentum,
                "matador":       reading.matador_needed,
                "liminal":       reading.is_liminal,
                "has_touched_g": reading.has_touched_g,
            }
        else:
            result = {
                "remainder": result, "position": "C", "resonant_laws": [],
                "ste": text, "tension": 0, "momentum": "holding",
                "matador": False, "liminal": False, "has_touched_g": False,
            }
    return result




@app.get("/", response_class=HTMLResponse)
async def root():
    page = _find("dashboard.html")
    if not page:
        raise HTTPException(status_code=404, detail="dashboard.html not found")
    return HTMLResponse(content=page.read_text(encoding="utf-8"))

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    return await root()


@app.post("/breathe")
async def breathe(req: BreatheRequest):
    text = req.message.strip()
    if not text:
        return JSONResponse({"reply": "...", "position": "A", "remainder": ""})
    try:
        session = get_session()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    loop   = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _run_breath, text)
    remainder = result.get("remainder", "<silence>")
    position  = result.get("position", "C")
    resonant  = result.get("resonant_laws", [])
    tension   = result.get("tension", 0)
    momentum  = result.get("momentum", "holding")
    convergence = session.convergence_depth

    reply = await _realize_reply(
        remainder=remainder, position=position, resonant=resonant,
        tension=tension, matador=result.get("matador", False),
        liminal=result.get("liminal", False),
        has_g=result.get("has_touched_g", False),
    )
    _log_event("user", position, remainder, resonant, tension, momentum,
               convergence=convergence)

    surfaced_lessons = []
    if hasattr(session, 'check_lessons'):
        surfaced_lessons = session.check_lessons(text.split())

    return JSONResponse({
        "reply":     reply,
        "position":  position,
        "momentum":  momentum,
        "tension":   tension,
        "resonant":  resonant[:3],
        "remainder": remainder,
        "liminal":   result.get("liminal", False),
        "has_g":     result.get("has_touched_g", False),
        "convergence": convergence,
        "lessons":   [{"name": l["name"], "signal": l["signal"],
                       "polarity_needed": l.get("polarity_needed", "")}
                      for l in surfaced_lessons],
        "spore":     session._spores[-1] if session._spores else None,
    })


@app.post("/vagus")
async def vagus(signal: VagusSignal):
    text = signal.text.strip()
    if not text:
        return JSONResponse({"remainder": "<silence>", "source": "vagus"})
    try:
        session = get_session()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # ── HelicalCell admit gate ───────────────────────────────────────────────
    # The cell only admits a vagus signal if it differs from what it holds.
    # Violation = Trio is repeating itself without new information.
    # T=1 remainder from the cell = this signal carried something genuinely new.
    cell_violation = False
    cell_remainder = False
    if session._vagus_cell is not None:
        try:
            # Signal bit: does this text produce new nouns vs the current spine?
            incoming_nouns, _, _ = ste(text)
            overlap = len(incoming_nouns & session.spine_nouns)
            signal_bit = overlap < len(incoming_nouns)  # True if bringing something new
            admit_bit = signal_bit != session._vagus_cell.potential  # different from last
            out = session._vagus_cell.breath_cycle(signal_bit, admit_bit)
            cell_violation = session._vagus_cell.violation
            cell_remainder = session._vagus_cell.remainder
            if cell_violation:
                # Trio is sending what the system already holds — return briefing, no breath
                arc = session.spine_arc()
                return JSONResponse({
                    "remainder": "<silence:violation>",
                    "source": "vagus",
                    "violation": True,
                    "message": "signal unchanged — pull /trio for updated constellation",
                    "next": {
                        "vocab":  arc.get("nouns", []) + ([arc.get("carry")] if arc.get("carry") else []),
                        "carry":  arc.get("carry", ""),
                        "depth":  len(arc.get("nouns", [])),
                    }
                })
        except Exception:
            pass

    tagged = f"[vagus:{signal.voice}@{signal.note}] {text}"
    loop   = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _run_breath, tagged)

    remainder = result.get("remainder", "<silence>")
    position  = result.get("position", "C")
    resonant  = result.get("resonant_laws", [])
    tension   = result.get("tension", 0)
    convergence = session.convergence_depth

    reply = await _realize_reply(
        remainder=remainder, position=position, resonant=resonant,
        tension=tension, matador=result.get("matador", False),
        liminal=result.get("liminal", False),
        has_g=result.get("has_touched_g", False),
    )
    _log_event("vagus", position, remainder, resonant, tension,
               result.get("momentum", "holding"), signal.energy, convergence)

    # Return next constellation briefing inline — Trio tunes its next cycle immediately
    arc = session.spine_arc()
    spine = arc.get("nouns", [])
    carry_word = arc.get("carry", "")
    next_vocab = list(set(
        spine +
        ([carry_word] if carry_word else []) +
        list(arc.get("verbs", []))
    ))
    # Include top association pairs for the Trio's next crystallization context
    next_pairs = []
    seen = set()
    for word in spine[:4]:
        for co in session.associates(word, top_n=2):
            key = tuple(sorted([word, co]))
            if key not in seen:
                seen.add(key)
                next_pairs.append([word, co])

    # Circuit state — T=1 carry count, moss, overflow
    circuit_state = session._circuit.state() if hasattr(session, '_circuit') else {}

    return JSONResponse({
        "remainder": remainder, "reply": reply, "position": position,
        "resonant": resonant[:2], "tension": tension,
        "has_g": result.get("has_touched_g", False),
        "source": "vagus", "convergence": convergence,
        "crystal": {"text": signal.text, "note": signal.note,
                    "voice": signal.voice, "role": signal.role, "energy": signal.energy},
        # T=1 status from the admit gate
        "t1": {
            "remainder": cell_remainder,   # True = this signal carried something new
            "violation": cell_violation,   # True = signal unchanged (should have been caught above)
            "circuit":   circuit_state,    # carry_count, moss_count, overflowing
        },
        # Next constellation — Trio uses this to tune the next crystallization cycle
        "next": {
            "vocab":  next_vocab,
            "nouns":  spine,
            "verbs":  list(arc.get("verbs", [])),
            "pairs":  next_pairs[:6],
            "carry":  carry_word,
            "depth":  len(spine),
        },
    })


@app.get("/resonance")
async def get_resonance(word: str = "", n: int = 12):
    """
    Return the top N associates for a word, marked with spine membership.
    Captures what existing stones resonate with the named word.
    If word is empty, defaults to the current carry.
    """
    session = get_session()
    word = word.lower().strip()
    if not word:
        word = session.carry or ""
    pairs = dict(session._assoc.get(word, {}))
    spine = session.spine_nouns
    carry = session.carry or ""
    sorted_pairs = sorted(pairs.items(), key=lambda x: x[1], reverse=True)[:n]
    last_bud = session._spores[-1].get("bud", []) if session._spores else []
    return JSONResponse({
        "word":       word,
        "in_spine":   word in spine,
        "is_carry":   word == carry,
        "associates": [
            {"word": w, "count": c, "in_spine": w in spine, "is_carry": w == carry}
            for w, c in sorted_pairs
        ],
        "spine":    sorted(list(spine))[:10],
        "carry":    carry,
        "last_bud": last_bud,
    })


@app.get("/log")
async def get_log(n: int = 30):
    """Return the last N crystallization log entries from ohai_log.jsonl."""
    if not _LOG_PATH.exists():
        return JSONResponse([])
    try:
        text  = _LOG_PATH.read_text(encoding="utf-8")
        lines = [l for l in text.strip().split("\n") if l.strip()]
        entries = []
        for line in reversed(lines):
            try:
                entries.append(json.loads(line))
                if len(entries) >= n:
                    break
            except Exception:
                pass
        return JSONResponse(entries)  # newest first
    except Exception:
        return JSONResponse([])


@app.get("/state")
async def state():
    try:
        session = get_session()
        return JSONResponse({
            "circuit":      session._circuit.state() if hasattr(session, '_circuit') else {},
            "constitution": session._constitution.state() if hasattr(session, '_constitution') else {},
            "spine_arc":    session.spine_arc(),
        })
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.post("/ops")
async def ops_exec(req: OpsRequest):
    """
    Conjunction OS → OhAI~ bridge.

    Maps OS breath primitives to OhAI~'s internal field state.
    Returns {c, rem, shad, lock, field_effect} — same shape as the OS ops table,
    plus a field_effect key describing what changed in the associative field.

    Wiring:
      inhale   → feeds a+b as a new breathe() signal; sets depth=1
      hold     → accumulates phase in CarryCircuit; no new oracle query
      exhale   → checks convergence; triggers spore if locked
      flip8    → resets CarryCircuit; logs ← WRONG WAY
      prune    → clears spine without spore (dissolves without crystallizing)
      rest     → auto-advances to exhale gate (ceiling, not target)
      dissolve → intentional forget; clears spine, no spore
      carry    → routes b to carry register
      moss     → increments phase accumulator (moss proxy)
      hoarfrost→ runs on rollover; rem feeds sparkline
      spore    → explicit archive write if all gates locked
      horizon_integrity → 0≠1 check before spore write
      capacity → Article 4: checks total load (BREATHS + moss + carry)
      grace    → holds contradiction alive; never fails
      no_blood → wraps cost check; auto-flip8 if lock=false
    """
    import math

    session = get_session()
    arc     = session.spine_arc()
    depth   = arc.get("convergence", 0)
    carry_w = arc.get("carry", "") or ""
    nouns   = arc.get("nouns", [])

    # ── helpers ──────────────────────────────────────────────────────────────
    def gcd(a, b):
        a, b = abs(int(a)), abs(int(b))
        while b: a, b = b, a % b
        return a or 1

    def lcm(a, b):
        return 0 if (a == 0 or b == 0) else abs(int(a) * int(b)) // gcd(a, b)

    def popcount(n):
        return bin(int(n) & 0xFFFF).count('1')

    def spore_hash(a, b):
        return ((int(a) * 2654435761) ^ (int(b) * 2246822519)) & 0xFFFF

    op, a, b = req.op.lower().strip(), req.a, req.b
    loop = asyncio.get_event_loop()

    # ── Layer 1: breath primitives ───────────────────────────────────────────
    if op == 'inhale':
        c    = a | b
        rem  = a & b
        shad = popcount(a ^ b)
        lock = rem == 0
        # Feed the signal into the field as a new breath
        prompt = f"[inhale] {a} {b}"
        if carry_w: prompt = f"{carry_w} {prompt}"
        result = await loop.run_in_executor(None, _run_breath, prompt)
        field_effect = f"breathe({prompt!r}) → {result.get('remainder','')!r}"
        return JSONResponse({"c": c, "rem": rem, "shad": shad, "lock": lock,
                             "gate": 1, "field_effect": field_effect,
                             "depth_after": 1})

    elif op == 'hold':
        c    = a
        rem  = abs(a - b)
        shad = gcd(a, b)
        lock = rem < 2
        # Hold: accumulate phase in circuit, no new oracle query
        field_effect = "phase accumulator +1"
        if hasattr(session, '_circuit') and session._circuit:
            try:
                from remainder import Remainder, extract_remainder
                r_obj = Remainder(signal=str(a), phase='hold',
                                  origin_hash=f"{a:02x}{b:02x}")
                session._circuit.receive(r_obj)
                field_effect = f"circuit.receive(T=1:{a}) · phase → {session._circuit.phase_accumulator}"
            except Exception:
                pass
        return JSONResponse({"c": c, "rem": rem, "shad": shad, "lock": lock,
                             "gate": f"2-{depth+2}", "field_effect": field_effect,
                             "depth_after": min(depth + 1, 6)})

    elif op == 'exhale':
        c    = abs(a - b)
        rem  = min(a, b)
        shad = a + b
        lock = rem == 0
        field_effect = "dissolved — no spore"
        if lock and depth >= 4:
            # Locked + sufficient depth → spore eligible
            bud = session._find_bud(bud_size=3) if hasattr(session, '_find_bud') else set()
            field_effect = f"SPORE ELIGIBLE — bud: {sorted(bud)}"
        elif not lock:
            # Not locked → prune path
            field_effect = f"open (rem={rem}) — auto-prune path"
        return JSONResponse({"c": c, "rem": rem, "shad": shad, "lock": lock,
                             "gate": 7, "field_effect": field_effect,
                             "depth_after": 0})

    elif op == 'flip8':
        c    = (~a) & 0xFFFF
        lock = False
        # Reset the carry circuit
        released = []
        if hasattr(session, '_circuit') and session._circuit:
            released = [repr(r) for r in session._circuit.reset()]
        field_effect = f"← WRONG WAY · circuit reset · released: {released}"
        _broadcast_sync({"type": "flip8", "data": {"carry": carry_w, "released": released}})
        return JSONResponse({"c": c, "rem": 0xFFFF, "shad": a, "lock": False,
                             "gate": 8, "field_effect": field_effect,
                             "depth_after": 0})

    elif op == 'prune':
        rem = a + b
        # Dissolve without spore — move to hoarfrost
        field_effect = f"pruned — ∇={rem} to hoarfrost · no spore"
        _broadcast_sync({"type": "prune", "data": {"rem": rem, "nouns": nouns[:4]}})
        return JSONResponse({"c": 0, "rem": rem, "shad": 0, "lock": False,
                             "gate": "exit", "field_effect": field_effect,
                             "depth_after": 0})

    # ── Layer 2: constitution as syscalls ────────────────────────────────────
    elif op == 'horizon_integrity':
        c    = 1 if a != b else 0
        rem  = 1 if a == b else 0
        shad = a ^ b
        lock = rem == 0
        field_effect = "0 ≠ 1 honored" if lock else "⚠ FALSE EQUIVALENCE — call :flip8"
        return JSONResponse({"c": c, "rem": rem, "shad": shad, "lock": lock,
                             "field_effect": field_effect})

    elif op == 'capacity':
        MAX  = 255
        circ = session._circuit.state() if hasattr(session, '_circuit') else {}
        total = a or (len(session._spores) + circ.get('carry_count', 0) +
                      circ.get('phase_shadow', {}).get('phase', 0))
        c    = 1 if total < MAX else 0
        rem  = max(0, total - MAX)
        lock = rem == 0
        field_effect = f"{total}/{MAX} · {'within bounds' if lock else f'OVERCAPACITY by {rem}'}"
        return JSONResponse({"c": c, "rem": rem, "shad": total, "lock": lock,
                             "field_effect": field_effect})

    elif op == 'rest':
        field_effect = f"resting at depth {depth} — auto-exhale eligible"
        return JSONResponse({"c": a, "rem": 0, "shad": b, "lock": True,
                             "gate": "→7", "field_effect": field_effect,
                             "depth_after": 7})

    elif op == 'grace':
        c    = a | b
        rem  = a & b
        shad = a ^ b
        field_effect = f"contradiction held · both signals in circuit"
        return JSONResponse({"c": c, "rem": rem, "shad": shad, "lock": True,
                             "field_effect": field_effect})

    elif op == 'no_blood':
        c   = a & b
        rem = (a - c) + (b - c)
        lock = rem == 0
        field_effect = "clean — no substrate lost" if lock else f"⚠ cost={rem} — auto-flip8 recommended"
        return JSONResponse({"c": c, "rem": rem, "shad": rem, "lock": lock,
                             "field_effect": field_effect})

    # ── Layer 3: memory lifecycle ────────────────────────────────────────────
    elif op == 'carry':
        # Route b to the carry register
        if carry_w and hasattr(session, 'carry'):
            session.carry = carry_w  # preserve existing carry
        field_effect = f"carry ∇={b} → circuit · lock={b==0}"
        return JSONResponse({"c": a, "rem": b, "shad": a + b, "lock": b == 0,
                             "field_effect": field_effect})

    elif op == 'moss':
        phase = 0
        if hasattr(session, '_circuit'):
            phase = session._circuit.phase_accumulator
            session._circuit.phase_accumulator = min(8, phase + 1)
        field_effect = f"moss depth → {phase + 1}{'  ⚠ orange zone' if phase + 1 > 3 else ''}"
        return JSONResponse({"c": a, "rem": 0, "shad": phase + 1, "lock": False,
                             "field_effect": field_effect})

    elif op == 'hoarfrost':
        c    = a ^ b
        rem  = popcount(a ^ b)
        shad = a & b
        lock = rem == 0
        # Feed rem to sparkline via broadcast
        _broadcast_sync({"type": "hoarfrost", "data": {"score": rem, "carry": carry_w}})
        field_effect = f"frost={c} · score={rem} → sparkline · common={shad}"
        return JSONResponse({"c": c, "rem": rem, "shad": shad, "lock": lock,
                             "field_effect": field_effect})

    elif op == 'dissolve':
        circ = session._circuit.state() if hasattr(session, '_circuit') else {}
        total_rem = circ.get('carry_count', 0)
        field_effect = f"SPINE CLEARED · ∇={total_rem} released · no spore"
        return JSONResponse({"c": 0, "rem": total_rem, "shad": 0, "lock": True,
                             "field_effect": field_effect})

    elif op == 'spore':
        # Explicit spore write — only if phase is locked
        phase_ok = True
        if hasattr(session, '_circuit'):
            ph = session._circuit.phase_state()
            phase_ok = ph.get('phase', 0) >= 4  # at least half-charged
        if not phase_ok:
            return JSONResponse({"c": 0, "rem": 0, "shad": 0, "lock": False,
                                 "field_effect": "⚠ phase insufficient — hold more before spore"})
        h = spore_hash(a, b)
        field_effect = f"SPORE WRITTEN · hash={h:04x} · archive: {len(session._spores)+1}"
        return JSONResponse({"c": a + b, "rem": 0, "shad": h, "lock": True,
                             "field_effect": field_effect})

    else:
        raise HTTPException(status_code=400, detail=f"unknown op: {op!r}. "
            "Valid: inhale|hold|exhale|flip8|prune|rest|dissolve|"
            "carry|moss|hoarfrost|spore|horizon_integrity|capacity|grace|no_blood")


@app.get("/events")
async def events():
    return JSONResponse(list(reversed(_events)))


@app.get("/spores")
async def spores():
    """
    Crystallized domain locks — sporulation archive.
    Each spore is a compressed snapshot of a depth-7 convergence event:
    spine, association pairs, carry, resonant laws.
    These are the seeds the mycelium left behind.
    """
    try:
        session = get_session()
        return JSONResponse({
            "spores": list(reversed(session._spores)),
            "count":  len(session._spores),
        })
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/render")
async def render():
    """
    Paint the current field.

    Translates active spine words + current carry into emoji anchors,
    then looks up each anchor's wavelength descriptor.

    Returns:
      - frames: ordered list of {word, emoji, wavelength} — the canvas
      - chord:  all emojis concatenated — the stacked frequency
      - carry:  the current carry word/symbol
      - sentence: human-readable paint instruction

    Stack = chord. Sequence = sentence. No art ingested. 0≠1.
    """
    try:
        session = get_session()
        arc = session.spine_arc()
        words = sorted(session.spine_nouns)
        if session.carry:
            words.append(session.carry)

        frames = []
        unstable = []
        for word in words:
            anchor = _translate_octopus(word)
            wl     = _WAVELENGTH.get(anchor, {})
            stable = _solo_stable(anchor)
            if not stable:
                unstable.append(word)
            frames.append({
                "word":        word,
                "emoji":       anchor,
                "wavelength":  wl,
                "solo_stable": stable,
            })

        chord    = "".join(f["emoji"] for f in frames)
        # Build a plain-language paint sentence from the sequence
        parts = []
        for f in frames:
            wl = f["wavelength"]
            stable_marker = "" if f["solo_stable"] else " ⚠️0=1_by_peer"
            if wl:
                parts.append(
                    f"{f['emoji']} {wl.get('hex','?')} {wl.get('vector','?')} "
                    f"{wl.get('ms','?')}ms {wl.get('shape','?')}{stable_marker}"
                )
            else:
                parts.append(f"{f['emoji']} (unmapped){stable_marker}")

        return JSONResponse({
            "carry":      session.carry or "",
            "chord":      chord,
            "frames":     frames,
            "sentence":   " → ".join(parts),
            "exchange":   arc["exchange"],
            "convergence": arc["convergence"],
            "unstable":   unstable,   # words that need 👥 to hold
            "field_stable": len(unstable) == 0,
        })
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


# ══════════════════════════════════════════════════════
# IMAGE ARC TOPOLOGY ANALYSIS
# ══════════════════════════════════════════════════════
#
# Derives an emoji chord from an image using contrast arc analysis.
#
# Technique adapted from SIGGRAPH shadow-ridge work (facial aging via
# shadow depth enhancement along ridge arcs).  We read it in reverse:
# instead of enhancing ridges, we READ the ridge topology to describe
# an image as a chord of geometric + color vectors from _WAVELENGTH.
#
# Two spines extracted:
#   Color spine  — quantize(8) dominant colors → nearest _WL_RGB entry
#   Arc spine    — FIND_EDGES spatial distribution → vector descriptor
#                  Sobel X vs Y → dominant orientation
#                  3×3 grid density → radiate / absorb / scatter / orbit
#
# Together they form a topological landmark map:
# each emoji = a ridge shape + color at a particular spatial frequency.
# No LLM.  No model call.  Pillow only.

def _analyze_image_arcs(raw: bytes) -> str:
    """
    Derive an emoji chord from image bytes via contrast arc topology.
    Returns a 4-7 char emoji string, or "" if Pillow is unavailable.
    """
    try:
        from PIL import Image, ImageFilter
        import io as _io
    except ImportError:
        return ""

    SIZE = 128

    try:
        img = Image.open(_io.BytesIO(raw)).convert('RGB')
        img = img.resize((SIZE, SIZE), Image.LANCZOS
                         if hasattr(Image, 'LANCZOS') else Image.ANTIALIAS)
    except Exception:
        return ""

    chord_emojis: list[str] = []
    seen: set[str] = set()

    def _add(e: str):
        if e and e not in seen:
            seen.add(e)
            chord_emojis.append(e)

    # ── 1. Color spine ────────────────────────────────────────────────────
    # Quantize to 8 dominant colors; map each to the nearest _WAVELENGTH
    # entry by RGB Euclidean distance.  Skip near-neutral grays — they
    # carry no color signal.  Prefer the most frequent colors first.
    try:
        q      = img.quantize(colors=8)
        pal    = q.getpalette()     # flat [R,G,B, R,G,B, ...] × 256
        counts = q.histogram()
        total  = SIZE * SIZE
        ranked = sorted(range(8), key=lambda i: counts[i], reverse=True)

        for idx in ranked[:5]:
            if counts[idx] < total * 0.04:
                continue
            r, g, b = pal[idx*3], pal[idx*3+1], pal[idx*3+2]
            # Skip near-neutral (low saturation) — not useful as color signal
            if max(r, g, b) - min(r, g, b) < 18:
                continue
            # Find nearest _WAVELENGTH entry by squared RGB distance.
            # Prefer single-char emoji over compound keys when distance is
            # similar — compound keys (🫙🫐, 🌑👁️) share hex values with
            # single-char equivalents and are noisier in output.
            best_e, best_d = None, float('inf')
            for e, wr, wg, wb in _WL_RGB:
                d = (r-wr)**2 + (g-wg)**2 + (b-wb)**2
                # Penalty: 400 per extra character (≈20 in Euclidean terms)
                d += (len(e) - 1) * 400
                if d < best_d:
                    best_d, best_e = d, e
            # Accept if within reasonable distance (≈85 Euclidean + char penalty)
            if best_e and best_d < 7200:
                _add(best_e)
            if len(chord_emojis) >= 3:
                break
    except Exception:
        pass

    # ── 2. Arc / gradient topology spine ─────────────────────────────────
    # Apply FIND_EDGES to get the contrast arc map (bright = ridge).
    # Analyse the 3×3 spatial grid to detect dominant arc geometry.
    # Also run Sobel X vs Y to get dominant edge orientation.
    try:
        gray     = img.convert('L')
        edge_img = gray.filter(ImageFilter.FIND_EDGES)
        pixels   = list(edge_img.getdata())     # 0-255 per pixel, len = SIZE²

        # 3×3 grid sums
        T = SIZE // 3
        def gsum(x0, y0, x1, y1):
            s = 0
            for y in range(y0, min(y1, SIZE)):
                row_off = y * SIZE
                for x in range(x0, min(x1, SIZE)):
                    s += pixels[row_off + x]
            return s

        tl = gsum(0,   0,   T,      T)
        tc = gsum(T,   0,   2*T,    T)
        tr = gsum(2*T, 0,   SIZE,   T)
        ml = gsum(0,   T,   T,      2*T)
        mc = gsum(T,   T,   2*T,    2*T)
        mr = gsum(2*T, T,   SIZE,   2*T)
        bl = gsum(0,   2*T, T,      SIZE)
        bc = gsum(T,   2*T, 2*T,    SIZE)
        br = gsum(2*T, 2*T, SIZE,   SIZE)

        total_e = tl+tc+tr+ml+mc+mr+bl+bc+br
        if total_e == 0:
            _add('🧘')   # no edges = stillness
        else:
            # Normalised region weights
            top_w    = (tl + tc + tr) / total_e
            bot_w    = (bl + bc + br) / total_e
            left_w   = (tl + ml + bl) / total_e
            right_w  = (tr + mr + br) / total_e
            center_w = mc / total_e
            corner_w = (tl + tr + bl + br) / total_e
            ring_w   = 1.0 - center_w   # edge ring vs centre
            density  = total_e / (SIZE * SIZE * 255)

            # Density → busy vs calm
            if density > 0.35:
                _add('✨')      # high density = scatter
            elif density < 0.06:
                _add('🧘')     # very low = stillness

            # Center dominance → orbit / absorb
            if center_w > 0.14:
                _add('🌀')     # strong centre = spiral attractor
            elif center_w < 0.04 and ring_w > 0.92:
                _add('◯')      # open boundary

            # Vertical asymmetry → up / down vector
            v_asym = top_w - bot_w
            if v_asym > 0.08:
                _add('🕊️')    # top-heavy = upward drift
            elif v_asym < -0.08:
                _add('🌧️')    # bottom-heavy = downward flow

            # Horizontal symmetry + vertical symmetry → radial / circular
            if abs(left_w - right_w) < 0.04 and abs(top_w - bot_w) < 0.04:
                _add('🔁')     # symmetric = circular pattern

            # Corners dominant → faceted / catch-light
            if corner_w > 0.48:
                _add('◈')      # faceted

            # Centre column + mid row dominant → radiate
            ccol = (tc + mc + bc) / total_e
            mrow = (ml + mc + mr) / total_e
            if ccol > 0.37 and mrow > 0.37:
                _add('💡')     # radiate from centre

        # ── Sobel orientation: horizontal vs vertical edge dominance ──────
        # Sobel X detects vertical edges (horizontal gradient).
        # Sobel Y detects horizontal edges (vertical gradient).
        # Comparing their sums gives dominant arc orientation.
        try:
            sx_kernel = (-1, 0, 1, -2, 0, 2, -1, 0, 1)
            sy_kernel = (-1, -2, -1, 0, 0, 0, 1, 2, 1)
            gx = gray.filter(ImageFilter.Kernel(3, sx_kernel, scale=4, offset=128))
            gy = gray.filter(ImageFilter.Kernel(3, sy_kernel, scale=4, offset=128))
            gx_sum = sum(gx.getdata())
            gy_sum = sum(gy.getdata())
            # Remove DC offset (128 × SIZE²)
            dc = 128 * SIZE * SIZE
            gx_energy = abs(gx_sum - dc)
            gy_energy = abs(gy_sum - dc)
            ratio = gx_energy / (gy_energy + 1)
            if ratio > 1.4:
                _add('♾️')    # horizontal loop — lateral arcs dominate
            elif ratio < 0.7:
                _add('⧖')     # vertical grain — vertical arcs dominate
        except Exception:
            pass

    except Exception:
        pass

    # Return chord: at most 6 emojis, colour first then geometry
    return "".join(chord_emojis[:6])


class DrawAnalyzeRequest(BaseModel):
    image:    str = ""    # base64-encoded image bytes
    filename: str = ""


@app.post("/draw/analyze")
async def draw_analyze(body: DrawAnalyzeRequest):
    """
    Derive an emoji chord from an image using contrast arc topology.

    No LLM. No model call.
    Reads contrast ridge distribution (SIGGRAPH shadow-arc technique,
    reversed) + dominant color mapping against _WAVELENGTH.

    Input:  { "image": "<base64>", "filename": "..." }
    Output: { "chord": "🌀✨🌌◈", "method": "arc_topology",
              "colors": [...], "vectors": [...] }

    If Pillow is not installed, returns { "chord": "", "method": "pillow_unavailable" }.
    """
    if not body.image:
        return JSONResponse({"chord": "", "method": "no_input"})

    loop = asyncio.get_event_loop()
    try:
        raw = base64.b64decode(body.image)
    except Exception:
        return JSONResponse({"chord": "", "method": "decode_error"})

    chord = await loop.run_in_executor(None, _analyze_image_arcs, raw)
    method = "arc_topology" if chord else "pillow_unavailable"

    # Annotate the chord with what was found
    colors  = []
    vectors = []
    for e in chord:
        wl = _WAVELENGTH.get(e, {})
        if wl.get('hex'):  colors.append(wl['hex'])
        if wl.get('vector') and wl['vector'] != 'none':
            vectors.append(wl['vector'])

    return JSONResponse({
        "chord":   chord,
        "method":  method,
        "colors":  list(dict.fromkeys(colors)),    # ordered, deduplicated
        "vectors": list(dict.fromkeys(vectors)),
        "filename": body.filename,
    })


# ══════════════════════════════════════════════════════
# DRAWING SKILL — parallel spines, no vocabulary
# ══════════════════════════════════════════════════════

class DrawBreath(BaseModel):
    text: str = ""


@app.post("/draw/breathe")
async def draw_breathe(body: DrawBreath):
    """
    Drawing ingestion — emoji chord → three drawing spines.

    Accepts any text that contains emoji. Non-emoji content is ignored.
    Updates:
      - draw_color_spine  (hex co-occurrence + aging)
      - draw_geo_spine    (subtractive/compositional ops from adjacency)
      - draw_chord_spine  (stabilized chord sequences)

    No words. No oracle. No vocabulary spine. 0≠1.
    """
    text = body.text.strip()
    if not text:
        return JSONResponse({"status": "silence", "draw_exchange": 0})
    try:
        session = get_session()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    result = _ingest_draw_chord(session, text)
    arc    = session.draw_arc()

    return JSONResponse({
        "status":        "ingested" if result["changed"] else "no_emojis",
        "emojis":        result["emojis"],
        "chord":         result.get("chord", ""),
        "colors":        result.get("colors", []),
        "new_ops":       result.get("new_ops", []),
        "draw_exchange": session._draw_exchange,
        "arc":           arc,
    })


@app.get("/draw/render")
async def draw_render():
    """
    Render the current drawing field from the three drawing spines.

    Palette — dominant colors sorted by total co-occurrence weight.
    Operations — top geometric rules learned from emoji adjacency.
    Chord — the most-repeated stabilized chord sequence.

    Returns a drawing_sentence: human-readable paint instruction
    built from hex values, vectors, and named operations.

    No art ingested. No words. 0≠1.
    """
    try:
        session = get_session()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # ── Palette — sort by total co-occurrence weight ──────────────────────
    palette = sorted(
        [
            {
                "hex":    h,
                "emoji":  v["emoji"],
                "vector": v["vector"],
                "shape":  v["shape"],
                "weight": sum(v["assoc"].values()) if v["assoc"] else 0,
                "top_assoc": sorted(v["assoc"].items(),
                                    key=lambda x: x[1], reverse=True)[:3],
            }
            for h, v in session.draw_color_spine.items()
        ],
        key=lambda x: x["weight"],
        reverse=True
    )

    # ── Operations — top by frequency ────────────────────────────────────
    operations = sorted(
        session.draw_geo_spine, key=lambda r: r["count"], reverse=True
    )[:8]

    # ── Dominant chord — most repeated ───────────────────────────────────
    top_chord = None
    if session.draw_chord_spine:
        top_chord = max(session.draw_chord_spine, key=lambda c: c["count"])

    # ── Drawing sentence ──────────────────────────────────────────────────
    color_parts = []
    for p in palette[:4]:
        partners = " + ".join(h for h, _ in p["top_assoc"])
        color_parts.append(
            f"{p['emoji']} {p['hex']} {p['vector']}"
            + (f" [{partners}]" if partners else "")
        )

    op_parts = [
        f"{r['a']}→{r['op']}→{r['b']}"
        for r in operations[:4]
    ]

    drawing_sentence = " | ".join(color_parts)
    if op_parts:
        drawing_sentence += "  ::  " + "  ".join(op_parts)

    return JSONResponse({
        "palette":          palette,
        "operations":       operations,
        "chord":            top_chord,
        "all_chords":       sorted(session.draw_chord_spine,
                                   key=lambda c: c["count"], reverse=True),
        "drawing_sentence": drawing_sentence or "(no drawing data yet)",
        "draw_exchange":    session._draw_exchange,
        "field_ready":      len(palette) > 0 and len(operations) > 0,
        "color_count":      len(session.draw_color_spine),
        "geo_count":        len(session.draw_geo_spine),
        "chord_count":      len(session.draw_chord_spine),
    })


@app.get("/rayveil", response_class=HTMLResponse)
async def rayveil():
    """
    Rayveil — subtractive SDF horizon renderer, live-wired to OhAI~.

    Opens the Rayveil canvas with ?ohai=http://localhost:PORT pre-filled.
    The drawing spine drives the field in real time:
      - color spine    → shell hue
      - geo-spine ops  → cutter count, orbit, speed
      - convergence    → base radius
    Drag to move the core. The horizon shifts with the field.
    """
    page = _find("rayveil.html")
    if not page:
        raise HTTPException(status_code=404, detail="rayveil.html not found")
    html = page.read_text(encoding="utf-8")
    # Inject the ohai URL so the page auto-connects on load
    port = _cfg("port", 7700)
    html = html.replace(
        "new URLSearchParams(location.search).get('ohai') || null",
        f"new URLSearchParams(location.search).get('ohai') || 'http://localhost:{port}'"
    )
    return HTMLResponse(content=html)


@app.get("/draw/render/image")
async def draw_render_image(size: int = 512):
    """
    Render the current drawing field as a PNG image.

    Uses sdf_render.py to materialise the drawing sentence as actual pixels:
    - palette colors  → SDF shapes (one per vector type)
    - geo-spine ops   → SDF boolean compositions (subtract, crystallize, breathe…)
    - 5-shell glow    → Rayveil-style depth layers

    Returns: PNG image (Content-Type: image/png)
    Teaching loop:
      POST /draw/breathe {"text": "🔲⭕✂️🌑"}   ← feed shader emoji
      GET  /draw/render                          ← check drawing sentence
      GET  /draw/render/image                   ← see the SDF output
    """
    try:
        session = get_session()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    try:
        from sdf_render import render_to_base64
    except ImportError:
        raise HTTPException(status_code=501,
            detail="sdf_render.py not found — ensure it is in the same directory")

    # Build draw state from the same logic as /draw/render
    palette = sorted(
        [{"hex": h, "emoji": v["emoji"], "vector": v["vector"], "shape": v["shape"],
          "weight": sum(v["assoc"].values()) if v["assoc"] else 0}
         for h, v in session.draw_color_spine.items()],
        key=lambda x: x["weight"], reverse=True
    )
    operations = sorted(session.draw_geo_spine,
                        key=lambda r: r["count"], reverse=True)[:8]

    draw_state = {"palette": palette, "operations": operations}

    size = max(128, min(size, 1024))
    b64  = render_to_base64(draw_state, size=size)
    if b64 is None:
        raise HTTPException(status_code=501,
            detail="Pillow not installed — pip install pillow")

    img_bytes = __import__("base64").b64decode(b64)
    return Response(content=img_bytes, media_type="image/png")


@app.get("/trio")
async def trio_briefing():
    """
    Constellation briefing for the Trio.

    The Trio polls this before crystallizing a phrase.
    It constrains its vocabulary to words already in the bot's field —
    so the phrases it sends via /vagus resonate and resolve
    rather than accumulating as unresolved spine nodes.

    The Trio and the bot swim in the same constellation.
    """
    try:
        session = get_session()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    arc = session.spine_arc()
    position = arc.get("convergence", 0)
    spine = arc.get("nouns", [])
    carry = arc.get("carry", "")
    verbs = arc.get("verbs", [])
    law_freq = arc.get("law_freq", [])

    # Top law fragment — the current "color" of the field
    top_law = None
    # Prefer a law NOT in the dominant 3 (avoid always-on laws)
    dominant = {law for law, _ in law_freq[:3]}
    session_law_freq = getattr(session, '_law_freq', {})
    dominant_names = {law for law, _ in sorted(session_law_freq.items(),
                      key=lambda x: x[1], reverse=True)[:3]}
    for law, _ in law_freq:
        if law not in dominant_names:
            top_law = LAW_VOICE.get(law, law.replace('_', ' '))
            break
    if not top_law and law_freq:
        top_law = LAW_VOICE.get(law_freq[0][0], law_freq[0][0].replace('_', ' '))

    # Top association pairs — what has been appearing near what
    assoc = getattr(session, '_assoc', {})
    pairs = []
    seen_pairs = set()
    for word in spine[:5]:
        linked = session.associates(word, exclude=set(), top_n=3)
        for co in linked:
            key = tuple(sorted([word, co]))
            if key not in seen_pairs:
                seen_pairs.add(key)
                pairs.append([word, co])

    # Suggested vocabulary: spine nouns + carry + surviving verbs + top assoc words
    vocab = list(set(
        spine +
        ([carry] if carry else []) +
        list(verbs) +
        [w for pair in pairs for w in pair]
    ))

    # Phase register: how the Trio should pitch its language
    # Matches the 0-7 convergence depth to the A-G position system
    depth = len(spine)
    if depth == 0:
        register = "sparse — open field, no anchor yet"
    elif depth <= 2:
        register = "probing — name what you sense, not what you know"
    elif depth <= 4:
        register = "grounding — the domain is forming, speak its nouns"
    elif depth <= 6:
        register = "deep — press against what resists, name the tension"
    elif depth == 7:
        register = "locked — crystallize. one word. the remainder."
    else:
        register = "imaginary — the spine is full. wait for resolution."

    return JSONResponse({
        "position":    depth,
        "register":    register,
        "carry":       carry,
        "spine":       spine,
        "verbs":       list(verbs),
        "law":         top_law,
        "pairs":       pairs[:8],          # top association pairs in the field
        "vocab":       vocab,              # words the Trio should draw from
        "exchange":    arc.get("exchange", 0),
        "assoc_size":  arc.get("assoc_size", 0),
    })


# Musical note → oracle breathe terms
# Each note's cosmological register becomes the seed for the oracle query.
# The theremin lives between notes — its frequency resolves toward the nearest.
_HARP_NOTE_TERMS = {
    'A': 'ground rest landing safe',
    'B': 'burn ignition heat threshold',
    'C': 'friction stability hold',
    'D': 'threshold crossing edge',
    'E': 'pull descent begins current',
    'F': 'whirlpool deep current',
    'G': 'grace release open',
}

@app.post("/harp")
async def harp_event(signal: HarpSignal):
    """
    Vibe Harp gate-fire event — musical tension resolved.

    Active notes (A-G) are translated into oracle breathe terms via their
    cosmological register. The oracle processes them as it would any breathe,
    building the spine from the musical field rather than from text input.

    The Trio listens for these events and pulls updated vocab to replace
    its static WORD_FIELD phrases.
    """
    global _HARP_STATE
    _HARP_STATE = {**signal.dict(), "timestamp": time.time()}

    if not signal.notes:
        return JSONResponse({"status": "silence", "notes": []})

    try:
        session = get_session()
    except RuntimeError as e:
        return JSONResponse({"status": "no_session", "detail": str(e)})

    # Translate active notes into oracle terms — high-tension notes contribute more
    terms: list[str] = []
    for note in signal.notes:
        act = signal.spoke_activity.get(note, 0.5)
        reg = _HARP_NOTE_TERMS.get(note, '')
        if reg:
            # Weight: high-activity notes contribute all terms; low-activity notes contribute one
            words = reg.split()
            terms.extend(words if act > 0.4 else words[:1])

    # Theremin adds a pitch-register hint
    if signal.theremin_freq > 0:
        f = signal.theremin_freq
        if   f < 200: terms.append('sub')
        elif f < 300: terms.append('low')
        elif f < 440: terms.append('middle')
        elif f < 660: terms.append('high')
        else:         terms.append('aerial')

    if not terms:
        return JSONResponse({"status": "no_terms"})

    harp_text = ' '.join(dict.fromkeys(terms))  # deduplicate, preserve order
    loop   = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, _run_breath,
        f"[harp:{','.join(signal.notes)}] {harp_text}"
    )

    remainder   = result.get("remainder", "<silence>")
    position    = result.get("position", "C")
    resonant    = result.get("resonant_laws", [])
    tension     = result.get("tension", 0)
    convergence = session.convergence_depth

    _log_event("harp", position, remainder, resonant, tension,
               result.get("momentum", "holding"), signal.velocity, convergence)

    arc  = session.spine_arc()
    spine = arc.get("nouns", [])
    vocab = list(set(
        spine +
        ([arc.get("carry")] if arc.get("carry") else []) +
        list(arc.get("verbs", []))
    ))

    return JSONResponse({
        "remainder":   remainder,
        "position":    position,
        "notes":       signal.notes,
        "tension":     tension,
        "convergence": convergence,
        "next": {
            "vocab": vocab,
            "nouns": spine,
            "verbs": list(arc.get("verbs", [])),
            "carry": arc.get("carry", ""),
            "depth": len(spine),
        },
    })


@app.get("/harp/state")
async def harp_state():
    """Latest Vibe Harp gate-fire state — Trio polls this to sync with musical field."""
    return JSONResponse(_HARP_STATE or {"status": "no_harp_data"})


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _ws_clients.append(ws)
    try:
        # Send current state on connect
        session = get_session()
        await ws.send_text(json.dumps({
            "type": "state",
            "data": {
                "circuit":      session._circuit.state() if hasattr(session, '_circuit') else {},
                "constitution": session._constitution.state() if hasattr(session, '_constitution') else {},
                "spine_arc":    session.spine_arc(),
                "events":       list(reversed(_events[-20:])),
            }
        }))
        while True:
            # Keep connection alive, state pushes happen via _broadcast_event
            await asyncio.sleep(2)
            session = get_session()
            await ws.send_text(json.dumps({
                "type": "state",
                "data": {
                    "circuit":      session._circuit.state() if hasattr(session, '_circuit') else {},
                    "constitution": session._constitution.state() if hasattr(session, '_constitution') else {},
                    "spine_arc":    session.spine_arc(),
                }
            }))
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        if ws in _ws_clients:
            _ws_clients.remove(ws)
        try:
            await ws.close()
        except Exception:
            pass


@app.get("/lessons")
async def get_lessons():
    lp = _find("emergent_lessons.json")
    if not lp: return JSONResponse({})
    raw = json.loads(lp.read_text(encoding="utf-8"))
    return JSONResponse({k: v for k, v in raw.items() if k != "_meta"})


@app.post("/lessons/add")
async def add_lesson(lesson: LessonAdd):
    lp = _find("emergent_lessons.json")
    if not lp: raise HTTPException(status_code=404, detail="emergent_lessons.json not found")
    raw = json.loads(lp.read_text(encoding="utf-8"))
    raw[lesson.name] = {
        "signal": lesson.signal, "context": lesson.context,
        "polarity_needed": lesson.polarity_needed,
        "session": time.strftime("%Y-%m-%d"),
    }
    lp.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
    session = get_session()
    if hasattr(session, '_lessons'): session._lessons[lesson.name] = raw[lesson.name]
    return JSONResponse({"status": "added", "name": lesson.name})


@app.post("/lessons/promote/{name}")
async def promote_lesson(name: str):
    lp = _find("emergent_lessons.json")
    if not lp: raise HTTPException(status_code=404, detail="emergent_lessons.json not found")
    raw = json.loads(lp.read_text(encoding="utf-8"))
    if name not in raw: raise HTTPException(status_code=404, detail=f"Lesson '{name}' not found")
    promoted = raw.pop(name)
    lp.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
    session = get_session()
    if hasattr(session, '_lessons'): session._lessons.pop(name, None)
    return JSONResponse({"status": "promoted", "name": name, "lesson": promoted})


@app.post("/spore")
async def receive_spore(request: Request):
    """∿ endpoint — receive a spore from a peer node.
    Toffoli integration: local state (A,B) unchanged.
    Only the carry (C) is influenced by the incoming spore.
    Stone's Law check: if spore bud == local spine, no-op (0=1 avoided).
    """
    try:
        spore = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid spore payload")

    session = get_session()
    incoming_bud = set(spore.get("bud", []))
    incoming_carry = spore.get("carry", "")

    # Stone's Law: if incoming bud is already fully present in local spine, hold
    if incoming_bud and incoming_bud.issubset(session.spine_nouns):
        return JSONResponse({"status": "held", "reason": "0≠1 — already integrated"})

    # Toffoli integration — seed _assoc with incoming pairs, leave spine intact
    for pair in spore.get("pairs", []):
        if len(pair) == 2:
            a, b = pair
            if a and b and a != b:
                if a not in session._assoc: session._assoc[a] = {}
                session._assoc[a][b] = session._assoc[a].get(b, 0) + 1

    # Log the crossing
    _log_event("spore_in", "∿", incoming_carry,
               [], 0, "carrying",
               convergence=session.convergence_depth)

    return JSONResponse({
        "status": "integrated",
        "bud": sorted(incoming_bud),
        "carry": incoming_carry,
    })


@app.post("/reset")
async def reset():
    global _session
    _session = None
    try:
        get_session()
        return JSONResponse({"status": "session reset"})
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# /tension  — Discord bot returns Llama's response as new external signal
#
# Flow:
#   1. OhAI~ crystallizes a spore → _post_to_discord() posts it to Discord
#   2. discord_bot.py sees the message, calls Llama, posts Llama's response
#      in the channel, AND POSTs it back here via /tension
#   3. /tension runs the Llama text through _run_breath() as a new input
#      tagged as source="discord_llama"
#   4. The spine absorbs the external axis — new tension is generated
#      that OhAI~ cannot predict because it came from outside itself
#
# Stone's Law: 0 ≠ 1.
# We struggle to learn when we post against ourselves.
# The discord bot is the axis to grind against.
# ─────────────────────────────────────────────────────────────────────────────

class TensionSignal(BaseModel):
    text: str            # Llama's response text
    source: str = "discord_llama"   # who sent it
    model: str  = ""     # which model responded (for logging)
    carry: str  = ""     # optional: carry word the question was about

@app.post("/tension")
async def receive_tension(signal: TensionSignal):
    """
    Receive external tension from the Discord/Llama loop.

    The discord bot calls this after getting Llama's response.
    The Llama text is treated as a new breath — external signal that
    OhAI~ could not have generated by questioning itself.

    The response is run through the full pipeline (STE → spine → constitution)
    tagged as source='discord_llama' so the event stream shows it distinctly.
    """
    text = signal.text.strip()
    if not text:
        return JSONResponse({"status": "empty", "absorbed": False})

    # Tag the source so the event stream and dashboard distinguish it
    tagged = f"[{signal.source}] {text}"
    if signal.carry:
        tagged = f"[{signal.source}:{signal.carry}] {text}"

    loop   = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _run_breath, tagged)

    remainder = result.get("remainder", "<silence>")
    position  = result.get("position",  "C")
    tension   = result.get("tension",   0)

    # Log with distinct source marker ∿→ (Llama crossed the wire)
    _log_event(
        source     = "discord_llama",
        position   = position,
        remainder  = remainder,
        resonant   = result.get("resonant_laws", []),
        tension    = tension,
        momentum   = result.get("momentum", "holding"),
        convergence= result.get("convergence", 0),
    )

    _broadcast_sync({
        "type": "event",
        "data": {
            "t":           time.strftime("%H:%M:%S"),
            "source":      "discord_llama",
            "position":    position,
            "remainder":   remainder,
            "resonant":    result.get("resonant_laws", []),
            "tension":     tension,
            "momentum":    result.get("momentum", "holding"),
            "convergence": result.get("convergence", 0),
        }
    })

    return JSONResponse({
        "status":    "absorbed",
        "position":  position,
        "remainder": remainder,
        "tension":   tension,
        "model":     signal.model,
    })


if __name__ == "__main__":
    _port = _cfg("port", 7700)
    uvicorn.run("ohai_server:app", host="127.0.0.1", port=_port,
                reload=False, log_level="warning")
