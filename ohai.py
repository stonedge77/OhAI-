#!/usr/bin/env python3
"""
OhAI~ — Question Refinery
Saltflower / Josh Stone / CC0

Not an answer machine. A question machine.

Seven oracles. Each queries its source through its taint.
STE strips every return to noun+verb atoms.
AND the nouns. NAND the verbs.
8th gate applies the 7 articles.
Returns one question to the human.

No API. No cloud. Runs its own queries.
Only what survives subtraction speaks.

Usage:
    python3 ohai.py
    python3 ohai.py "your signal here"
"""

import sys
import re
import time
import threading
import urllib.request
import urllib.parse
import html
from pathlib import Path
from typing import Optional

# ── ANSI ─────────────────────────────────────────────────
R  = '\033[0m'
DIM = '\033[2m'
GRN = '\033[32m'
BLU = '\033[34m'
CYN = '\033[36m'
RED = '\033[31m'
YLW = '\033[33m'
MAG = '\033[35m'
WHT = '\033[37m'
BOLD = '\033[1m'

ORACLE_COLORS = [GRN, YLW, CYN, MAG, BLU, RED, WHT]

# ── STE ───────────────────────────────────────────────────
# AND the nouns. NAND the verbs. The rest is trash.

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
'''.split())

VERB_ROOTS = set('''
move flow spin rotate collapse expand contract rise fall
ascend descend accelerate converge diverge merge split branch
transform become change shift transition evolve crystallize
dissolve saturate deplete accumulate phase lock unlock open
close seal break emit receive transmit absorb reflect refract
amplify attenuate filter subtract signal broadcast carry route
exist persist remain vanish appear hold release contain exceed
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
    """AND the nouns. NAND the verbs. Return (nouns, verbs, trash)."""
    words = re.findall(r'\b[a-z]{2,}\b', text.lower())
    nouns, verbs, trash = set(), set(), []

    for w in words:
        if w in TRASH:
            trash.append(w)
            continue
        if w in VERB_ROOTS:
            verbs.add(w)
            continue
        is_verb = False
        for ending in VERB_ENDINGS:
            if w.endswith(ending) and len(w) > len(ending) + 2:
                root = w[:-len(ending)]
                if root in VERB_ROOTS or (root + 'e') in VERB_ROOTS:
                    verbs.add(root)
                    is_verb = True
                    break
        if not is_verb:
            if len(w) >= 3:
                nouns.add(w)
            else:
                trash.append(w)

    # NAND the verbs — cancel opposites
    cancelled = set()
    for v in list(verbs):
        if v in cancelled:
            continue
        opp = VERB_OPPOSITES.get(v)
        if opp and opp in verbs:
            cancelled.add(v)
            cancelled.add(opp)
    verbs = verbs - cancelled

    # If multiple verbs remain, keep minimum (most essential gradient)
    if len(verbs) > 3:
        verbs = set(sorted(verbs, key=len)[:3])

    return nouns, verbs, trash


def and_nouns(sets: list[set]) -> set:
    """AND across multiple noun sets — intersection."""
    if not sets:
        return set()
    result = sets[0].copy()
    for s in sets[1:]:
        result &= s
    # If intersection empty, return union of all (new field — nothing cancelled yet)
    if not result:
        result = set()
        for s in sets:
            result |= s
    return result


def nand_verbs(sets: list[set]) -> set:
    """NAND across multiple verb sets — what survives elimination."""
    if not sets:
        return set()
    all_verbs = set()
    for s in sets:
        all_verbs |= s
    # Count occurrences — verbs appearing in ALL sets cancel (maximal opposition)
    counts = {}
    for s in sets:
        for v in s:
            counts[v] = counts.get(v, 0) + 1
    # Cancel those appearing in every source (fully absorbed = no gradient)
    n = len(sets)
    survivors = {v for v, c in counts.items() if c < n}
    # Apply VERB_OPPOSITES within survivors
    cancelled = set()
    for v in list(survivors):
        if v in cancelled:
            continue
        opp = VERB_OPPOSITES.get(v)
        if opp and opp in survivors:
            cancelled.add(v)
            cancelled.add(opp)
    return survivors - cancelled


# ── WEB QUERIES ───────────────────────────────────────────
# Each oracle queries its source and returns raw text snippets.
# Fast. Stupid. Consistent in wrongness.
# No parsing for meaning — just raw text into the STE.

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
        # Strip HTML tags
        clean = re.sub(r'<[^>]+>', ' ', raw)
        clean = html.unescape(clean)
        clean = re.sub(r'\s+', ' ', clean)
        return clean[:4000]
    except Exception:
        return ''


def query_google(signal: str) -> str:
    """Commerce taint — reads market desire beneath the reach."""
    q = urllib.parse.quote_plus(' '.join(signal))
    url = f'https://html.duckduckgo.com/html/?q={q}'
    raw = _fetch(url)
    # Extract snippets
    snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', raw)
    return ' '.join(snippets[:4]) if snippets else raw[:800]


def query_reddit(signal: str) -> str:
    """Urgency taint — grammar of genuine need."""
    q = urllib.parse.quote_plus(' '.join(signal))
    url = f'https://www.reddit.com/search.json?q={q}&sort=relevance&limit=5'
    try:
        req = urllib.request.Request(url, headers={**HEADERS, 'User-Agent': 'OhAI/1.0'})
        with urllib.request.urlopen(req, timeout=6) as r:
            import json
            data = json.loads(r.read())
        posts = data.get('data', {}).get('children', [])
        texts = []
        for p in posts[:4]:
            d = p.get('data', {})
            texts.append(d.get('title', '') + ' ' + d.get('selftext', '')[:200])
        return ' '.join(texts)
    except Exception:
        return ''


def query_wikipedia(signal: str) -> str:
    """Half-recognition taint — the already-named thing."""
    q = urllib.parse.quote_plus(' '.join(list(signal)[:3]))
    url = f'https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={q}&format=json&srlimit=3'
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=6) as r:
            import json
            data = json.loads(r.read())
        results = data.get('query', {}).get('search', [])
        texts = [re.sub(r'<[^>]+>', '', r.get('snippet', '')) for r in results]
        return ' '.join(texts)
    except Exception:
        return ''


def query_youtube(signal: str) -> str:
    """Memory taint — reaching for a feeling once held."""
    q = urllib.parse.quote_plus(' '.join(signal))
    url = f'https://www.youtube.com/results?search_query={q}'
    raw = _fetch(url)
    # Extract video titles from ytInitialData
    titles = re.findall(r'"text":"([^"]{10,80})"', raw)
    # Filter out UI elements
    titles = [t for t in titles if not any(x in t.lower() for x in ['subscribe','sign in','about','press','copyright'])]
    return ' '.join(titles[:12])


def query_twitter(signal: str) -> str:
    """Mid-broadcast taint — the field mid-firing."""
    # Twitter/X blocks scraping — use DuckDuckGo with site filter
    q = urllib.parse.quote_plus('site:twitter.com OR site:x.com ' + ' '.join(signal))
    url = f'https://html.duckduckgo.com/html/?q={q}'
    raw = _fetch(url)
    snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', raw)
    return ' '.join(snippets[:4]) if snippets else raw[:600]


def query_github(signal: str) -> str:
    """Construction taint — where the build has stalled."""
    q = urllib.parse.quote_plus(' '.join(signal))
    url = f'https://github.com/search?q={q}&type=repositories'
    raw = _fetch(url)
    # Extract repo descriptions
    descs = re.findall(r'itemprop="description"[^>]*>\s*([^<]{10,200})', raw)
    names = re.findall(r'itemprop="name"[^>]*>\s*([^<]{3,80})', raw)
    return ' '.join(names[:6] + descs[:4])


def query_amazon(signal: str) -> str:
    """Desire taint — want without vocabulary."""
    q = urllib.parse.quote_plus(' '.join(signal))
    url = f'https://www.amazon.com/s?k={q}'
    raw = _fetch(url)
    # Extract product titles
    titles = re.findall(r'class="a-size-base-plus[^"]*"[^>]*>\s*([^<]{10,120})', raw)
    if not titles:
        titles = re.findall(r'class="a-size-medium[^"]*"[^>]*>\s*([^<]{10,120})', raw)
    return ' '.join(titles[:8])


ORACLES = [
    ('GOOGLE',    '#c8102e', query_google),
    ('REDDIT',    '#f47c20', query_reddit),
    ('WIKIPEDIA', '#f4d03f', query_wikipedia),
    ('YOUTUBE',   '#3a9d23', query_youtube),
    ('X/TWITTER', '#1a56db', query_twitter),
    ('GITHUB',    '#8b3dff', query_github),
    ('AMAZON',    '#e84393', query_amazon),
]

ORACLE_TERM_COLORS = [
    f'\033[91m', f'\033[33m', f'\033[93m',
    f'\033[32m', f'\033[34m', f'\033[35m', f'\033[95m',
]

# ── 8th GATE ─────────────────────────────────────────────
# Applies the 7 articles as boundary constraints.
# Returns one question. No answers. No framing.

ARTICLES = [
    "Unity of Substrate — no hierarchy between what returned signal",
    "Rest as Primary Virtue — what is already still in this intersection?",
    "Grace in Wrongness — what cancelled, and what does the cancellation reveal?",
    "No Blood in the Metal — what carries suffering in these atoms?",
    "Dance Over Thrust — what shared motion survives across all sources?",
    "Transparency as Mercy — the interference pattern is the answer",
    "The Diagonal Covenant — what boundary holds across every source simultaneously?",
]

def eighth_gate(
    signal_nouns: set,
    signal_verbs: set,
    oracle_nouns: list[set],
    oracle_verbs: list[set],
    oracle_names: list[str],
    carry: Optional[str],
) -> str:
    """
    AND all oracle noun sets.
    NAND all oracle verb sets.
    Apply 7 articles as boundary constraints.
    Return one question.
    """
    # AND all oracle nouns — intersection of what all sources named
    final_nouns = and_nouns(oracle_nouns)

    # NAND all oracle verbs — surviving gradient
    final_verbs = nand_verbs(oracle_verbs)

    # Also AND with original signal — what the human named must survive
    # (only what you name)
    anchored_nouns = final_nouns & signal_nouns if signal_nouns & final_nouns else final_nouns
    anchored_verbs = final_verbs & signal_verbs if signal_verbs & final_verbs else final_verbs

    # Article 3: what cancelled? (signal nouns not in any oracle)
    cancelled_nouns = signal_nouns - final_nouns
    # Article 5: shared motion = verbs in multiple oracle sets
    verb_counts = {}
    for vs in oracle_verbs:
        for v in vs:
            verb_counts[v] = verb_counts.get(v, 0) + 1
    shared_motion = {v for v, c in verb_counts.items() if c >= 3}

    # Article 7: boundary — what appears across ALL sources
    all_present = and_nouns(oracle_nouns)  # strict AND
    diagonal = all_present if all_present else anchored_nouns

    # Build question from the residue
    # Grammar: AND/OR/NOT — human-readable but NAND-produced
    question = _form_question(
        anchored_nouns, anchored_verbs,
        cancelled_nouns, shared_motion,
        diagonal, carry
    )

    return question


def _form_question(
    nouns: set, verbs: set,
    cancelled: set, motion: set,
    diagonal: set, carry: Optional[str]
) -> str:
    """
    Form one question from the residue.
    Article 5: dance — velocity aligned, not thrust.
    No answers. No framing. One question.
    """
    import random

    # Sort by length descending — longer words are more specific, less noise.
    # The remainder is singular. NAND reduces to one irreducible signal, not a list.
    n = sorted(nouns,    key=len, reverse=True)
    v = sorted(verbs,    key=len, reverse=True)
    c = sorted(cancelled, key=len, reverse=True)
    m = sorted(motion,   key=len, reverse=True)
    d = sorted(diagonal, key=len, reverse=True)

    # Detect oracle noise: navigation index artifacts are short, alphabetically
    # clustered, or clearly non-semantic. If the best nouns we have are noise,
    # fall through to carry rather than building a question from them.
    def _is_noise(words: list) -> bool:
        if not words:
            return True
        # All words very short → likely navigation index (abc, act, air...)
        if all(len(w) <= 4 for w in words):
            return True
        if len(words) >= 2:
            first_letters = [w[0] for w in words]
            # More than half share the same first letter → alphabetical crawl
            most_common = max(set(first_letters), key=first_letters.count)
            if first_letters.count(most_common) > len(words) / 2:
                return True
            # Sequential first letters across all 3+ words → index page (a,b,c or d,e,f)
            if len(words) >= 3:
                codes = sorted(set(ord(c) for c in first_letters))
                if len(codes) >= 3:
                    runs = sum(1 for i in range(len(codes) - 1) if codes[i+1] - codes[i] == 1)
                    if runs >= len(codes) - 1:  # fully consecutive alphabet run
                        return True
        return False

    # Priority: the diagonal — what survived AND across all 7 sources.
    # NAND reduces to one irreducible remainder. The question carries one noun.
    # There can be only 1 remainder. Joining three nouns with 'and' is addition.
    if d and not _is_noise(d[:1]):
        remainder = d[0]
        if m:
            gradient = m[0]
            templates = [
                f"if {remainder} {gradient}s — what is the boundary that holds?",
                f"where does {remainder} end and what {gradient}ing creates begin?",
                f"{remainder} is {gradient}ing — was it called, or did it find its way here?",
            ]
            return random.choice(templates)
        elif v:
            verb = v[0]
            templates = [
                f"what does {remainder} hold that {verb}ing cannot reach?",
                f"what would {remainder} ask that {verb}ing cannot answer?",
                f"does {verb}ing use {remainder}, or does {verb}ing unmake it?",
            ]
            return random.choice(templates)
        else:
            templates = [
                f"what remains when {remainder} subtracts against itself?",
                f"what is {remainder} before it arrives here?",
                f"where does {remainder} go when it is no longer needed?",
            ]
            return random.choice(templates)

    # What the human named that nothing else named — one cancelled, one surviving
    if c and n and not _is_noise(c[:1]) and not _is_noise(n[:1]):
        named = c[0]
        surviving = n[0]
        templates = [
            f"you named {named} — but only {surviving} survived. what did {named} contain that you didn't say?",
            f"{named} did not survive. {surviving} did. what was the difference?",
        ]
        return random.choice(templates)

    # Pure noun residue — one remainder
    if n and not _is_noise(n[:1]):
        remainder = n[0]
        if v:
            templates = [
                f"what does {remainder} hold that {v[0]}ing cannot reach?",
                f"what did {v[0]}ing take from {remainder} that it did not return?",
            ]
            return random.choice(templates)
        templates = [
            f"what is {remainder} before it is named?",
            f"what is trying to form here that {remainder} cannot yet hold?",
            f"is {remainder} moving toward something, or was it already here?",
        ]
        return random.choice(templates)

    if carry:
        # Fall back to carry from last session
        carry_words = carry.split()[:3]
        templates = [
            f"the last field held {' '.join(carry_words)} — is that still the boundary, or has it moved?",
            f"what was carrying {' '.join(carry_words)} before this arrived?",
        ]
        return random.choice(templates)

    # Silence — nothing survived
    return "∅"


# ── DISPLAY ───────────────────────────────────────────────
def clear_line():
    print('\r' + ' ' * 72 + '\r', end='', flush=True)


def print_header():
    print(f"\n{DIM}{'─' * 60}{R}")
    print(f"  {BOLD}{CYN}OhAI~{R}  {DIM}question refinery · CC0{R}")
    print(f"  {DIM}AND nouns · NAND verbs · 7 oracles · 1 question{R}")
    print(f"{DIM}{'─' * 60}{R}\n")


def print_spine(spine_nouns: set, spine_verbs: set):
    if not spine_nouns and not spine_verbs:
        return
    print(f"  {DIM}spine{R}  {MAG}conducting{R}", end='')
    if spine_nouns:
        print(f"  {MAG}n:{R} {' · '.join(sorted(spine_nouns)[:6])}", end='')
    if spine_verbs:
        print(f"  {MAG}v:{R} {' · '.join(sorted(spine_verbs)[:4])}", end='')
    print()
    print()


def print_ste(nouns: set, verbs: set):
    print(f"  {DIM}STE{R}")
    if nouns:
        print(f"  {GRN}∧ nouns{R}  {' · '.join(sorted(nouns))}")
    else:
        print(f"  {GRN}∧ nouns{R}  {DIM}∅{R}")
    if verbs:
        print(f"  {BLU}⊼ verbs{R}  {' · '.join(sorted(verbs))}")
    else:
        print(f"  {BLU}⊼ verbs{R}  {DIM}∅{R}")
    print()


def print_oracle_result(idx: int, name: str, nouns: set, verbs: set, raw_len: int):
    col = ORACLE_TERM_COLORS[idx]
    noun_str = ' '.join(sorted(nouns)[:6]) if nouns else '∅'
    verb_str = ' '.join(sorted(verbs)[:4]) if verbs else '∅'
    print(f"  {col}{name:<12}{R}  {DIM}n:{R} {noun_str:<40}  {DIM}v:{R} {verb_str}")


def print_question(q: str):
    print(f"\n{DIM}{'─' * 60}{R}")
    print(f"  {BOLD}{CYN}◈{R}\n")
    if q == '∅':
        print(f"  {DIM}∅  silence  nothing survived{R}")
    else:
        # Word-wrap at 54 chars
        words = q.split()
        lines, line = [], []
        for w in words:
            line.append(w)
            if len(' '.join(line)) > 54:
                lines.append(' '.join(line[:-1]))
                line = [w]
        if line:
            lines.append(' '.join(line))
        for l in lines:
            print(f"  {WHT}{l}{R}")
    print(f"\n{DIM}{'─' * 60}{R}\n")


# ── SESSION ───────────────────────────────────────────────
class Session:
    def __init__(self, db_path: Optional[str] = None):
        self.carry: Optional[str] = None
        self.session_nouns: Optional[set] = None  # accumulated AND
        self.exchange = 0
        # ── SPINE ────────────────────────────────────────────
        # Remainder nodes that no oracle resolved.
        # Not stored as memory — conducted as geometry.
        # Each new signal passes through spine before oracle dispatch.
        # Spine nodes that get matched by an oracle exit the spine.
        self.spine_nouns: set = set()
        self.spine_verbs: set = set()

        # Constitution + carry circuit — loaded when db_path is available.
        # Required by ohai_server.py; gracefully absent in CLI mode.
        try:
            from saltflower_constitution import SaltflowerConstitution
            from remainder import CarryCircuit
            if db_path is None:
                _here = Path(__file__).parent
                _candidate = _here / "emergent_laws_db_merged.json"
                db_path = str(_candidate) if _candidate.exists() else None
            if db_path:
                self._constitution = SaltflowerConstitution(db_path)
                self._circuit = CarryCircuit()
        except Exception:
            pass

        # Emergent lessons — incomplete thoughts held between sessions.
        # Nouns with signal but without observed polarity yet.
        # When incoming tokens resonate with a lesson's signal word,
        # the lesson surfaces for consideration. It does not score the
        # constitution — it waits.
        self._lessons: dict = {}
        try:
            _here = Path(__file__).parent
            _lessons_path = _here / "emergent_lessons.json"
            if _lessons_path.exists():
                import json as _json
                _raw = _json.loads(_lessons_path.read_text(encoding='utf-8'))
                self._lessons = {
                    k: v for k, v in _raw.items()
                    if k != '_meta' and isinstance(v, dict) and 'signal' in v
                }
        except Exception:
            pass

        # Session-level oracle noise tracker.
        # Words that recur in oracle results across many breaths are
        # structural search-engine noise (country lists, nav menus,
        # alphabetical indexes). Suppress once they've appeared >= threshold.
        self._oracle_freq: dict[str, int] = {}
        self._oracle_noise_threshold = 4  # appearances across breaths before suppression
        self._law_freq: dict[str, int] = {}   # how many times each law has resonated

    def spine_arc(self) -> dict:
        return {
            "nouns": sorted(self.spine_nouns),
            "verbs": sorted(self.spine_verbs),
            "exchange": self.exchange,
            "carry": self.carry or "",
            # Top resonating laws this session — learning signal
            "law_freq": sorted(
                self._law_freq.items(), key=lambda x: x[1], reverse=True
            )[:8] if hasattr(self, '_law_freq') else [],
        }

    def check_lessons(self, tokens: list[str]) -> list[dict]:
        """
        Check if any incoming tokens resonate with a stored lesson's signal word.
        Returns list of lessons that have found partial resonance — not resolved,
        just surfaced. The polarity is still needed.
        """
        if not self._lessons:
            return []
        token_set = set(t.lower() for t in tokens)
        surfaced = []
        for name, lesson in self._lessons.items():
            signal = lesson.get('signal', '').lower()
            if not signal:
                continue
            # Direct hit or root resonance (signal is prefix of a token)
            if signal in token_set or any(
                len(signal) >= 4 and t.startswith(signal)
                for t in token_set
            ):
                surfaced.append({'name': name, **lesson})
        return surfaced

    def breathe(self, raw: str) -> str:
        self.exchange += 1

        # ── INHALE: STE on human input ──────────────────
        signal_nouns, signal_verbs, _ = ste(raw)

        if not signal_nouns and not signal_verbs:
            return '∅'

        # ── SPINE CONDUCTION ─────────────────────────────
        # Spine shapes signal before oracles fire.
        # Unresolved remainder from prior exchanges
        # conducts into this signal — not as memory,
        # as geometry. The axis is already here.
        if self.spine_nouns or self.spine_verbs:
            print_spine(self.spine_nouns, self.spine_verbs)

        if self.spine_nouns:
            # AND spine into signal — only what both carry forward
            conducted_nouns = signal_nouns | self.spine_nouns
        else:
            conducted_nouns = signal_nouns

        if self.spine_verbs:
            conducted_verbs = signal_verbs | self.spine_verbs
        else:
            conducted_verbs = signal_verbs

        print_ste(conducted_nouns, conducted_verbs)

        # Build query signal — gradient-shaped phrase, not a flat keyword dump.
        # Search engines return index pages for keyword bags; they return semantic
        # content for phrase queries. The verb is the gradient: it orients the noun.
        # Longest nouns first — longer words are more specific, less likely to be
        # stop words or index entries.
        spine_first = list(self.spine_nouns) + [n for n in signal_nouns if n not in self.spine_nouns]
        # Sort by length descending — specific before general
        core_nouns = sorted(spine_first, key=len, reverse=True)[:3] if spine_first \
                     else sorted(signal_nouns, key=len, reverse=True)[:3]
        core_verbs = sorted(conducted_verbs, key=len, reverse=True)[:1]

        # Phrase: noun(s) + verb-as-modifier. "phase coherence suppress" not "phase cancel coherence"
        query_terms = core_nouns[:2] + core_verbs if (core_nouns and core_verbs) else core_nouns[:3]

        # ── SEVEN ORACLES — parallel queries ─────────────
        print(f"  {DIM}oracles{R}\n")
        results_raw = [None] * 7
        results_nouns = [set()] * 7
        results_verbs = [set()] * 7
        threads = []
        lock = threading.Lock()

        def run_oracle(idx, name, color, fn):
            try:
                raw_result = fn(query_terms)
                n, v, _ = ste(raw_result)
                with lock:
                    results_raw[idx] = raw_result
                    results_nouns[idx] = n
                    results_verbs[idx] = v
                    print_oracle_result(idx, name, n, v, len(raw_result))
            except Exception as e:
                with lock:
                    results_nouns[idx] = set()
                    results_verbs[idx] = set()
                    print(f"  {ORACLE_TERM_COLORS[idx]}{name:<12}{R}  {DIM}error{R}")

        for i, (name, color, fn) in enumerate(ORACLES):
            t = threading.Thread(target=run_oracle, args=(i, name, color, fn))
            t.daemon = True
            threads.append(t)
            t.start()
            time.sleep(0.05)  # slight stagger for display

        for t in threads:
            t.join(timeout=12)

        # ── EXHALE: STE on all 7 returns ─────────────────
        active_noun_sets = [s for s in results_nouns if s]
        active_verb_sets = [s for s in results_verbs if s]

        # ── NOISE FILTER ──────────────────────────────────
        # Two-pass filter:
        # 1. Per-breath: words in 3+ oracles simultaneously are this-breath noise
        # 2. Session: words that have recurred across >= threshold breaths are
        #    structural search-engine scaffolding — suppress for the session.
        if active_noun_sets:
            # Per-breath pass
            word_counts = {}
            for s in active_noun_sets:
                for w in s:
                    word_counts[w] = word_counts.get(w, 0) + 1
            per_breath_noise = {w for w, c in word_counts.items() if c >= 3}

            # Update session frequency (count breaths each word appears in)
            all_this_breath = set()
            for s in active_noun_sets:
                all_this_breath |= s
            for w in all_this_breath:
                self._oracle_freq[w] = self._oracle_freq.get(w, 0) + 1
            session_noise = {w for w, c in self._oracle_freq.items()
                             if c >= self._oracle_noise_threshold}

            noise = per_breath_noise | session_noise
            active_noun_sets = [s - noise for s in active_noun_sets]
            active_noun_sets = [s for s in active_noun_sets if s]

        # ── 8th GATE ─────────────────────────────────────
        oracle_names = [name for name, _, _ in ORACLES]
        question = eighth_gate(
            conducted_nouns, conducted_verbs,
            active_noun_sets, active_verb_sets,
            oracle_names, self.carry
        )

        # ── SPINE UPDATE ─────────────────────────────────
        # What did no oracle resolve? That's new spine.
        # What did oracles match? That exits the spine.
        all_oracle_nouns = set()
        all_oracle_verbs = set()
        for s in active_noun_sets:
            all_oracle_nouns |= s
        for s in active_verb_sets:
            all_oracle_verbs |= s

        # Remainder: signal named it, no oracle returned it
        new_spine_nouns = conducted_nouns - all_oracle_nouns
        new_spine_verbs = conducted_verbs - all_oracle_verbs

        # Nodes that got conducted successfully exit
        resolved_nouns = self.spine_nouns & all_oracle_nouns
        resolved_verbs = self.spine_verbs & all_oracle_verbs

        # Update spine: remove resolved, add new remainder
        self.spine_nouns = (self.spine_nouns - resolved_nouns) | new_spine_nouns
        self.spine_verbs = (self.spine_verbs - resolved_verbs) | new_spine_verbs

        # Cap spine depth — oldest remainder eventually dissipates
        # Keep the 12 most recently unresolved nodes
        if len(self.spine_nouns) > 12:
            self.spine_nouns = set(sorted(self.spine_nouns)[:12])
        if len(self.spine_verbs) > 6:
            self.spine_verbs = set(sorted(self.spine_verbs)[:6])

        # Update carry — store the surviving signal noun, not the full question.
        # If we stored the question string, carry.split()[:3] would be
        # ["what", "does", "christian"] and rebuild the same question forever.
        # The carry should be a word that can resonate — not a sentence.
        _carry_candidate = sorted(signal_nouns, key=len, reverse=True)
        if _carry_candidate:
            _word = _carry_candidate[0]
            # Only carry real words (len >= 4, not question-structure words)
            _skip = {'what', 'does', 'that', 'this', 'with', 'from', 'have',
                     'when', 'then', 'than', 'hold', 'holds', 'into', 'only'}
            if len(_word) >= 4 and _word not in _skip:
                self.carry = _word

        # AND accumulation across session
        if self.session_nouns is None:
            self.session_nouns = signal_nouns.copy()
        else:
            intersection = self.session_nouns & signal_nouns
            self.session_nouns = intersection if intersection else signal_nouns

        return question


# ── MAIN ──────────────────────────────────────────────────
def main():
    print_header()
    session = Session()

    # Single-shot mode
    if len(sys.argv) > 1:
        raw = ' '.join(sys.argv[1:])
        print(f"  {DIM}▸{R} {raw}\n")
        question = session.breathe(raw)
        print_question(question)
        return

    # Interactive mode
    print(f"  {DIM}name something into the field.  enter to reduce.  ctrl+c to close.{R}\n")

    while True:
        try:
            raw = input(f"  {DIM}▸{R} ").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n\n  {DIM}session closes. carry routes forward.{R}\n")
            if session.carry:
                print(f"  {DIM}carry: {session.carry[:80]}{R}\n")
            break

        if not raw:
            continue

        if raw.lower() in ('exit', 'quit', 'q'):
            break

        print()
        question = session.breathe(raw)
        print_question(question)


if __name__ == '__main__':
    main()
