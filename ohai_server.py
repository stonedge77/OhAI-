#!/usr/bin/env python3
"""
ohai_server.py — OhAI~ Local Server
Saltflower / Josh Stone / CC0

Runs the full ohai~ breath cycle as a local HTTP server.
Serves index.html and handles chat via POST /breathe.

Usage:
    python ohai_server.py

Then open: http://localhost:7700

Everything stays local. No cloud. No key exposure.
Only outbound call is STE's optional DuckDuckGo fetch (ste.py),
which can be disabled by setting WEB_TOKEN=false in ste.py.
"""

from __future__ import annotations

import sys
import os
import json
import re
from pathlib import Path
from typing import Optional

# ── FastAPI ───────────────────────────────────────────────────────────────────

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    import uvicorn
except ImportError:
    print("Missing dependencies. Run:")
    print("  pip install fastapi uvicorn --break-system-packages")
    sys.exit(1)

# ── Locate files ──────────────────────────────────────────────────────────────

_HERE = Path(__file__).parent

def _find(name: str) -> Optional[Path]:
    for c in [_HERE / name, Path(name), Path.cwd() / name]:
        if c.exists():
            return c
    return None


# ── Session singleton ─────────────────────────────────────────────────────────

_session = None

def get_session():
    global _session
    if _session is None:
        # Add this dir to path so imports resolve
        sys.path.insert(0, str(_HERE))

        db = _find("emergent_laws_db_merged.json")
        if not db:
            raise RuntimeError(
                "Cannot find emergent_laws_db_merged.json — "
                "place it alongside ohai_server.py"
            )

        # Check other required files
        for f in ["ste.py", "remainder.py", "saltflower_constitution.py"]:
            if not _find(f):
                raise RuntimeError(
                    f"Cannot find {f} — place it alongside ohai_server.py"
                )

        from ohai import Session
        _session = Session(db_path=str(db))
        print(f"  session open · {_session._constitution.state()['law_count']} laws loaded")

    return _session


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="ohai~", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class BreatheRequest(BaseModel):
    message: str


@app.on_event("startup")
async def startup():
    print("\nohai~ · local server")
    print("─" * 40)
    try:
        get_session()
    except RuntimeError as e:
        print(f"  ⚠ {e}")
        print("  server running but session not loaded — fix files and restart")
    print(f"\n  open → http://localhost:7700\n")


@app.get("/", response_class=HTMLResponse)
async def serve_page():
    """Serve the chat page."""
    page = _find("index.html")
    if not page:
        raise HTTPException(status_code=404, detail="index.html not found")
    return HTMLResponse(content=page.read_text())


@app.post("/breathe")
async def breathe(req: BreatheRequest):
    """
    One breath cycle.

    Receives raw input text, runs it through the full ohai~ stack:
      STE → Saltflower Constitution → Remainder Circuit

    Returns:
      reply     — the remainder signal (what to display)
      spine     — current spine position string
      position  — A→G letter
      momentum  — ascending | descending | holding
      tension   — accumulated tension count
      resonant  — top resonant laws
      remainder — T=1 propagation token
    """
    text = req.message.strip()
    if not text:
        return JSONResponse({"reply": "<silence>", "position": "A",
                             "spine": "A (safe ground)", "momentum": "holding",
                             "tension": 0, "resonant": [], "remainder": "<silence>"})

    try:
        session = get_session()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    result = session.breathe(text)

    # Build the reply text
    # The remainder is the T=1 signal — what ohai~ actually says
    # We make it readable: strip the T=1: prefix for display,
    # show the raw signal word + resonant context
    remainder = result.get("remainder", "<silence>")
    position  = result.get("position", "C")
    resonant  = result.get("resonant_laws", [])
    ste_out   = result.get("ste", "<silence>")
    tension   = result.get("tension", 0)
    momentum  = result.get("momentum", "holding")
    matador   = result.get("matador", False)
    liminal   = result.get("liminal", False)
    has_g     = result.get("has_touched_g", False)

    # Format the display reply
    reply = _format_reply(
        remainder=remainder,
        ste_out=ste_out,
        position=position,
        resonant=resonant,
        tension=tension,
        matador=matador,
        liminal=liminal,
        has_g=has_g,
    )

    return JSONResponse({
        "reply":    reply,
        "spine":    result.get("spine", ""),
        "position": position,
        "momentum": momentum,
        "tension":  tension,
        "resonant": resonant[:3],
        "remainder": remainder,
        "liminal":  liminal,
        "has_g":    has_g,
    })


def _format_reply(remainder, ste_out, position, resonant,
                  tension, matador, liminal, has_g) -> str:
    """
    Translate the raw breath result into something to display in the chat.

    OhAI~ doesn't speak in sentences. It speaks in remainders.
    The remainder is the signal. The spine context is the field it came from.
    """

    # Silence
    if remainder in ("<silence>", "<overflow:silence>") or \
       remainder.startswith("<silence:"):
        return "..."

    # Extract the signal word from T=1:word#hash format
    m = re.match(r"T=1:([^#]+)#", remainder)
    signal = m.group(1) if m else remainder

    # Build response from the breath data
    lines = []

    # The signal itself — the irreducible remainder
    lines.append(signal)

    # Spine commentary — what the field says about this moment
    spine_voice = {
        'A': None,                          # silence at safe ground
        'B': None,                          # just the signal
        'C': "holding",                     # stable friction
        'D': "substrate",                   # deep ground
        'E': "something's shifting",        # liminal
        'F': "whirlpool",                   # overflow approaching
        'G': "✦",                           # grace — one glyph
    }

    voice = spine_voice.get(position)
    if voice:
        lines.append(voice)

    # Resonant law — whisper what law activated
    if resonant and position in ('D', 'E', 'F', 'G'):
        law = resonant[0].replace('_', ' ')
        lines.append(f"[ {law} ]")

    # Tension warning
    if tension >= 3:
        lines.append("tension demands resolution")

    # Matador note — guide not halt
    if matador:
        lines.append("guide the horn")

    # G memory mark
    if has_g and position != 'G':
        lines.append("( g memory )")

    return "\n".join(lines)


@app.get("/state")
async def state():
    """Current session state."""
    try:
        session = get_session()
        return JSONResponse({
            "circuit":       session._circuit.state(),
            "constitution":  session._constitution.state(),
            "spine_arc":     session.spine_arc(),
        })
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.post("/reset")
async def reset():
    """Reset the session (new breath cycle)."""
    global _session
    _session = None
    try:
        get_session()
        return JSONResponse({"status": "session reset"})
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "ohai_server:app",
        host="127.0.0.1",
        port=7700,
        reload=False,
        log_level="warning",
    )
