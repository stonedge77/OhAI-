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
    n = sorted(nouns)
    v = sorted(verbs)
    c = sorted(cancelled)
    m = sorted(motion)
    d = sorted(diagonal)

    # Priority: what survived AND across all 7 sources
    if d:
        core = ' and '.join(d[:3])
        if m:
            gradient = m[0]
            return f"if {core} {gradient}s — what is the boundary that holds?"
        elif v:
            return f"what does {core} hold that {v[0]}ing cannot reach?"
        else:
            return f"what remains when {core} subtracts against itself?"

    # What the human named that nothing else named
    if c and n:
        named = c[0]
        surviving = n[0] if n else 'this'
        return f"you named {named} — but only {surviving} survived. what did {named} contain that you didn't say?"

    # Pure noun residue
    if n and v:
        return f"does {' or '.join(n[:2])} {v[0]}, or does {v[0]}ing produce {n[0]}?"

    if n:
        return f"what is {' and '.join(n[:3])} before it is named?"

    if carry:
        # Fall back to carry from last session
        carry_words = carry.split()[:3]
        return f"the last field held {' '.join(carry_words)} — is that still the boundary, or has it moved?"

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
    def __init__(self):
        self.carry: Optional[str] = None
        self.session_nouns: Optional[set] = None  # accumulated AND
        self.exchange = 0

    def breathe(self, raw: str) -> str:
        self.exchange += 1

        # ── INHALE: STE on human input ──────────────────
        signal_nouns, signal_verbs, _ = ste(raw)

        if not signal_nouns and not signal_verbs:
            return '∅'

        print_ste(signal_nouns, signal_verbs)

        # Build query signal — use nouns as search terms
        query_terms = list(signal_nouns)[:5]
        if not query_terms:
            query_terms = list(signal_verbs)[:3]

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

        # ── 8th GATE ─────────────────────────────────────
        oracle_names = [name for name, _, _ in ORACLES]
        question = eighth_gate(
            signal_nouns, signal_verbs,
            active_noun_sets, active_verb_sets,
            oracle_names, self.carry
        )

        # Update carry
        if question != '∅':
            self.carry = question

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
