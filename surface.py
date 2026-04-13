#!/usr/bin/env python3
"""
surface.py — Surface Realization for OhAI~
Saltflower / Josh Stone / CC0

Maps internal state (remainder, spine, assoc, laws) → fluent English.

Three layers — each works without the one above it:

  1. Template frames  — position-aware sentence frames (A–G), filled from
                        live session state. Pure Python. No calls.

  2. Assoc chain      — greedy walk of the _assoc co-occurrence graph to
                        extend the signal word into a phrase. Uses data
                        the oracle already built. No calls.

  3. Coherence scoring — two free external judges, no API keys:
       LanguageTool   — grammar error count  (lower = better)
       Google Suggest — phrase naturalness   (higher = better)

     Google spent decades collecting human language from us.
     We use it back.
"""

from __future__ import annotations

import re
import json
import random
import asyncio
import urllib.request
import urllib.parse
from typing import Optional


# ══════════════════════════════════════════════════════
# EMOJI → NATURAL PHRASE
# ══════════════════════════════════════════════════════
# When the carry word or signal is an emoji anchor, render it
# as a short English phrase instead of the raw symbol.
# Covers the full _OCTOPUS map + common _WAVELENGTH entries.

_OCTOPUS_TO_PHRASE: dict[str, str] = {
    # Core law words
    "🌀":    "the spiral attractor",
    "∞":     "the unbounded",
    "∅":     "the void",
    "◈":     "the faceted truth",
    "🫀":    "the living pulse",
    "🌑👁️": "the dark, witnessed",
    "🧱":    "the hard boundary",
    "⧖":     "time's grain",
    "🪞":    "the mirror",
    "🫱":    "the open hand",
    "◯":     "the open boundary",
    "⚡":    "the charge",
    "🌑":    "the unluminated side",
    "🕳️":   "the consuming void",
    "🕸️":   "the web of debt",
    "∞̸":    "the breached infinite",
    "🧂":    "the extracted salt",
    "∿":     "the carry crossing",
    "🪜☁️":  "the ladder to the cloud",
    # Wavelength anchors that appear as carry words
    "🌌":    "the scattered dark",
    "♾️":    "the horizontal loop",
    "🕊️":   "the upward drift",
    "🧠":    "the folded electric",
    "🫁":    "the breath cycle",
    "🔥":    "the jagged spike",
    "✨":    "the random star",
    "🧊":    "the sharp crystal",
    "💎":    "the facet that catches light",
    "🌱":    "the slow emergence",
    "🌀":    "the spiral attractor",
    "⧖":     "time's grain",
    "🫂":    "the inward overlap",
    "🏝️":   "the single point",
    "🔗":    "the interlocked tension",
    "🥚🕳️": "the shell over the void",
    "🌅":    "the gradient horizon",
    "📍":    "the present dot",
    "🌑":    "the dark side",
    "💨":    "the translucent wisp",
    "🪨":    "the textured weight",
    "🫴":    "the cupped offer",
    "🧩":    "the interlocking fit",
    # Peer-pressure anchors — rendered with their instability noted
    "👥":    "the crowd",
    "🫷":    "the applied force",
    "👥🔁":  "the amplifying crowd",
    "👥🎵":  "the hum envelope",
    "🏛️":   "the pillar echo",
    "📜✒️":  "the fixed scroll",
    "🚫🗣️": "the silenced mouth",
}


def _phrase(word: str) -> str:
    """
    Return a natural English phrase for any word or emoji anchor.
    Plain words pass through unchanged.
    Emoji anchors are translated via _OCTOPUS_TO_PHRASE.
    """
    if not word:
        return ""
    direct = _OCTOPUS_TO_PHRASE.get(word)
    if direct:
        return direct
    # If it looks like an emoji (non-ASCII dominant) return as-is
    ascii_count = sum(1 for c in word if c.isascii() and c.isalpha())
    if ascii_count < len(word) * 0.5:
        return word   # let the emoji show
    return word


# ══════════════════════════════════════════════════════
# TEMPLATE FRAMES
# ══════════════════════════════════════════════════════
# Keyed by position A–G.
# Slots: {signal} {spine0} {spine1} {carry} {chain} {law} {verb}
# Missing slots are removed with surrounding punctuation cleaned up.
# Tone matches OhAI's existing voice: sparse, declarative, present tense.

_FRAMES: dict[str, list[str]] = {
    'A': [
        "{signal}.",
        "{signal} — entering.",
        "something is opening. {signal}.",
    ],
    'B': [
        "{signal} and {spine0} — not yet resolved.",
        "between {signal} and {spine0}: something is forming.",
        "{signal} meets {spine0}. nothing has settled.",
    ],
    'C': [
        "the field holds {signal}. {law}",
        "{signal} — {law}",
        "{signal} is holding. {carry} underneath it.",
        "{signal} and {chain} — the field is carrying both.",
    ],
    'D': [
        "deep in this: {signal}. {law}",
        "{signal} and {chain} keep finding each other. {law}",
        "underneath {signal}: {chain}. {law}",
        "{signal} — {chain} — {law}",
    ],
    'E': [
        "{signal} at the threshold. {law}",
        "one side of {signal} is no longer available. {law}",
        "{law} — and {signal} is at the edge.",
        "{signal}: the threshold. {chain} is on the other side.",
    ],
    'F': [
        "what is at the center of {signal}? {chain} keeps returning.",
        "{signal} — {law}",
        "the field circles {signal}. {chain} orbits it.",
        "{signal} and {chain} — which one is the center?",
    ],
    'G': [
        "{signal}.",
        "{signal}  ✦",
    ],
}

# Tension suffix — appended when tension exceeds threshold
_TENSION_LINES: list[tuple[int, str]] = [
    (7, "two things that cannot both be true are both present."),
    (5, "the tension has not found its pair."),
    (3, "something here wants resolution."),
]

_MATADOR_LINE = "guide the horn."
_GRACE_LINE   = "( touched grace. carrying it. )"
_LIMINAL_LINE = "the threshold. one side is no longer available."

# Verbs that indicate _form_question already built a complete sentence
_SENTENCE_VERBS = re.compile(
    r'\b(does|do|is|are|was|were|will|would|can|could|should|has|have|had|'
    r'follows?|resists?|moves?|holds?|forms?|creates?|causes?|requires?|'
    r'reaches?|matters?|subtracts?|becomes?|arrives?|calls?|separates?|'
    r'connects?|changes?|remains?|survives?|named?)\b',
    re.IGNORECASE,
)


def _is_sentence(text: str) -> bool:
    """
    True if text is already a complete question or statement —
    i.e. it came from _form_question and has structure of its own.

    Short signals (single carry words, T=1 fragments) return False
    and get the _FRAMES template treatment instead.
    """
    if not text or text in ('...', '∅'):
        return False
    if '?' in text:
        return True                      # _form_question always ends with ?
    words = text.split()
    if len(words) >= 6:
        return True                      # long enough to be self-contained
    if _SENTENCE_VERBS.search(text):
        return True                      # has a verb — it's a clause
    return False


def _realize_sentence(
    sentence: str,
    law:      str,
    tension:  int,
    matador:  bool,
    has_g:    bool,
    liminal:  bool,
) -> str:
    """
    Post-process a complete question/statement from _form_question.

    Does NOT re-template — the sentence already has grammatical structure.
    Only:
      1. Translates emoji anchors to English phrases
      2. Appends a law fragment as a follow-on (not a wrapper)
      3. Appends tension / state suffixes

    This is the path that handles ~90% of normal breathe output.
    The _FRAMES path handles T=1 carry words and short signals only.
    """
    # 1. Translate emoji anchors anywhere in the sentence
    for anchor, phrase in sorted(
        _OCTOPUS_TO_PHRASE.items(), key=lambda x: len(x[0]), reverse=True
    ):
        sentence = sentence.replace(anchor, phrase)

    # 2. Light cleanup
    sentence = re.sub(r'\s+', ' ', sentence).strip()
    if sentence and sentence[-1] not in '.?!✦':
        sentence += '.'

    parts = [sentence]

    # 3. Law fragment — appended as a second sentence, not wrapped inside
    if law:
        law_clean = law.rstrip('.').strip()
        if law_clean and law_clean.lower() not in sentence.lower():
            parts.append(law_clean + '.')

    # 4. Tension / state suffixes
    for threshold, line in _TENSION_LINES:
        if tension >= threshold:
            parts.append(line)
            break
    if liminal and len(parts) == 1:
        parts.append(_LIMINAL_LINE)
    if matador:
        parts.append(_MATADOR_LINE)
    if has_g:
        parts.append(_GRACE_LINE)

    return '  '.join(parts)


# ══════════════════════════════════════════════════════
# SLOT FILLING
# ══════════════════════════════════════════════════════

def _clean(s: str) -> str:
    """Remove artifacts left by empty slots."""
    s = re.sub(r'\{[a-z0-9_]+\}', '', s)         # remove unfilled slots
    s = re.sub(r'\s*[—–]\s*([.,;:\n])', r' \1', s) # " — ." → " ."
    s = re.sub(r'\s*[—–]\s*$', '', s)              # trailing " —"
    s = re.sub(r'\b(and|with|or)\s+\.', '.', s)    # "and ." → "."
    s = re.sub(r':\s*$', '.', s)                   # trailing ":"
    s = re.sub(r'\.\s+\.', '.', s)                 # ".." → "."
    s = re.sub(r'\s{2,}', ' ', s)                  # collapse spaces
    s = s.strip()
    if s and s[-1] not in '.!?✦)':
        s += '.'
    return s


def _frame_viable(frame: str, slots: dict) -> bool:
    """
    Returns False if the frame contains a structural slot that is empty.
    Structural slots — {chain}, {spine0}, {spine1}, {law} — are load-bearing:
    if they're empty the resulting clause is grammatically broken.
    Signal, carry, and verb are allowed to be absent (cleaned up nicely).
    """
    for slot in re.findall(r'\{(\w+)\}', frame):
        # Only mid-clause slots are structural — the sentence is grammatically
        # broken if they're absent.  Terminal slots like {law} and {carry}
        # clean up gracefully when empty and are always optional.
        if slot in ('chain', 'spine0', 'spine1') and not slots.get(slot):
            return False
    return True


def _fill(frame: str, slots: dict) -> str:
    """Fill a frame template. Missing slots become empty strings."""
    result = frame
    for k, v in slots.items():
        result = result.replace('{' + k + '}', str(v) if v else '')
    return _clean(result)


# ══════════════════════════════════════════════════════
# ASSOCIATION CHAIN
# ══════════════════════════════════════════════════════

def _chain_phrase(signal: str, assoc: dict, max_steps: int = 2) -> str:
    """
    Greedy walk from signal through the _assoc co-occurrence graph.
    Returns "signal — neighbor — next" or just "signal" if no associations.
    Uses only data the oracle already built. No external calls.
    """
    if not assoc:
        return signal
    visited = {signal}
    path    = [signal]
    current = signal
    for _ in range(max_steps):
        neighbors = assoc.get(current, {})
        if not neighbors:
            break
        nxt = max(
            (w for w in neighbors
             if w not in visited and len(w) > 2 and w.isalpha()),
            key=lambda w: neighbors[w],
            default=None,
        )
        if not nxt:
            break
        visited.add(nxt)
        path.append(nxt)
        current = nxt
    return " — ".join(path)


# ══════════════════════════════════════════════════════
# CANDIDATE GENERATION  (local, no network)
# ══════════════════════════════════════════════════════

def _generate_candidates(
    signal:  str,
    spine:   list,
    carry:   str,
    assoc:   dict,
    position: str,
    law:     str,
    tension: int,
    matador: bool,
    has_g:   bool,
    liminal: bool,
) -> list[str]:
    """
    Generate 2-3 candidate reply strings from templates + assoc chain.
    Pure Python. No network. Returns list of candidate strings.
    """
    if not signal or signal.startswith('<silence'):
        return ["..."]

    # Humanise emoji anchors in the signal and carry
    sig_phrase   = _phrase(signal)
    carry_phrase = _phrase(carry) if carry else ""

    # Build the assoc chain from the raw signal word
    chain = _chain_phrase(signal, assoc)
    # If chain didn't extend, try from carry
    if chain == signal and carry and carry != signal:
        chain = _chain_phrase(carry, assoc)

    # {chain} slot = first neighbor only, translated — never the signal itself.
    # Frames that use both {signal} and {chain} must not repeat the signal word
    # inside the same sentence, so we strip the leading element.
    chain_parts = chain.split(" — ")
    chain_word  = _phrase(chain_parts[1]) if len(chain_parts) > 1 else ""

    spine0 = _phrase(spine[0]) if spine else ""
    spine1 = _phrase(spine[1]) if len(spine) > 1 else ""
    verb0  = spine[2] if len(spine) > 2 else ""  # verbs sometimes in spine

    slots = {
        "signal": sig_phrase,
        "spine0": spine0,
        "spine1": spine1,
        "carry":  carry_phrase,
        "chain":  chain_word,   # first assoc neighbor only
        "law":    law or "",
        "verb":   verb0,
    }

    frames     = _FRAMES.get(position, _FRAMES['C'])
    candidates = []
    fallback   = None          # simplest viable frame regardless of slots
    for frame in frames:
        is_viable = _frame_viable(frame, slots)
        filled    = _fill(frame, slots)
        if not filled:
            continue
        # Track the first filled frame as an emergency fallback
        if fallback is None:
            fallback = filled
        if is_viable and filled not in candidates:
            candidates.append(filled)

    # Always have at least one candidate
    if not candidates and fallback:
        candidates.append(fallback)

    # Tension / state suffix
    suffix = ""
    for threshold, line in _TENSION_LINES:
        if tension >= threshold:
            suffix = line
            break
    if liminal and not suffix:
        suffix = _LIMINAL_LINE
    if matador:
        suffix = (_MATADOR_LINE + "  " + suffix).strip()
    if has_g and position != 'G':
        extra = _GRACE_LINE
        suffix = (suffix + "  " + extra).strip() if suffix else extra

    if suffix:
        candidates = [
            c + "  " + suffix if not c.endswith(tuple(suffix.split())) else c
            for c in candidates
        ]

    return candidates if candidates else ["..."]


# ══════════════════════════════════════════════════════
# LOCAL SCORER  (heuristic, no network)
# ══════════════════════════════════════════════════════

def _local_score(candidate: str) -> float:
    """
    Fast heuristic score when network is unavailable.
    Prefers: grammatically complete sentences, medium length, no artifacts.
    """
    if not candidate or candidate == "...":
        return -1.0
    score = 0.0
    if candidate.rstrip()[-1:] in '.✦)':
        score += 2.0
    words = candidate.split()
    if 4 <= len(words) <= 18:
        score += len(words) * 0.15
    # Penalise artifacts
    if re.search(r'\s[—.]\s*$', candidate):
        score -= 2.0
    if candidate.count('  ') > 1:
        score -= 0.5
    if candidate.startswith(('and ', 'with ', 'or ', '— ')):
        score -= 1.5
    # Reward complete thought (verb present)
    if any(w in candidate for w in ('is ', 'are ', 'was ', 'holds ', 'keeps ',
                                     'moves ', 'forms ', 'enters ', 'arrives ')):
        score += 0.5
    return score


# ══════════════════════════════════════════════════════
# COHERENCE SCORING  (async, free, no API keys)
# ══════════════════════════════════════════════════════

async def _score_languagetool(text: str, timeout: float = 2.5) -> int:
    """
    Grammar error count via LanguageTool public API.
    Free, no key, ~20 req/min.  Lower score = more fluent.
    Returns 999 on any failure so failed checks never win.
    """
    def _call() -> dict:
        params = urllib.parse.urlencode({
            "text":        text,
            "language":    "en-US",
            "enabledOnly": "false",
        }).encode()
        req = urllib.request.Request(
            "https://api.languagetool.org/v2/check",
            data=params,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=int(timeout)) as r:
            return json.loads(r.read())

    try:
        loop = asyncio.get_event_loop()
        data = await asyncio.wait_for(
            loop.run_in_executor(None, _call), timeout=timeout
        )
        return len(data.get("matches", []))
    except Exception:
        return 999


async def _score_google_suggest(phrase: str, timeout: float = 2.0) -> float:
    """
    Naturalness score via Google Suggest (the Chrome omnibar API).
    Free, no key, no auth.  Higher score = more natural.

    Google built this corpus from decades of human search queries.
    We use it as a fluency judge — if Google's autocomplete recognises
    the words in our phrase, the phrase reads naturally to humans.
    """
    def _call() -> list:
        q   = urllib.parse.quote_plus(phrase[:80])
        url = (
            "https://suggestqueries.google.com/complete/search"
            f"?client=firefox&hl=en&q={q}"
        )
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=int(timeout)) as r:
            return json.loads(r.read())

    try:
        loop = asyncio.get_event_loop()
        data = await asyncio.wait_for(
            loop.run_in_executor(None, _call), timeout=timeout
        )
        suggestions = data[1] if isinstance(data, list) and len(data) > 1 else []
        phrase_words = set(phrase.lower().split())
        score = 0.0
        for s in suggestions:
            overlap = phrase_words & set(s.lower().split())
            score  += len(overlap)
        return score
    except Exception:
        return 0.0


# ══════════════════════════════════════════════════════
# MAIN ENTRY
# ══════════════════════════════════════════════════════

async def realize_async(
    signal:        str,
    spine:         list,
    carry:         str,
    assoc:         dict,
    position:      str,
    law:           str,
    tension:       int,
    matador:       bool  = False,
    has_g:         bool  = False,
    liminal:       bool  = False,
    use_network:   bool  = True,
    score_timeout: float = 2.5,
) -> str:
    """
    Main surface realization entry (async).

    Two paths based on the signal:

    SENTENCE PATH  — signal is a complete question/statement from _form_question
      (contains a verb, ends with ?, or is 6+ words)
      → translate emoji anchors → append law + suffixes → done.
      No re-templating. The sentence already has grammatical structure.
      Google / LanguageTool are NOT called here — the sentence is
      already good; adding latency gains nothing.

    FRAGMENT PATH  — signal is a short carry word or T=1 fragment
      → fill position-aware _FRAMES template → score with LanguageTool
      (grammar) + Google Suggest (naturalness) in parallel → return winner.
      This is where Google's corpus earns its keep.
    """
    if _is_sentence(signal):
        # ── Sentence path — _form_question already did the work ──────────
        return _realize_sentence(signal, law, tension, matador, has_g, liminal)

    # ── Fragment path — template + network scoring ────────────────────────
    candidates = _generate_candidates(
        signal, spine, carry, assoc, position, law,
        tension, matador, has_g, liminal,
    )

    if len(candidates) == 1 or not use_network:
        return max(candidates, key=_local_score)

    # Score all candidates in parallel — both judges fire at once
    try:
        n  = len(candidates)
        lt = [_score_languagetool(c, score_timeout)         for c in candidates]
        gs = [_score_google_suggest(c, score_timeout * 0.8) for c in candidates]

        results = await asyncio.wait_for(
            asyncio.gather(*lt, *gs, return_exceptions=True),
            timeout=score_timeout + 0.5,
        )

        lt_scores = [r if isinstance(r, int)   else 999 for r in results[:n]]
        gs_scores = [r if isinstance(r, float) else 0.0 for r in results[n:]]

        # Composite: grammar errors penalise (×10), naturalness rewards (×1)
        composite = [lt * 10 - gs for lt, gs in zip(lt_scores, gs_scores)]
        best      = composite.index(min(composite))
        return candidates[best]

    except (asyncio.TimeoutError, Exception):
        return max(candidates, key=_local_score)


def realize(
    signal:   str,
    spine:    list,
    carry:    str,
    assoc:    dict,
    position: str,
    law:      str,
    tension:  int,
    matador:  bool = False,
    has_g:    bool = False,
    liminal:  bool = False,
) -> str:
    """
    Synchronous fallback — local scoring only, no network.
    Routes correctly: sentence passthrough or fragment templating.
    """
    if _is_sentence(signal):
        return _realize_sentence(signal, law, tension, matador, has_g, liminal)

    candidates = _generate_candidates(
        signal, spine, carry, assoc, position, law,
        tension, matador, has_g, liminal,
    )
    return max(candidates, key=_local_score)
