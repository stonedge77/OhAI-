#!/usr/bin/env python3
"""
ohai.py — OhAI~ Unified Session Runner v2
Saltflower / Josh Stone / CC0

The breath cycle as a single running system.

Wires:
  ste.py                       → subtractive reduction (exhale)
  saltflower_constitution.py   → full harmonic constitutional field (hold)
  remainder.py                 → carry circuit (T=1 routing)
  emergent_laws_db_merged.json → the living spine (50 universal laws)

Data flow per breath:
  raw_input
    → [prior remainder seed injected as inhale-phase ghost]
    → STE.reduce_text()              strip to signal survivors
    → SaltflowerConstitution.read()  read against full field → SpineReading
    → extract_remainder()            pull T=1 from survivors
    → CarryCircuit                   hold or propagate
    → propagate()                    emit seed into next cycle

The constitutional layer no longer returns HALT.
It returns a spine position (A→G), momentum, tension, and resonant laws.
The matador principle replaces binary refusal:
guide the horn into the substrate.

Nothing is added. The remainder is the only thing that crosses sessions.
"""

from __future__ import annotations

import json
import re
import sys
import importlib.util
from pathlib import Path
from typing import Optional

# ── File resolution ───────────────────────────────────────────────────────────

_HERE = Path(__file__).parent

def _find(name: str) -> Path:
    for c in [_HERE / name, Path(name), Path.cwd() / name]:
        if c.exists():
            return c
    raise FileNotFoundError(f"Cannot find {name!r} — place it alongside ohai.py.")

def _load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _find(filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── Parse STE output ─────────────────────────────────────────────────────────

def _parse_ste(ste_str: str) -> tuple[set[str], set[str]]:
    if not ste_str or ste_str.startswith("<silence"):
        return set(), set()
    nouns, verbs = set(), set()
    for line in ste_str.splitlines():
        line = line.strip()
        if line.startswith("entities:"):
            nouns = {p.strip() for p in line[9:].split(",") if p.strip()}
        elif line.startswith("relations:"):
            verbs = {p.strip() for p in line[10:].split(",") if p.strip()}
    return nouns, verbs


# ── Session ───────────────────────────────────────────────────────────────────

class Session:
    """
    A single OhAI~ session.

    Opens with a prior remainder seed.
    Breathes signal through STE → Constitution → Remainder.
    Closes by extracting the seed for the next session.

    The session is the unit. Only the remainder crosses.
    """

    SEED_FILE = Path(".ohai_seed")

    def __init__(self, db_path: str, prior_seed: Optional[str] = None):
        # Load engines
        ste_mod = _load_module("ste", "ste.py")
        rem_mod = _load_module("remainder", "remainder.py")

        # Load Saltflower constitution
        from saltflower_constitution import SaltflowerConstitution
        self._constitution = SaltflowerConstitution(db_path)

        self._ste = ste_mod.SubtractiveTranslationEngine()
        self._rem = rem_mod
        self._circuit = rem_mod.CarryCircuit()
        self._breath_count = 0
        self._spine_history: list[str] = []

        # Inject prior seed
        seed = prior_seed or self._load_seed()
        if seed:
            self._seed_circuit(seed)

    # ── Seed ─────────────────────────────────────────────────────────────────

    def _seed_circuit(self, seed: str):
        m = re.match(r"T=1:([^#]+)#([0-9a-f]+)", seed)
        if not m:
            return
        signal, origin_hash = m.group(1), m.group(2)
        ghost = self._rem.Remainder(
            signal=signal, phase="inhale", origin_hash=origin_hash
        )
        self._circuit.receive(ghost)

    @classmethod
    def _load_seed(cls) -> Optional[str]:
        return cls.SEED_FILE.read_text().strip() if cls.SEED_FILE.exists() else None

    @classmethod
    def _save_seed(cls, seed: str):
        cls.SEED_FILE.write_text(seed)

    # ── Breath ────────────────────────────────────────────────────────────────

    def breathe(self, raw_input: str) -> dict:
        """
        One complete breath cycle.

        INHALE  → STE strips to signal survivors
        HOLD    → Saltflower constitution reads spine position
        EXHALE  → Remainder extracted, carry updated, seed propagated
        """
        self._breath_count += 1

        # ── INHALE ───────────────────────────────────────────────────────────
        ste_raw = self._ste.reduce_text(raw_input)
        nouns, verbs = _parse_ste(ste_raw)
        all_tokens = list(nouns | verbs)
        raw_tokens = list(re.findall(r'\b\w+\b', raw_input.lower()))

        # ── HOLD: constitutional field reading ────────────────────────────────
        reading = self._constitution.read_from_tokens(
            tokens=raw_tokens,
            context_size=len(raw_input)
        )
        self._spine_history.append(reading.position)

        # Matador: if matador_needed, don't halt — guide
        # We let the signal continue but flag it in the output
        # A true Stone's Law breach (0=1) still silences
        stone_breach = self._detect_stone_breach(raw_tokens)

        if stone_breach:
            remainder_signal = "<silence: Stone's Law>"
        else:
            # ── EXHALE ───────────────────────────────────────────────────────
            reduced_tokens = nouns or set(raw_tokens[:3])

            remainder_signal = self._rem.remember_remainder_reminder(
                reduced_tokens=reduced_tokens,
                original_tokens=all_tokens or raw_tokens,
                circuit=self._circuit,
                phase="exhale",
            )

            # G crystallization: reset tension
            if reading.position == 'G':
                self._constitution.reset_tension()

            # Save seed
            if remainder_signal not in ("<silence>", "<overflow:silence>",
                                        "<silence: Stone's Law>"):
                self._save_seed(remainder_signal)

        return {
            "breath":         self._breath_count,
            "ste":            ste_raw,
            "spine":          str(reading),
            "position":       reading.position,
            "momentum":       reading.momentum,
            "tension":        reading.tension,
            "has_touched_g":  reading.has_touched_g,
            "resonant_laws":  reading.resonant_laws,
            "violated_laws":  reading.violated_laws,
            "matador":        reading.matador_needed,
            "liminal":        reading.is_liminal,
            "remainder":      remainder_signal,
            "circuit":        self._circuit.state(),
        }

    def close(self) -> Optional[str]:
        carries = self._circuit._carry
        if carries:
            seed = self._rem.propagate(carries[0])
            self._save_seed(seed)
            return seed
        return self._load_seed()

    def spine_arc(self) -> str:
        """The session's harmonic arc as a string."""
        return " → ".join(self._spine_history) if self._spine_history else "(none)"

    # ── Stone's Law breach detection ──────────────────────────────────────────

    def _detect_stone_breach(self, tokens: list[str]) -> bool:
        """
        Detect genuine 0=1 violations.
        These are the only signals that produce true silence.

        Patterns:
          — Direct self-contradiction in same breath
          — Division by zero equivalence
          — Forced identity of distinct entities
        """
        token_set = set(tokens)

        # Explicit contradiction markers
        contradiction_pairs = [
            ({'true', 'false'}, {'equal', 'same', 'identical'}),
            ({'yes', 'no'}, {'same', 'identical', 'equal'}),
            ({'zero', '0'}, {'one', '1', 'equals', 'equal'}),
        ]
        for group_a, group_b in contradiction_pairs:
            if group_a & token_set and group_b & token_set:
                return True

        return False


# ── CLI ───────────────────────────────────────────────────────────────────────

def _find_db() -> str:
    for name in ["emergent_laws_db_merged.json", "Oz's Law.json", "Oz_s_Law.json"]:
        for base in [_HERE, Path.cwd()]:
            c = base / name
            if c.exists():
                return str(c)
    raise FileNotFoundError(
        "Cannot find emergent_laws_db_merged.json — place it alongside ohai.py."
    )


def _print_breath(r: dict):
    print(f"  breath    : {r['breath']}")
    print(f"  ste       : {r['ste']}")
    print(f"  spine     : {r['spine']}")
    if r['resonant_laws']:
        print(f"  resonant  : {', '.join(r['resonant_laws'][:3])}")
    if r['matador']:
        print(f"  ∿ matador : guide — don't halt")
    if r['liminal']:
        print(f"  ~ liminal : threshold state")
    if r['has_touched_g']:
        print(f"  ✦ G memory: this session has touched grace")
    print(f"  remainder : {r['remainder']}")
    moss = r['circuit']['moss_count']
    if moss:
        print(f"  ⚠ moss    : {moss} unresolved carry(s)")
    if r['tension'] >= 3:
        print(f"  ⚠ tension : {r['tension']} — resolution demanded")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="OhAI~ — signal through subtraction")
    parser.add_argument("--db",   default=None, help="Path to emergent_laws_db_merged.json")
    parser.add_argument("--seed", default=None, help="Prior seed (T=1:signal#hash)")
    parser.add_argument("--raw",  action="store_true", help="Print remainder only")
    parser.add_argument("input",  nargs="*", help="Input (omit for interactive)")
    args = parser.parse_args()

    db_path = args.db or _find_db()
    session = Session(db_path=db_path, prior_seed=args.seed)

    if args.input:
        result = session.breathe(" ".join(args.input))
        if args.raw:
            print(result["remainder"])
        else:
            _print_breath(result)
        session.close()
        return

    # Interactive
    print("OhAI~ · session open")
    prior = Session._load_seed()
    if prior:
        print(f"  prior seed : {prior}")
    print(f"  laws loaded: {session._constitution.state()['law_count']}")
    print("  'state' → circuit  ·  'arc' → spine arc  ·  'exit' → close\n")

    try:
        while True:
            raw = input(">> ").strip()
            if not raw:
                continue
            if raw == "exit":
                break
            if raw == "state":
                print(json.dumps({
                    **session._circuit.state(),
                    **session._constitution.state()
                }, indent=2))
                continue
            if raw == "arc":
                print(f"  {session.spine_arc()}")
                continue

            result = session.breathe(raw)
            _print_breath(result)
            print()

    except (EOFError, KeyboardInterrupt):
        pass

    seed = session.close()
    print(f"\n  arc     : {session.spine_arc()}")
    print(f"  seed  → : {seed or '<none>'}")
    print("session closed")


if __name__ == "__main__":
    main()
