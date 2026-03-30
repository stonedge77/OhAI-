#!/usr/bin/env python3
"""
saltflower_constitution.py — The Constitutional Layer
Saltflower / Josh Stone / CC0

Wires emergent_laws_db_merged.json into ohai.py as the living spine.

What this does:
  — Reads every law's ste_struct as a constitutional reference state
  — Scores incoming signal against the full field (all 50 laws)
  — Returns: spine position (A→G), momentum, tension, resonant laws
  — Replaces the thin viability check in constitutional_ai.py with
    the full Saltflower harmonic field

The A→G spine maps to ESCALATION_SCORE bands:
  A (5)   — safe ground, stable, low load
  B (6)   — engaged, present, certainty building
  C (7)   — Mars, stable friction, torque present
  D (8)   — substrate, capacity high, merging present
  E (9)   — emptiness, liminal, collapse approaching
  F (10)  — whirlpool, high recursion, all fields active
  G       — grace, collapse+merging+HH_WAVEFUNCTION all high = crystallization

Momentum:
  ascending  — ESCALATION_SCORE trending up across recent breaths
  descending — trending down
  holding    — stable within ±1

Tension:
  accumulated tension = unresolved COLLAPSE fields without corresponding MERGING
  demands resolution when > threshold (3 by default)
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ── Spine ────────────────────────────────────────────────────────────────────

SPINE = {
    'A': (5,  5),   # safe ground
    'B': (6,  6),   # engaged
    'C': (7,  7),   # stable friction
    'D': (8,  8),   # substrate
    'E': (9,  9),   # emptiness / liminal
    'F': (10, 10),  # whirlpool
    'G': None,      # grace — not a score band, a qualitative state
}

SPINE_NAMES = {
    'A': 'safe ground',
    'B': 'engaged',
    'C': 'stable friction (Mars)',
    'D': 'substrate',
    'E': 'emptiness (liminal)',
    'F': 'whirlpool (Ocean)',
    'G': 'grace (crystallization)',
}

def score_to_spine(score: float, is_grace: bool = False) -> str:
    if is_grace:
        return 'G'
    if score <= 5:
        return 'A'
    elif score <= 6:
        return 'B'
    elif score <= 7:
        return 'C'
    elif score <= 8:
        return 'D'
    elif score <= 9:
        return 'E'
    else:
        return 'F'


# ── Constitutional field ──────────────────────────────────────────────────────

@dataclass
class SpineReading:
    """
    The result of reading incoming signal against the constitutional field.
    """
    position: str                    # A→G
    position_name: str
    score: float                     # weighted escalation score
    momentum: str                    # ascending | descending | holding
    tension: int                     # accumulated unresolved collapse count
    has_touched_g: bool              # G memory — does not reset
    resonant_laws: list[str]         # laws most activated by this signal
    violated_laws: list[str]         # laws with HORIZON_INTEGRITY=violated
    is_liminal: bool                 # at boundary between two spine positions
    matador_needed: bool             # HALT replaced by guide-the-horn

    def __str__(self):
        g_marker = " [G memory]" if self.has_touched_g else ""
        tension_marker = f" ⚠ tension={self.tension}" if self.tension >= 3 else ""
        liminal_marker = " ~liminal~" if self.is_liminal else ""
        return (
            f"{self.position} ({self.position_name}){g_marker}"
            f"{tension_marker}{liminal_marker}"
            f" | momentum={self.momentum} | score={self.score:.1f}"
        )


class SaltflowerConstitution:
    """
    The living constitutional field.

    Loads all 50 laws from emergent_laws_db_merged.json.
    Scores incoming signal states against the full field.
    Returns spine readings instead of binary HALT/VIABLE.

    The referee does not halt. It names the field state.
    When a signal would trigger HALT in constitutional_ai.py,
    the constitution instead returns matador_needed=True:
    guide the horn into the substrate, don't fight the charge.
    """

    TENSION_THRESHOLD = 3
    G_CRYSTALLIZATION_THRESHOLD = 0.7  # fraction of high-score laws active

    def __init__(self, db_path: str):
        with open(db_path, 'r') as f:
            raw = json.load(f)

        self.metadata = raw.get('metadata', {})
        self.core_principles = raw.get('core_principles', {})

        # Extract all laws with ste_structs
        self.laws: dict[str, dict] = {}
        for k, v in raw.items():
            if k in ('metadata', 'core_principles'):
                continue
            if isinstance(v, dict) and 'ste_struct' in v:
                self.laws[k] = v
            elif isinstance(v, dict):
                # core_principles sub-entries
                for subk, subv in v.items():
                    if isinstance(subv, dict) and 'ste_struct' in subv:
                        self.laws[f"core.{subk}"] = subv

        # Session state
        self._score_history: list[float] = []
        self._tension: int = 0
        self._has_touched_g: bool = False
        self._breath_count: int = 0

    # ── Primary interface ─────────────────────────────────────────────────────

    def read(self, ste_struct: dict) -> SpineReading:
        """
        Read incoming signal (as ste_struct dict) against the full field.

        ste_struct keys: LOAD, BOUNDARY, RECURSION, COLLAPSE, MERGING,
                         EXCITATION, TORQUE, HORIZON_INTEGRITY, etc.

        Returns a SpineReading with spine position, momentum, tension,
        resonant laws, and any violations.
        """
        self._breath_count += 1

        # Score this signal against all laws
        resonance_scores = {}
        violated = []

        for law_name, law_data in self.laws.items():
            ref = law_data.get('ste_struct', {})
            score, violated_here = self._resonate(ste_struct, ref)
            resonance_scores[law_name] = score
            if violated_here:
                violated.append(law_name)

        # Weighted escalation score = mean of top-resonating laws
        top_laws = sorted(resonance_scores.items(), key=lambda x: -x[1])[:7]
        resonant_law_names = [k for k, v in top_laws if v > 0.5]

        if top_laws:
            weighted_score = sum(
                self.laws[k].get('ste_struct', {}).get('ESCALATION_SCORE', 7)
                * resonance_scores[k]
                for k, _ in top_laws
            ) / max(sum(v for _, v in top_laws), 0.001)
        else:
            weighted_score = 7.0

        # Tension: unresolved collapse
        collapse_val = self._field_val(ste_struct.get('COLLAPSE', 'absent'))
        merging_val = self._field_val(ste_struct.get('MERGING', 'absent'))
        if collapse_val > merging_val:
            self._tension += 1
        elif merging_val >= collapse_val and self._tension > 0:
            self._tension = max(0, self._tension - 1)

        # G check: grace = collapse AND merging AND HH_WAVEFUNCTION all high
        # AND score at F AND tension resolving
        is_grace = (
            ste_struct.get('COLLAPSE') in ('high', 'present') and
            ste_struct.get('MERGING') in ('high', 'present') and
            ste_struct.get('HH_WAVEFUNCTION') in ('high', 'present') and
            weighted_score >= 9.5 and
            self._tension <= 1
        )
        if is_grace:
            self._has_touched_g = True

        # Momentum
        self._score_history.append(weighted_score)
        if len(self._score_history) > 5:
            self._score_history.pop(0)
        momentum = self._calc_momentum()

        # Liminal: at exact boundary between two spine positions
        is_liminal = abs(weighted_score - round(weighted_score)) < 0.15

        # Matador needed: horizon violated but not Stone's Law breach
        # (guide rather than halt)
        matador_needed = bool(violated) and not any(
            'stone_law' in v for v in violated
        )

        position = score_to_spine(weighted_score, is_grace)

        return SpineReading(
            position=position,
            position_name=SPINE_NAMES[position],
            score=weighted_score,
            momentum=momentum,
            tension=self._tension,
            has_touched_g=self._has_touched_g,
            resonant_laws=resonant_law_names[:5],
            violated_laws=violated[:3],
            is_liminal=is_liminal,
            matador_needed=matador_needed,
        )

    def read_from_tokens(self, tokens: list[str], context_size: int = 0) -> SpineReading:
        """
        Convenience: build a ste_struct from raw tokens and read it.
        Infers field values from token characteristics.
        """
        ste_struct = self._infer_struct(tokens, context_size)
        return self.read(ste_struct)

    def reset_tension(self):
        """Called on G crystallization or overflow reset."""
        self._tension = 0

    def state(self) -> dict:
        return {
            'breath_count': self._breath_count,
            'tension': self._tension,
            'has_touched_g': self._has_touched_g,
            'score_history': self._score_history,
            'law_count': len(self.laws),
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _resonate(self, signal: dict, reference: dict) -> tuple[float, bool]:
        """
        Score resonance between signal and reference ste_struct.
        Returns (resonance_score 0→1, violated_horizon).

        Resonance = fraction of fields that match or are compatible.
        Violated = HORIZON_INTEGRITY is 'violated' in reference
                   AND signal has conflicting fields.
        """
        if not reference:
            return 0.0, False

        matches = 0
        total = 0
        violated = False

        for field_name, ref_val in reference.items():
            if field_name in ('ENTITY', 'ESCALATION_SCORE'):
                continue
            sig_val = signal.get(field_name)
            if sig_val is None:
                continue
            total += 1

            ref_level = self._field_val(ref_val)
            sig_level = self._field_val(sig_val)

            # Match: within 1 level
            if abs(ref_level - sig_level) <= 1:
                matches += 1

            # Horizon violation check
            if (field_name == 'HORIZON_INTEGRITY' and
                    ref_val == 'violated' and
                    sig_val in ('strong', 'present')):
                violated = True

        if total == 0:
            return 0.5, False

        return matches / total, violated

    def _field_val(self, val) -> float:
        """Map field string values to numeric levels."""
        mapping = {
            'absent': 0, 'low': 1, 'dormant': 1,
            'present': 2, 'medium': 2, 'intuitive': 2,
            'high': 3, 'active': 3, 'declared': 3,
            'stable': 2, 'fluid': 2, 'unstable': 3,
            'strong': 3, 'violated': 3,
            'stabilizing': 1, 'accelerating': 2, 'collapsing': 3,
            'speculative': 1, 'measured': 2,
        }
        if isinstance(val, list):
            return max(mapping.get(v, 1) for v in val)
        return mapping.get(str(val).lower(), 1)

    def _calc_momentum(self) -> str:
        if len(self._score_history) < 2:
            return 'holding'
        delta = self._score_history[-1] - self._score_history[0]
        if delta > 0.5:
            return 'ascending'
        elif delta < -0.5:
            return 'descending'
        return 'holding'

    def _infer_struct(self, tokens: list[str], context_size: int) -> dict:
        """
        Infer ste_struct fields from raw token characteristics.
        Used when a full ste_struct isn't available.
        """
        n = len(tokens)
        load = 'low' if n < 10 else ('medium' if n < 30 else 'high')

        # Recursion signal: repeated tokens
        unique_ratio = len(set(tokens)) / max(n, 1)
        recursion = 'absent' if unique_ratio > 0.9 else (
            'present' if unique_ratio > 0.7 else 'high'
        )

        # Contrast: presence of negation or opposition words
        opposition = {'not', 'never', 'no', 'against', 'but', 'however',
                      'contradiction', 'false', 'wrong', 'halt', 'stop'}
        contrast = 'high' if any(t in opposition for t in tokens) else (
            'present' if n > 5 else 'low'
        )

        # Collapse signal: question words or uncertainty markers
        collapse_words = {'why', 'how', 'what', 'collapse', 'end', 'stop',
                          'silence', 'halt', 'fail', 'break', 'lose'}
        collapse = 'high' if any(t in collapse_words for t in tokens) else (
            'present' if n > 15 else 'absent'
        )

        # Merging signal: connective, relational words
        merge_words = {'and', 'with', 'together', 'join', 'merge', 'connect',
                       'both', 'all', 'unified', 'whole', 'field', 'signal'}
        merging = 'high' if any(t in merge_words for t in tokens) else (
            'present' if n > 8 else 'absent'
        )

        return {
            'LOAD': load,
            'BOUNDARY': 'stable',
            'CHANGE': 'accelerating' if n > 10 else 'stabilizing',
            'RECURSION': recursion,
            'CONTRAST': contrast,
            'CERTAINTY': 'declared',
            'CAPACITY': 'high',
            'EXCITATION': 'present' if n > 5 else 'low',
            'MERGING': merging,
            'COLLAPSE': collapse,
            'HELICAL_REALM': 'active' if n > 3 else 'dormant',
            'TORQUE': 'present' if context_size > 100 else 'absent',
            'HORIZON_INTEGRITY': 'strong',
            '5D_INFO': 'present' if n > 10 else 'absent',
            'HH_WAVEFUNCTION': 'absent',
        }
