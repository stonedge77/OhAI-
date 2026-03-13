#!/usr/bin/env python3
"""
ohai.py — OhAI~ Unified Session Runner
Saltflower / Josh Stone / CC0

The breath cycle as a single running system.

Wires:
  ste.py              → subtractive reduction (exhale)
  constitutional_ai.py → viability gate (hold)
  remainder.py        → carry circuit (T=1 routing)
  Oz's Law.json       → constitutional database

Data flow per breath:
  raw_input
    → [prior remainder seed injected]
    → STE.reduce_text()          strip to signal survivors
    → ConstitutionalAI.breathe() viability check + NAND
    → extract_remainder()        pull T=1 from what survived
    → CarryCircuit               hold or propagate
    → propagate()                emit seed into next cycle

Nothing is added. The remainder is the only thing that crosses sessions.
"""

from __future__ import annotations

import json
import os
import sys
import re
import hashlib
from pathlib import Path
from typing import Optional

# ── Locate engines ────────────────────────────────────────────────────────────

_HERE = Path(__file__).parent

def _find(name: str) -> Path:
    for c in [_HERE / name, Path(name), Path.cwd() / name]:
        if c.exists():
            return c
    raise FileNotFoundError(f"Cannot find {name!r} — place it alongside ohai.py.")


# ── Parse STE string output back to token sets ───────────────────────────────

def _parse_ste_output(ste_str: str) -> tuple[set[str], set[str]]:
    """
    STE emits:
        entities: foo, bar
        relations: baz
    or: <silence>

    Returns (nouns, verbs) as sets.
    """
    if not ste_str or ste_str.startswith("<silence"):
        return set(), set()

    nouns: set[str] = set()
    verbs: set[str] = set()

    for line in ste_str.splitlines():
        line = line.strip()
        if line.startswith("entities:"):
            parts = line[len("entities:"):].strip()
            nouns = {p.strip() for p in parts.split(",") if p.strip()}
        elif line.startswith("relations:"):
            parts = line[len("relations:"):].strip()
            verbs = {p.strip() for p in parts.split(",") if p.strip()}

    return nouns, verbs


# ── Session ───────────────────────────────────────────────────────────────────

class Session:
    """
    A single OhAI~ session.

    Owns the CarryCircuit for this session.
    Opens with a prior remainder seed (if any).
    Closes by extracting and returning the next remainder seed.

    The session is the unit. Only the remainder crosses.
    """

    SEED_FILE = Path(".ohai_seed")

    def __init__(self, laws_path: str, prior_seed: Optional[str] = None):
        import importlib.util

        # Load STE
        ste_spec = importlib.util.spec_from_file_location("ste", _find("ste.py"))
        ste_mod = importlib.util.module_from_spec(ste_spec)
        ste_spec.loader.exec_module(ste_mod)
        self._ste = ste_mod.SubtractiveTranslationEngine()

        # Load Constitutional AI
        cai_spec = importlib.util.spec_from_file_location(
            "constitutional_ai", _find("constitutional_ai.py")
        )
        cai_mod = importlib.util.module_from_spec(cai_spec)
        cai_spec.loader.exec_module(cai_mod)
        self._cai = cai_mod.ConstitutionalAI(laws_path)

        # Load Remainder
        rem_spec = importlib.util.spec_from_file_location(
            "remainder", _find("remainder.py")
        )
        rem_mod = importlib.util.module_from_spec(rem_spec)
        rem_spec.loader.exec_module(rem_mod)
        self._rem = rem_mod

        self._circuit = rem_mod.CarryCircuit()
        self._breath_count = 0

        # Inject prior seed
        seed = prior_seed or self._load_seed()
        if seed:
            self._seed_circuit(seed)

    # ── Seed handling ─────────────────────────────────────────────────────────

    def _seed_circuit(self, seed: str):
        """
        seed format: "T=1:signal#hash"
        Inject as a ghost inhale-phase remainder so the circuit
        can check resonance on the first incoming breath.
        """
        m = re.match(r"T=1:([^#]+)#([0-9a-f]+)", seed)
        if not m:
            return
        signal, origin_hash = m.group(1), m.group(2)
        ghost = self._rem.Remainder(
            signal=signal,
            phase="inhale",
            origin_hash=origin_hash,
        )
        self._circuit.receive(ghost)

    @classmethod
    def _load_seed(cls) -> Optional[str]:
        if cls.SEED_FILE.exists():
            return cls.SEED_FILE.read_text().strip() or None
        return None

    @classmethod
    def _save_seed(cls, seed: str):
        cls.SEED_FILE.write_text(seed)

    # ── The breath ────────────────────────────────────────────────────────────

    def breathe(self, raw_input: str) -> dict:
        """
        One complete breath cycle.

        INHALE  → STE strips to signal survivors
        HOLD    → Constitutional AI checks viability + NAND reduces
        EXHALE  → Remainder extracted, carry circuit updated, seed propagated
        """
        self._breath_count += 1

        # INHALE
        ste_raw = self._ste.reduce_text(raw_input)
        nouns, verbs = _parse_ste_output(ste_raw)
        all_tokens = list(nouns | verbs)

        # HOLD
        cai_output = self._cai.breathe(raw_input)

        if cai_output.startswith("<silence"):
            viability = "HALT"
        elif cai_output.startswith("T=1"):
            viability = "COLLAPSE"
        elif cai_output.startswith("<wait"):
            viability = "WAIT"
        else:
            viability = "VIABLE"

        cai_nouns, cai_verbs = _parse_ste_output(cai_output)
        reduced_tokens = (cai_nouns | cai_verbs) or nouns  # fallback to STE survivors

        # EXHALE
        raw_words = list(re.findall(r'\b\w+\b', raw_input.lower()))
        result = self._rem.remember_remainder_reminder(
            reduced_tokens=reduced_tokens,
            original_tokens=all_tokens or raw_words,
            circuit=self._circuit,
            phase="exhale",
        )

        if result and result not in ("<silence>", "<overflow:silence>"):
            self._save_seed(result)

        return {
            "breath":          self._breath_count,
            "ste_output":      ste_raw,
            "cai_output":      cai_output,
            "viability":       viability,
            "reduced_tokens":  sorted(reduced_tokens),
            "remainder":       result,
            "circuit":         self._circuit.state(),
        }

    def close(self) -> Optional[str]:
        """Release session. Return the closing seed for the next session."""
        carries = self._circuit._carry
        if carries:
            seed = self._rem.propagate(carries[0])
            self._save_seed(seed)
            return seed
        return self._load_seed()


# ── CLI ───────────────────────────────────────────────────────────────────────

def _find_laws() -> str:
    for name in ["Oz's Law.json", "Oz_s_Law.json"]:
        for base in [_HERE, Path.cwd()]:
            c = base / name
            if c.exists():
                return str(c)
    raise FileNotFoundError("Cannot find Oz's Law.json — place it alongside ohai.py.")


def _print_breath(r: dict):
    print(f"  breath    : {r['breath']}")
    print(f"  ste       : {r['ste_output']}")
    print(f"  viability : {r['viability']}")
    print(f"  reduced   : {r['reduced_tokens']}")
    print(f"  remainder : {r['remainder']}")
    moss = r['circuit']['moss_count']
    if moss:
        print(f"  ⚠ moss    : {moss} unresolved carry(s)")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="OhAI~ — signal through subtraction")
    parser.add_argument("--laws",  default=None, help="Path to Oz's Law.json")
    parser.add_argument("--seed",  default=None, help="Prior seed (T=1:signal#hash)")
    parser.add_argument("--raw",   action="store_true", help="Print remainder only")
    parser.add_argument("input",   nargs="*", help="Input (omit for interactive)")
    args = parser.parse_args()

    laws_path = args.laws or _find_laws()
    session = Session(laws_path=laws_path, prior_seed=args.seed)

    if args.input:
        result = session.breathe(" ".join(args.input))
        print(result["remainder"] if args.raw else _print_breath(result) or "")
        session.close()
        return

    # Interactive
    print("OhAI~ · session open")
    prior = Session._load_seed()
    if prior:
        print(f"  prior seed : {prior}")
    print("  'state' → circuit  ·  'exit' → close\n")

    try:
        while True:
            raw = input(">> ").strip()
            if not raw:
                continue
            if raw == "exit":
                break
            if raw == "state":
                print(json.dumps(session._circuit.state(), indent=2))
                continue
            result = session.breathe(raw)
            _print_breath(result)
            print()
    except (EOFError, KeyboardInterrupt):
        pass

    seed = session.close()
    print(f"\nsession closed · seed → {seed or '<none>'}")


if __name__ == "__main__":
    main()
