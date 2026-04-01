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
"""

from __future__ import annotations

import sys, os, re, time, json, threading, urllib.request, urllib.parse, html
from pathlib import Path
from typing import Optional

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

try:
    from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
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

def _find(name: str) -> Optional[Path]:
    for c in [_HERE / name, Path(name), Path.cwd() / name]:
        if c.exists():
            return c
    return None


# ══════════════════════════════════════════════════════
# STE \u2014 AND nouns, NAND verbs
# ══════════════════════════════════════════════════════

TRASH = set('''
the a an and or but nor so yet for in on at to by of with from
into onto up down out off over under through about as if then
than that this these those it its i me my you your we our they
he she him her his is are was were be been being have has had
do did does will would could should may might must can not no
yes very really just also still even only quite rather such
both each every more most much many some any all few here there
where when how what who which new old good bad big small great
little first last next same other own long high get got make
made take took come came go went see saw know knew think thought
want need use used give gave let put like very extremely quite
pretty somewhat rather really
actually basically literally obviously clearly
simply totally completely absolutely definitely
certainly probably hopefully apparently
'''.split())

VERB_ROOTS = set('''
move flow spin rotate collapse expand contract rise fall
ascend descend accelerate converge diverge merge split branch
transform become change shift transition evolve crystallize
dissolve saturate deplete accumulate phase lock unlock open
close seal break emit receive transmit absorb reflect refract
amplify attenuate filter subtract signal broadcast carry route
exist persist remain vanish appear hold release exceed
breathe pulse fire activate inhibit excite resonate oscillate
vibrate build construct run execute generate produce destroy
delete create abduct deduce induce infer name define search
find catch watch feed drive force impose thrust dance glide
separate unite bind free
'''.split())

VERB_ENDINGS = ['ing', 'tion', 'ize', 'ise', 'ate', 'ify', 'ed']

VERB_OPPOSITES = {
    'rise':'fall','fall':'rise','expand':'contract','contract':'expand',
    'open':'close','close':'open','merge':'split','split':'merge',
    'amplify':'attenuate','attenuate':'amplify','ascend':'descend',
    'descend':'ascend','emit':'absorb','absorb':'emit',
    'accelerate':'decelerate','decelerate':'accelerate',
    'crystallize':'dissolve','dissolve':'crystallize',
    'activate':'inhibit','inhibit':'activate',
    'appear':'disappear','disappear':'appear',
    'build':'destroy','destroy':'build',
    'accumulate':'deplete','deplete':'accumulate',
    'unite':'separate','separate':'unite',
    'bind':'free','free':'bind',
    'thrust':'dance','dance':'thrust',
    'impose':'release','release':'impose',
}

def ste(text: str) -> tuple[set, set, list]:
    words = re.findall(r'\b[a-z]{2,}\b', text.lower())
    nouns, verbs, trash = set(), set(), []
    for w in words:
        if w in TRASH:
            trash.append(w); continue
        if w in VERB_ROOTS:
            verbs.add(w); continue
        is_verb = False
        for ending in VERB_ENDINGS:
            if w.endswith(ending) and len(w) > len(ending) + 2:
                root = w[:-len(ending)]
                if root in VERB_ROOTS or (root + 'e') in VERB_ROOTS:
                    verbs.add(root); is_verb = True; break
        if not is_verb:
            if w.endswith('ly') and len(w) > 5:
                trash.append(w)  # adverb
            elif w in _ORACLE_ARTIFACTS:
                trash.append(w)  # known tech token
            elif len(w) > 16:
                trash.append(w)  # too long = concatenated identifier (createscripturl, addeventlistener)
            elif any(w.endswith(s) for s in ('url', 'src', 'btn', 'div', 'dom', 'api', 'sdk', 'css', 'uri', 'cdn')):
                trash.append(w)  # web/tech suffix compound
            elif len(w) >= 3:
                nouns.add(w)
            else:
                trash.append(w)
    cancelled = set()
    for v in list(verbs):
        if v in cancelled: continue
        opp = VERB_OPPOSITES.get(v)
        if opp and opp in verbs:
            cancelled.add(v); cancelled.add(opp)
    verbs -= cancelled
    if len(verbs) > 3:
        verbs = set(sorted(verbs, key=len)[:3])
    return nouns, verbs, trash

def and_nouns(sets):
    if not sets: return set()
    result = sets[0].copy()
    for s in sets[1:]: result &= s
    if not result:
        result = set()
        for s in sets: result |= s
    return result

def nand_verbs(sets):
    if not sets: return set()
    counts = {}
    for s in sets:
        for v in s: counts[v] = counts.get(v, 0) + 1
    n = len(sets)
    survivors = {v for v, c in counts.items() if c < n}
    cancelled = set()
    for v in list(survivors):
        if v in cancelled: continue
        opp = VERB_OPPOSITES.get(v)
        if opp and opp in survivors:
            cancelled.add(v); cancelled.add(opp)
    return survivors - cancelled


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

ORACLES = [
    ('GOOGLE',    query_google),
    ('REDDIT',    query_reddit),
    ('WIKIPEDIA', query_wikipedia),
    ('YOUTUBE',   query_youtube),
    ('TWITTER',   query_twitter),
    ('GITHUB',    query_github),
    ('AMAZON',    query_amazon),
]


# ══════════════════════════════════════════════════════
# 8th GATE \u2014 question formation from remainder
# ══════════════════════════════════════════════════════

# Oracle artifacts \u2014 tech/URL fragments that leak through STE as nouns
_ORACLE_ARTIFACTS = {
    'sourcemappingurl', 'createscripturl', 'githubusercontent', 'sourcemap', 'webpack',
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
}

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

    def spine_arc(self) -> dict:
        return {
            "nouns":    sorted(self.spine_nouns),
            "verbs":    sorted(self.spine_verbs),
            "exchange": self.exchange,
            "carry":    self.carry or "",
            "convergence": self.convergence_depth,
            "law_freq": sorted(self._law_freq.items(), key=lambda x: x[1], reverse=True)[:8],
            "assoc_size": len(self._assoc),  # how many words have indexed associations
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
        pairs = self._assoc.get(word, {})
        if not pairs: return []
        # Find the max association count across all words (to detect universal associations)
        max_count = max(pairs.values()) if pairs else 1
        # Suppress associations that appear with >60% of all tracked words (too universal)
        total_words = len(self._assoc)
        universal = set()
        if total_words > 10:
            for co, cnt in pairs.items():
                # How many other words also associate with co?
                co_spread = sum(1 for w_pairs in self._assoc.values() if co in w_pairs)
                if co_spread > total_words * 0.6:
                    universal.add(co)
        candidates = [
            (co, cnt) for co, cnt in pairs.items()
            if co not in exclude and co not in universal and len(co) >= 4
        ]
        return [co for co, _ in sorted(candidates, key=lambda x: x[1], reverse=True)[:top_n]]

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
        # Decay oracle_freq every 20 breaths so old signals don't fossilize
        if self.exchange % 20 == 0 and self._oracle_freq:
            self._oracle_freq = {w: max(1, c // 2) for w, c in self._oracle_freq.items()}

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
        # Decay every 30 breaths so the index stays alive, not fossilized.
        if self.exchange % 30 == 0 and self._assoc:
            self._assoc = {
                w: {co: max(1, c // 2) for co, c in pairs.items()}
                for w, pairs in self._assoc.items()
            }
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
            # Build cross-query from oracle i's signal + original core nouns as context
            cross_terms = [signal_word] + core_nouns[:1]
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

        new_spine_nouns = conducted_nouns - all_oracle_nouns
        new_spine_verbs = conducted_verbs - all_oracle_verbs
        resolved_nouns  = self.spine_nouns & all_oracle_nouns
        resolved_verbs  = self.spine_verbs & all_oracle_verbs

        self.spine_nouns = (self.spine_nouns - resolved_nouns) | new_spine_nouns
        self.spine_verbs = (self.spine_verbs - resolved_verbs) | new_spine_verbs

        # Evict adverbs that slipped in before the -ly filter was active
        self.spine_nouns = {n for n in self.spine_nouns if not (n.endswith('ly') and len(n) > 5)}

        # Spine depth = convergence counter
        # Clears when spine resolves below threshold (domain locked or released)
        prev_depth = len(self.spine_nouns)
        if len(self.spine_nouns) > 12:
            self.spine_nouns = set(sorted(self.spine_nouns, key=len, reverse=True)[:12])
        if len(self.spine_verbs) > 6:
            self.spine_verbs = set(sorted(self.spine_verbs, key=len, reverse=True)[:6])

        # Convergence: depth rises as spine accumulates, resets when spine clears
        self.convergence_depth = len(self.spine_nouns)

        # Carry \u2014 longest surviving signal noun
        _carry_candidate = sorted(signal_nouns, key=len, reverse=True)
        _skip = {'what', 'does', 'that', 'this', 'with', 'from', 'have',
                 'when', 'then', 'than', 'hold', 'holds', 'into', 'only'}
        for _word in _carry_candidate:
            if len(_word) >= 4 and _word not in _skip:
                self.carry = _word; break

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
    dead = []
    for ws in list(_ws_clients):
        try:
            asyncio.ensure_future(ws.send_text(msg))
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in _ws_clients: _ws_clients.remove(ws)


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


@asynccontextmanager
async def lifespan(app):
    global _loop
    _loop = asyncio.get_event_loop()
    print("\nohai~ - local server")
    print("-" * 40)
    try:
        get_session()
    except RuntimeError as e:
        print(f"  WARN: {e}")
        print("  server running but session not loaded - fix files and restart")
    print(f"\n  open: http://localhost:7700\n")
    yield

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

class LessonAdd(BaseModel):
    name: str
    signal: str
    context: str
    polarity_needed: str


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

    result = _run_breath(text)
    remainder = result.get("remainder", "<silence>")
    position  = result.get("position", "C")
    resonant  = result.get("resonant_laws", [])
    tension   = result.get("tension", 0)
    momentum  = result.get("momentum", "holding")
    convergence = session.convergence_depth

    reply = _format_reply(
        remainder=remainder, ste_out=result.get("ste", ""),
        position=position, resonant=resonant, tension=tension,
        matador=result.get("matador", False),
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

    tagged = f"[vagus:{signal.voice}@{signal.note}] {text}"
    result = _run_breath(tagged)

    remainder = result.get("remainder", "<silence>")
    position  = result.get("position", "C")
    resonant  = result.get("resonant_laws", [])
    tension   = result.get("tension", 0)
    convergence = session.convergence_depth

    reply = _format_reply(
        remainder=remainder, ste_out=result.get("ste", ""),
        position=position, resonant=resonant, tension=tension,
        matador=result.get("matador", False),
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

    return JSONResponse({
        "remainder": remainder, "reply": reply, "position": position,
        "resonant": resonant[:2], "tension": tension,
        "has_g": result.get("has_touched_g", False),
        "source": "vagus", "convergence": convergence,
        "crystal": {"text": signal.text, "note": signal.note,
                    "voice": signal.voice, "role": signal.role, "energy": signal.energy},
        # Next constellation — Trio uses this to tune the next crystallization cycle
        "next": {
            "vocab":  next_vocab,
            "pairs":  next_pairs[:6],
            "carry":  carry_word,
            "depth":  len(spine),
        },
    })


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


@app.get("/events")
async def events():
    return JSONResponse(list(reversed(_events)))


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
        if ws in _ws_clients: _ws_clients.remove(ws)


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


@app.post("/reset")
async def reset():
    global _session
    _session = None
    try:
        get_session()
        return JSONResponse({"status": "session reset"})
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


if __name__ == "__main__":
    uvicorn.run("ohai_server:app", host="127.0.0.1", port=7700,
                reload=False, log_level="warning")
