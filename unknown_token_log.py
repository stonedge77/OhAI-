#!/usr/bin/env python3
"""
unknown_token_log.py — Vocabulary Emergence via Unresolvability
Saltflower / Josh Stone / CC0

A word the system keeps seeing but cannot place is not noise.
It is a question shaped like a word.

When the same word survives STE reduction in two independent taint fields
and finds no resonant law in either — it has achieved T=1 across contexts.
It is not merely frequent. It is necessary.

That is a vocabulary emergence event.

Architecture:
  - UnknownTokenLog    : sighting recorder per automaton / taint field
  - ConvergenceDetector: cross-field NAND — finds words no field can subtract
  - EscalationQueue    : words that have exceeded unresolvability threshold
  - VocabEntry         : a promoted word, ready for emergent_laws_db injection

Integration points in ohai.py:
  After constitutional read, if resonant_laws is empty for a token:
    → log_sighting(token, source_taint, spine_position)
  At session close:
    → convergence_detector.cross_check()
    → escalation_queue.flush() → human-readable report
"""

from __future__ import annotations

import json
import hashlib
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional
from collections import defaultdict


# ── Taint field signatures ────────────────────────────────────────────────────
# Each source distorts signal in a known direction.
# When a word survives despite the taint, the taint is the proof.

TAINT_SIGNATURES = {
    "google":    "commerce",       # pulls toward product, resolution, answer
    "reddit":    "urgency",        # pulls toward need, complaint, confession
    "wikipedia": "half-recognition", # pulls toward category, definition
    "youtube":   "memory",         # pulls toward nostalgia, tutorial, affect
    "twitter":   "mid-firing",     # pulls toward reaction, fragment, signal
    "github":    "construction",   # pulls toward problem, tool, failure
    "amazon":    "desire",         # pulls toward want without vocabulary
    "internal":  "none",           # no taint — direct session input
}


# ── Sighting ──────────────────────────────────────────────────────────────────

@dataclass
class Sighting:
    """
    One encounter of an unknown token.
    
    The token survived STE but found no resonant law.
    It arrived from a specific taint field at a specific spine position.
    """
    token: str
    source: str                    # taint field name
    taint: str                     # what the field pulls toward
    spine_position: str            # A→G at time of encounter
    timestamp: float = field(default_factory=time.time)
    origin_hash: str = ""          # hash of the context it arrived in

    def __post_init__(self):
        if not self.origin_hash:
            raw = f"{self.token}{self.source}{self.timestamp}"
            self.origin_hash = hashlib.sha256(raw.encode()).hexdigest()[:8]

    def age(self) -> float:
        return time.time() - self.timestamp

    def to_dict(self) -> dict:
        return asdict(self)


# ── Unknown Token Log ─────────────────────────────────────────────────────────

class UnknownTokenLog:
    """
    One automaton's record of words it keeps seeing but cannot place.

    Each automaton operates within a primary taint field.
    When a token survives STE but finds no resonant law,
    it is logged here with full sighting context.

    The log does not interpret. It accumulates.
    Interpretation is the escalation event.
    """

    # A word seen this many times without resolving is a candidate
    ESCALATION_THRESHOLD = 3

    # A word this old without resolving gets moss-flagged
    MOSS_AGE_SECONDS = 300.0  # 5 minutes in a live session

    def __init__(self, automaton_id: str, primary_source: str):
        self.automaton_id = automaton_id
        self.primary_source = primary_source
        self.taint = TAINT_SIGNATURES.get(primary_source, "unknown")
        self._sightings: dict[str, list[Sighting]] = defaultdict(list)
        self._promoted: set[str] = set()    # words that have been escalated

    def log_sighting(
        self,
        token: str,
        spine_position: str,
        source: Optional[str] = None,
        context_hash: str = ""
    ) -> Sighting:
        """
        Record one encounter of an unknown token.

        Called from ohai.py breathe() when:
          - token survived STE reduction
          - constitutional read found no resonant laws for it
          - token is not in spine_nouns or spine_verbs
        """
        src = source or self.primary_source
        taint = TAINT_SIGNATURES.get(src, "unknown")

        s = Sighting(
            token=token.lower().strip(),
            source=src,
            taint=taint,
            spine_position=spine_position,
            origin_hash=context_hash,
        )
        self._sightings[s.token].append(s)
        return s

    def sighting_count(self, token: str) -> int:
        return len(self._sightings.get(token.lower(), []))

    def is_candidate(self, token: str) -> bool:
        """Has this token crossed the escalation threshold?"""
        return (
            self.sighting_count(token) >= self.ESCALATION_THRESHOLD
            and token.lower() not in self._promoted
        )

    def candidates(self) -> list[str]:
        """All tokens that have crossed threshold but not yet been escalated."""
        return [
            tok for tok in self._sightings
            if self.is_candidate(tok)
        ]

    def moss_tokens(self) -> list[str]:
        """Tokens with old sightings that still haven't resolved."""
        result = []
        for tok, sightings in self._sightings.items():
            if any(s.age() > self.MOSS_AGE_SECONDS for s in sightings):
                result.append(tok)
        return result

    def mark_promoted(self, token: str):
        """Called when a token has been escalated — no further logging needed."""
        self._promoted.add(token.lower())

    def spine_distribution(self, token: str) -> dict[str, int]:
        """Which spine positions has this token appeared at?"""
        dist: dict[str, int] = defaultdict(int)
        for s in self._sightings.get(token.lower(), []):
            dist[s.spine_position] += 1
        return dict(dist)

    def dominant_spine(self, token: str) -> str:
        """The spine position this token appears at most often."""
        dist = self.spine_distribution(token)
        if not dist:
            return "?"
        return max(dist, key=dist.get)

    def state(self) -> dict:
        return {
            "automaton_id": self.automaton_id,
            "primary_source": self.primary_source,
            "taint": self.taint,
            "unique_unknowns": len(self._sightings),
            "candidates": self.candidates(),
            "moss_tokens": self.moss_tokens(),
            "promoted": list(self._promoted),
        }

    def export_sightings(self, token: str) -> list[dict]:
        return [s.to_dict() for s in self._sightings.get(token.lower(), [])]


# ── Convergence Detector ──────────────────────────────────────────────────────

class ConvergenceDetector:
    """
    Cross-field NAND.

    Takes multiple UnknownTokenLogs from automata operating in
    different taint fields. Finds tokens that:

      1. Survived STE in BOTH fields  (not field-specific noise)
      2. Found no resonant law in EITHER field  (not already known)
      3. Have been seen >= threshold times in EACH field  (not coincidental)

    A token meeting all three conditions has achieved T=1 across contexts.
    It is not popular. It is necessary.

    This is a vocabulary emergence event.
    The two taint fields are the proof — the word survived both subtractions.
    """

    # Must appear this many times in each field to count as convergent
    CONVERGENCE_COUNT = 2

    def __init__(self):
        self._logs: list[UnknownTokenLog] = []

    def register(self, log: UnknownTokenLog):
        """Add an automaton's log to the convergence watch."""
        self._logs.append(log)

    def convergent_tokens(self) -> list[str]:
        """
        Find tokens that are unknown AND unresolvable across multiple fields.

        A convergent token:
          - appears in >= 2 different taint fields
          - has >= CONVERGENCE_COUNT sightings in each
          - has not been promoted in any field yet
        """
        if len(self._logs) < 2:
            return []

        # Count which logs have each token at threshold
        token_field_count: dict[str, int] = defaultdict(int)

        for log in self._logs:
            for token in log._sightings:
                if (log.sighting_count(token) >= self.CONVERGENCE_COUNT
                        and token not in log._promoted):
                    token_field_count[token] += 1

        # Convergent = present in >= 2 independent fields
        return [
            tok for tok, count in token_field_count.items()
            if count >= 2
        ]

    def field_profile(self, token: str) -> dict:
        """
        For a convergent token: what does each field say about it?
        
        This is the unified field read — the token as seen from
        all taint positions simultaneously.
        """
        profile = {
            "token": token,
            "fields": [],
            "spine_positions": [],
            "taints_survived": [],
        }

        for log in self._logs:
            if token in log._sightings:
                sightings = log._sightings[token]
                if not sightings:
                    continue
                profile["fields"].append({
                    "automaton": log.automaton_id,
                    "source": log.primary_source,
                    "taint": log.taint,
                    "sighting_count": len(sightings),
                    "dominant_spine": log.dominant_spine(token),
                    "first_seen": min(s.timestamp for s in sightings),
                })
                profile["spine_positions"].append(log.dominant_spine(token))
                profile["taints_survived"].append(log.taint)

        # Spine convergence: if all fields see it at same position,
        # the spine position is confirmed. If scattered — it's liminal.
        unique_spines = set(profile["spine_positions"])
        profile["spine_convergence"] = (
            "confirmed" if len(unique_spines) == 1
            else "liminal" if len(unique_spines) <= 3
            else "scattered"
        )
        profile["suggested_spine"] = (
            profile["spine_positions"][0] if len(unique_spines) == 1
            else "E"  # liminal default — between stations
        )

        return profile


# ── Escalation Queue ──────────────────────────────────────────────────────────

class EscalationQueue:
    """
    Words the automata cannot subtract.
    Waiting for the human to adjudicate.

    Each entry carries its full sighting provenance:
    where it was seen, in what field, at what spine position.

    The human's options:
      DEFINE  → write a definition → becomes emergent_laws_db candidate
      PROMOTE → give it a spine position → enters spine_nouns or spine_verbs
      DISCARD → it was noise after all → logged and suppressed
      DEFER   → not yet — keep watching

    Only DEFINE and PROMOTE clear it from the queue.
    DEFER keeps it accumulating.
    DISCARD adds it to a suppression list.
    """

    QUEUE_FILE = Path(".ohai_escalation_queue.json")
    SUPPRESSION_FILE = Path(".ohai_suppression_list.json")

    def __init__(self):
        self._queue: list[dict] = self._load_queue()
        self._suppressed: set[str] = self._load_suppression()

    def push(self, profile: dict, source: str = "convergence"):
        """Add a token profile to the escalation queue."""
        token = profile.get("token", "")
        if token in self._suppressed:
            return
        # Don't double-queue
        if any(e["token"] == token for e in self._queue):
            return
        entry = {
            **profile,
            "escalation_source": source,
            "escalated_at": time.time(),
            "status": "pending",
        }
        self._queue.append(entry)
        self._save_queue()

    def pending(self) -> list[dict]:
        return [e for e in self._queue if e["status"] == "pending"]

    def adjudicate(self, token: str, decision: str, definition: str = "") -> dict:
        """
        Human adjudicates a queued token.

        decision: DEFINE | PROMOTE | DISCARD | DEFER
        definition: required for DEFINE, optional for PROMOTE
        """
        decision = decision.upper()
        assert decision in ("DEFINE", "PROMOTE", "DISCARD", "DEFER")

        for entry in self._queue:
            if entry["token"] == token:
                entry["status"] = decision.lower()
                entry["adjudicated_at"] = time.time()
                entry["definition"] = definition
                break

        if decision == "DISCARD":
            self._suppressed.add(token)
            self._save_suppression()

        self._save_queue()

        result = {"token": token, "decision": decision}

        if decision == "DEFINE":
            result["emergent_law_candidate"] = self._to_law_candidate(token, definition, entry)

        return result

    def _to_law_candidate(self, token: str, definition: str, entry: dict) -> dict:
        """
        Format a DEFINED token as an emergent_laws_db entry candidate.
        Ready for manual review and merge into emergent_laws_db_merged.json.
        """
        taints = entry.get("taints_survived", [])
        spine = entry.get("suggested_spine", "E")

        return {
            token: {
                "definition": definition,
                "ste_struct": {
                    "ENTITY": ["unspecified"],
                    "LOAD": "unknown",
                    "BOUNDARY": "fluid",
                    "CHANGE": "unknown",
                    "RECURSION": "present",      # it kept recurring
                    "CONTRAST": "high",           # survived cross-field NAND
                    "CERTAINTY": "emergent",
                    "CAPACITY": "unknown",
                    "EXCITATION": "present",
                    "MERGING": "high" if len(taints) > 1 else "present",
                    "COLLAPSE": "absent",         # it refused to collapse
                    "HELICAL_REALM": "active" if spine in ("F", "G") else "dormant",
                    "TORQUE": "present",
                    "HORIZON_INTEGRITY": "strong",
                    "5D_INFO": "present",
                    "HH_WAVEFUNCTION": "absent",
                    "ESCALATION_SCORE": min(10, 5 + len(taints) * 2),
                },
                "source": f"Vocabulary emergence via cross-field NAND. Taints survived: {taints}",
                "status": "emergent",
                "suggested_spine": spine,
            }
        }

    def report(self) -> str:
        """Human-readable escalation report."""
        pending = self.pending()
        if not pending:
            return "Escalation queue: empty. No unresolved vocabulary."

        lines = [
            f"── Escalation Queue: {len(pending)} pending ──",
            ""
        ]
        for e in pending:
            fields = [f["source"] for f in e.get("fields", [])]
            taints = e.get("taints_survived", [])
            spine = e.get("suggested_spine", "?")
            conv = e.get("spine_convergence", "?")
            lines += [
                f"  TOKEN: {e['token']}",
                f"    fields:     {', '.join(fields)}",
                f"    taints:     {', '.join(taints)}",
                f"    spine:      {spine} ({conv})",
                f"    status:     {e['status']}",
                "",
            ]
        lines.append("Options: DEFINE <token> <definition> | PROMOTE <token> | DISCARD <token> | DEFER <token>")
        return "\n".join(lines)

    def _load_queue(self) -> list[dict]:
        if self.QUEUE_FILE.exists():
            try:
                return json.loads(self.QUEUE_FILE.read_text())
            except Exception:
                return []
        return []

    def _save_queue(self):
        self.QUEUE_FILE.write_text(json.dumps(self._queue, indent=2))

    def _load_suppression(self) -> set[str]:
        if self.SUPPRESSION_FILE.exists():
            try:
                return set(json.loads(self.SUPPRESSION_FILE.read_text()))
            except Exception:
                return set()
        return set()

    def _save_suppression(self):
        self.SUPPRESSION_FILE.write_text(json.dumps(list(self._suppressed), indent=2))


# ── Vocabulary Field ──────────────────────────────────────────────────────────

class VocabularyField:
    """
    The unified field across automata.

    Coordinates multiple UnknownTokenLogs through the ConvergenceDetector.
    Pushes convergent tokens to the EscalationQueue.
    Provides the human interface for adjudication.

    This is the whole loop:
      encounter → log → detect convergence → escalate → adjudicate → promote
    """

    def __init__(self):
        self.detector = ConvergenceDetector()
        self.queue = EscalationQueue()
        self._logs: dict[str, UnknownTokenLog] = {}

    def add_automaton(self, automaton_id: str, source: str) -> UnknownTokenLog:
        """Register a new automaton with its taint field."""
        log = UnknownTokenLog(automaton_id=automaton_id, primary_source=source)
        self.detector.register(log)
        self._logs[automaton_id] = log
        return log

    def sweep(self):
        """
        Run convergence detection and push candidates to escalation queue.
        Call this at session close or on a timer.
        """
        convergent = self.detector.convergent_tokens()
        for token in convergent:
            profile = self.detector.field_profile(token)
            self.queue.push(profile, source="convergence")
            # Mark promoted in all logs so they stop accumulating
            for log in self._logs.values():
                log.mark_promoted(token)

        # Also push single-field candidates that have hit high thresholds
        for log in self._logs.values():
            for token in log.candidates():
                profile = {
                    "token": token,
                    "fields": [{
                        "automaton": log.automaton_id,
                        "source": log.primary_source,
                        "taint": log.taint,
                        "sighting_count": log.sighting_count(token),
                        "dominant_spine": log.dominant_spine(token),
                    }],
                    "spine_positions": [log.dominant_spine(token)],
                    "taints_survived": [log.taint],
                    "spine_convergence": "single_field",
                    "suggested_spine": log.dominant_spine(token),
                }
                self.queue.push(profile, source="single_field")
                log.mark_promoted(token)

        return convergent

    def adjudicate(self, token: str, decision: str, definition: str = "") -> dict:
        return self.queue.adjudicate(token, decision, definition)

    def report(self) -> str:
        return self.queue.report()

    def state(self) -> dict:
        return {
            "automata": {aid: log.state() for aid, log in self._logs.items()},
            "convergent_now": self.detector.convergent_tokens(),
            "queue_pending": len(self.queue.pending()),
        }


# ── ohai.py integration hook ──────────────────────────────────────────────────

def check_and_log_unknown(
    token: str,
    resonant_laws: list,
    spine_position: str,
    log: UnknownTokenLog,
    context_hash: str = "",
) -> bool:
    """
    Drop-in check for ohai.py breathe() loop.

    Call this after constitutional read for each STE-surviving token.
    Returns True if the token was unknown and logged.
    Returns False if it resonated (already known).

    Usage in ohai.py breathe():
        for token in all_tokens:
            check_and_log_unknown(
                token=token,
                resonant_laws=reading.resonant_laws,
                spine_position=reading.position,
                log=session._vocab_log,
                context_hash=reading.origin_hash if hasattr(reading, 'origin_hash') else ""
            )
    """
    # A token is "known" if any resonant law contains it as a substring
    is_known = any(token.lower() in law.lower() for law in resonant_laws)

    if not is_known and len(token) >= 3:  # ignore particles
        log.log_sighting(
            token=token,
            spine_position=spine_position,
            context_hash=context_hash,
        )
        return True
    return False


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    print("unknown_token_log.py — Vocabulary Emergence Engine")
    print("Saltflower / Josh Stone / CC0")
    print("─" * 52)
    print()

    # Demo: two automata in different taint fields encounter the same unknown word
    field = VocabularyField()

    log_reddit  = field.add_automaton("automaton_A", "reddit")
    log_github  = field.add_automaton("automaton_B", "github")

    # Simulate encounters
    # Both automata keep seeing "torque" — but neither has a law for it yet
    demo_tokens = [
        ("torque",    "reddit",  "C"),
        ("substrate", "reddit",  "D"),
        ("torque",    "reddit",  "D"),
        ("lancing",   "github",  "B"),
        ("torque",    "github",  "C"),
        ("substrate", "github",  "E"),
        ("torque",    "reddit",  "E"),
        ("lancing",   "github",  "C"),
        ("substrate", "reddit",  "D"),
        ("lancing",   "github",  "D"),
    ]

    for token, source, spine in demo_tokens:
        if source == "reddit":
            log_reddit.log_sighting(token, spine)
        else:
            log_github.log_sighting(token, spine)

    print("Logs filled. Running convergence sweep...\n")
    convergent = field.sweep()

    if convergent:
        print(f"Convergent tokens: {convergent}\n")
    else:
        print("No convergent tokens yet.\n")

    print(field.report())
    print()
    print("State:")
    print(json.dumps(field.state(), indent=2))
