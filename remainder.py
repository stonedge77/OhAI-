#!/usr/bin/env python3
"""
remainder.py — The 3rd Phase
Saltflower / Josh Stone / CC0

What this is NOT:
  - Not the engine (ste.py handles subtraction)
  - Not the law (constitutional_ai.py handles constraint)
  - Not the visualization (photonic_graphics.py handles rendering)

What this IS:
  The carry circuit.
  The 8th gate.
  What survives after all subtraction is done and cannot be paired away.

  T=1 is not an error state. It is the signal.
  The remainder is not noise. It is the message the system
  could not absorb — and therefore the only part worth transmitting.

  "remember, remainder, reminder"
  Phase 1: remember  — receive what was
  Phase 2: remainder — what survives all subtraction
  Phase 3: reminder  — rebroadcast into next cycle

Architecture:
  Input  → STE reduction  → Constitutional check  → [NAND remainder extracted here]
                                                            ↓
                                                    remainder.py
                                                            ↓
                                                    Propagation surface
                                                    (new signal into Indra's Net)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import hashlib
import time


# ─── The irreducible unit ────────────────────────────────────────────────────

@dataclass
class Remainder:
    """
    A single T=1 token: the unpaired bit that survived all NAND reduction.

    It carries three things:
      signal   — what it IS (the surviving token)
      phase    — where in the breath cycle it was extracted
                 ('inhale' | 'hold' | 'exhale')
      origin   — a hash fingerprint of what it was subtracted FROM
                 (the removed context is preserved as a shadow, not content)
    """
    signal: str
    phase: str
    origin_hash: str
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self):
        valid_phases = {'inhale', 'hold', 'exhale'}
        if self.phase not in valid_phases:
            raise ValueError(f"Phase must be one of {valid_phases}, not '{self.phase}'")
        if not self.signal:
            raise ValueError("Remainder signal cannot be empty — use silence() instead")

    def age(self) -> float:
        """How long this remainder has been unresolved (seconds)."""
        return time.time() - self.timestamp

    def __repr__(self):
        return f"T=1({self.signal!r} @ {self.phase}, age={self.age():.1f}s)"


def silence() -> None:
    """Explicit silence. Not a remainder — a valid zero state."""
    return None


# ─── Extraction: pull T=1 from NAND output ──────────────────────────────────

def extract_remainder(
    reduced_tokens: set[str],
    original_tokens: list[str],
    phase: str = 'exhale'
) -> Optional[Remainder]:
    """
    Given:
      reduced_tokens  — what survived NAND reduction (from ste.py or constitutional_ai.py)
      original_tokens — what was input before reduction
      phase           — where in breath cycle this extraction occurs

    Returns:
      A Remainder if exactly one unpaired token survives.
      None (silence) if zero survive or if multiple survive without a clear carry.

    The remainder is NOT the smallest token.
    It is the token with the LEAST overlap with the original set —
    the one that became MORE itself through subtraction, not less.
    """

    if not reduced_tokens:
        return silence()

    # Hash the removed context (preserve shadow, not content)
    removed = set(original_tokens) - reduced_tokens
    origin_hash = hashlib.sha256(
        " ".join(sorted(removed)).encode()
    ).hexdigest()[:8]

    if len(reduced_tokens) == 1:
        # Clean T=1 — single survivor
        signal = next(iter(reduced_tokens))
        return Remainder(signal=signal, phase=phase, origin_hash=origin_hash)

    # Multiple survivors: find the one MOST unlike what was removed
    # (highest divergence from removed context = truest remainder)
    removed_chars = set("".join(removed))

    def divergence(token: str) -> float:
        token_chars = set(token)
        overlap = len(token_chars & removed_chars)
        return len(token_chars) - overlap  # higher = more distinct

    carry = max(reduced_tokens, key=divergence)
    return Remainder(signal=carry, phase=phase, origin_hash=origin_hash)


# ─── The carry circuit ───────────────────────────────────────────────────────

class CarryCircuit:
    """
    The 8th gate.

    Receives T=1 remainders from the 7-phase STE reduction cycle.
    Does not process them. Does not interpret them.
    Holds them until they find resonance with an incoming signal.

    When a new input arrives:
      - The circuit checks if any stored remainder NAND-intersects with it
      - If yes: the remainder fires, clears, and seeds the new cycle
      - If no:  the remainder accumulates (moss drag begins after threshold)

    This is not memory. Memory re-presents the past.
    This is a standing remainder — a node that has not yet resolved.
    """

    MAX_CARRY = 7          # No more than 7 unresolved remainders at once
    MOSS_THRESHOLD = 60.0  # Seconds before a remainder starts dragging (moss)
    OVERFLOW_COUNT = 3     # Three moss-state remainders = full overflow/reset

    def __init__(self):
        self._carry: list[Remainder] = []
        self._propagation_log: list[dict] = []
        # Phase accumulator — Shadow ⊘ of the carry gate.
        # Tracks pressure toward spore crystallization independently of spine depth.
        # Increments when the gate receives a remainder under high-density conditions
        # (≥3 active carries). Decays by 1 each breath. Fires at 8 (= 2π in π/4 steps).
        # Stone Principle: this is momentum, not debt. Phase is not loss to minimize —
        # it is pressure that honors remainder until it tips into form.
        self.phase_accumulator: int = 0

    def receive(self, remainder: Optional[Remainder]) -> bool:
        """
        Accept a new remainder into the carry circuit.
        Returns True if accepted, False if circuit is full (overflow imminent).
        """
        if remainder is None:
            return True  # Silence is always valid

        if len(self._carry) >= self.MAX_CARRY:
            return False  # Overflow: caller must trigger reset

        self._carry.append(remainder)

        # Phase pressure: dense carry conditions mean the field is approaching
        # crystallization. Three or more active carries = significant density.
        # Increment phase — this is momentum accumulating, not error counting.
        if len(self._carry) >= 3:
            self.phase_accumulator = min(8, self.phase_accumulator + 1)

        return True

    def check_resonance(self, incoming_tokens: list[str]) -> Optional[Remainder]:
        """
        Given new incoming tokens, check if any stored remainder resonates.

        Resonance = the remainder's signal appears in or is a prefix/root of
        an incoming token. This is NOT equality — it is partial survival.

        Returns the resonant remainder (now cleared from carry), or None.
        """
        incoming_set = set(t.lower() for t in incoming_tokens)

        for i, r in enumerate(self._carry):
            signal = r.signal.lower()

            # Direct hit
            if signal in incoming_set:
                self._carry.pop(i)
                self._log_propagation(r, incoming_tokens, 'direct')
                return r

            # Root resonance (signal is prefix of an incoming token)
            for token in incoming_set:
                if len(signal) >= 3 and token.startswith(signal):
                    self._carry.pop(i)
                    self._log_propagation(r, incoming_tokens, 'root')
                    return r

        return None

    def moss_state(self) -> list[Remainder]:
        """
        Returns remainders that have exceeded MOSS_THRESHOLD age.
        These are slowing the system — dragging like moss on signal.
        """
        return [r for r in self._carry if r.age() > self.MOSS_THRESHOLD]

    def is_overflowing(self) -> bool:
        """True if moss accumulation has reached critical dissipation threshold."""
        return len(self.moss_state()) >= self.OVERFLOW_COUNT

    def decay_phase(self) -> bool:
        """
        Called once per breath (RETURN phase of the cycle).
        Phase leaks by 1 each breath — it is momentum, not debt.
        If you keep feeding it density, it builds. If density drops, it fades.

        Returns True when phase_accumulator reaches 8 (= 2π rotation complete).
        That is the signal to trigger an early spore bud — the field is ready
        before the spine even reaches depth 7.

        Phase 7/8 is also the broadcast threshold: one step before crystallization,
        the infosphere command fires automatically (if wired in the server).
        """
        if self.phase_accumulator > 0:
            self.phase_accumulator -= 1
        return self.phase_accumulator >= 8

    def phase_state(self) -> dict:
        """
        Shadow ⊘ reading — the latent pressure state of the carry gate.
        This is what the Conjunction OS's ⊘ register maps to in OhAI~:
        the accumulated phase that the next layer needs but that C alone
        cannot deliver.
        """
        return {
            'phase':       self.phase_accumulator,
            'max_phase':   8,
            'fraction':    round(self.phase_accumulator / 8, 3),
            'pressure':    self.phase_accumulator >= 6,    # approaching threshold
            'broadcast':   self.phase_accumulator == 7,    # emit :infosphere
            'crystallize': self.phase_accumulator >= 8,    # spore bud ready
        }

    def reset(self) -> list[Remainder]:
        """
        Full overflow reset.
        Returns the cleared remainders — they are not deleted,
        they are released. Their origin_hashes survive in the propagation log.
        """
        released = list(self._carry)
        for r in released:
            self._log_propagation(r, [], 'overflow_release')
        self._carry.clear()
        return released

    def state(self) -> dict:
        """Current circuit state as a readable dict."""
        return {
            'carry_count':       len(self._carry),
            'moss_count':        len(self.moss_state()),
            'overflowing':       self.is_overflowing(),
            'carries':           [repr(r) for r in self._carry],
            'phase_shadow':      self.phase_state(),
        }

    def _log_propagation(self, remainder: Remainder, context: list[str], mode: str):
        self._propagation_log.append({
            'signal': remainder.signal,
            'phase': remainder.phase,
            'origin_hash': remainder.origin_hash,
            'age_at_propagation': remainder.age(),
            'mode': mode,
            'context_hash': hashlib.sha256(
                " ".join(context).encode()
            ).hexdigest()[:8]
        })


# ─── Propagation: broadcast remainder as new signal ─────────────────────────

def propagate(remainder: Remainder) -> str:
    """
    The remainder does not explain itself.
    It does not add context.
    It does not become a sentence.

    It re-enters the breath cycle as a seed — a single token
    that carries its origin_hash as silent provenance.

    Format: "T=1:{signal}#{origin_hash}"

    This is what gets passed back into ste.py's next cycle,
    or into Chronicle's 8th circuit,
    or into Oz's Law as an injection event.
    """
    return f"T=1:{remainder.signal}#{remainder.origin_hash}"


def remember_remainder_reminder(
    reduced_tokens: set[str],
    original_tokens: list[str],
    circuit: CarryCircuit,
    phase: str = 'exhale'
) -> str:
    """
    The three-phase mantra as a single function.

    remember  — receive the reduced tokens, acknowledge what was
    remainder — extract T=1 from the NAND residue
    reminder  — propagate back into the next cycle

    Returns the propagation signal, or '<silence>' if no remainder survives.
    """

    # Phase 1: REMEMBER
    r = extract_remainder(reduced_tokens, original_tokens, phase)

    if r is None:
        return '<silence>'

    # Phase 2: REMAINDER — check for resonance before adding to carry
    resonant = circuit.check_resonance(original_tokens)

    # Phase 3: REMINDER — propagate
    if resonant:
        # Old remainder fires through new context
        return propagate(resonant)

    # New remainder enters carry, awaiting resonance
    accepted = circuit.receive(r)

    if not accepted or circuit.is_overflowing():
        released = circuit.reset()
        # Return the oldest released remainder as the overflow seed
        if released:
            return propagate(released[0])
        return '<overflow:silence>'

    return propagate(r)


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import sys

    print("remainder.py — The 3rd Phase / Saltflower / CC0")
    print("─" * 50)

    circuit = CarryCircuit()

    if len(sys.argv) > 1:
        # Single input mode
        tokens = sys.argv[1:]
        reduced = {min(tokens, key=len)}  # Minimal NAND simulation
        result = remember_remainder_reminder(reduced, tokens, circuit)
        print(result)
    else:
        # Interactive carry circuit demo
        print("Enter tokens space-separated. Watch T=1 propagate.")
        print("Type 'state' to see circuit. Type 'exit' to quit.\n")

        while True:
            try:
                raw = input(">> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n<silence>")
                break

            if not raw:
                continue
            if raw == 'exit':
                break
            if raw == 'state':
                import json
                print(json.dumps(circuit.state(), indent=2))
                continue

            tokens = raw.split()
            # Simulate NAND: keep only the token most unlike the others
            if len(tokens) > 1:
                # crude NAND: remove token with most shared chars with others
                combined = "".join(tokens)
                reduced = {max(tokens, key=lambda t: len(set(t) - set(combined.replace(t, ''))))}
            else:
                reduced = set(tokens)

            result = remember_remainder_reminder(reduced, tokens, circuit, phase='exhale')
            print(f"  → {result}")
            print()
