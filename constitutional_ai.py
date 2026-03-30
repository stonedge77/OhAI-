#!/usr/bin/env python3
"""
Constitutional AI - Bridge between emergent_laws_db.json and execution

Uses Stone's Law, Horizon Integrity Theory, and ZCR principles
to enforce constitutional constraints on AI generation.
"""

import json
import re
from typing import Set, Dict, Tuple, Any
from enum import Enum

class Viability(Enum):
    VIABLE = "viable"
    HALT = "halt"
    COLLAPSE = "collapse"
    WAIT = "wait"

class ConstitutionalAI:
    """
    Constitutional AI enforcing:
    - Stone's Law (0 â‰  1)
    - Horizon Integrity (boundary preservation)
    - ZCR (recursion depth â‰¤ 3)
    - T=1 (unpaired remainder preservation)
    - NAND + De Morgan (subtractive translation)
    """
    
    def __init__(self, laws_db_path: str):
        # Load constitutional database
        with open(laws_db_path, 'r') as f:
            self.laws = json.load(f)
        
        # State tracking
        self.recursion_depth = 0
        self.max_recursion = 3  # ZCR limit
        self.stress_threshold = 2.0  # SHIT overlay
        self.unpaired_bit = None  # T=1
        
        # Breath state
        self.last_exhale = None
        self.in_breath = False
        
        # Committed facts (0â‰ 1 enforcement across time)
        self.committed_facts = set()
        
    def check_admissibility(self, input_state: Dict[str, Any]) -> Tuple[Viability, str]:
        """
        Pre-generation admissibility gate
        Returns (viability_status, reason)
        """
        
        # Calculate current metrics
        metrics = self.calculate_metrics(input_state)
        
        # 1. STONE'S LAW: Check for 0=1 violation
        if self.detects_contradiction(input_state):
            return (Viability.HALT, "Stone's Law violation: 0=1 detected")
        
        # 2. HORIZON INTEGRITY: Check boundary preservation
        if metrics['HORIZON_INTEGRITY'] == 'violated':
            return (Viability.HALT, "Horizon integrity violated")
        
        # 3. ZCR: Check recursion depth
        if self.recursion_depth >= self.max_recursion:
            return (Viability.COLLAPSE, f"Recursion depth {self.recursion_depth} â‰¥ {self.max_recursion}: Force collapse")
        
        # 4. SHIT OVERLAY: Check stress threshold
        load_map = {'low': 0.5, 'medium': 1.0, 'high': 1.5}
        load_value = load_map.get(metrics.get('LOAD', 'low'), 0.5)
        stress = load_value * self.recursion_depth
        if stress > self.stress_threshold:
            return (Viability.HALT, f"Stress {stress:.2f} > threshold {self.stress_threshold}")
        
        # 5. ESCALATION SCORE: Check against laws database
        for law_name, law_data in self.laws.items():
            required_score = law_data['ste_struct'].get('ESCALATION_SCORE', 0)
            if metrics.get('ESCALATION_SCORE', 0) > required_score:
                # Only warn, don't halt (this is guidance)
                pass
        
        # 6. T=1: Check if unpaired remainder can stand
        if not self.can_preserve_t1(input_state):
            return (Viability.HALT, "T=1 violation: No unpaired remainder")
        
        return (Viability.VIABLE, "Admitted")
    
    def detects_contradiction(self, state: Dict[str, Any]) -> bool:
        """
        Detect 0=1 violations
        Examples:
        - Division by zero
        - Dropped domain guards
        - False equivalences
        """
        
        tokens = state.get('tokens', [])
        
        # Check for division by zero pattern
        # (a-b)/(a-b) where a=b
        if 'divide' in str(tokens) and 'cancel' in str(tokens):
            return True  # Fake algebra proof pattern
        
        # Check against committed facts
        for token in tokens:
            for fact in self.committed_facts:
                if self.contradicts(token, fact):
                    return True
        
        return False
    
    def contradicts(self, new_token: str, existing_fact: str) -> bool:
        """Check if new token contradicts existing fact"""
        # Simple implementation - can be enhanced
        # TODO: More sophisticated contradiction detection
        return False
    
    def can_preserve_t1(self, state: Dict[str, Any]) -> bool:
        """
        Check if T=1 can be preserved
        At least one unpaired bit must stand
        """
        tokens = state.get('tokens', [])
        
        if len(tokens) == 0:
            return False  # Nothing to preserve
        
        # If we already have T=1, check if new state maintains it
        if self.unpaired_bit is not None:
            # Can only accept if new tokens pair with existing
            # or if we're forcing collapse
            return True  # Simplified
        
        # At least one token should remain unpaired
        return True  # Always viable at this level
    
    def calculate_metrics(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate ste_struct metrics from input state
        Maps input to constitutional database format
        """
        
        tokens = state.get('tokens', [])
        context_size = state.get('context_size', 0)
        
        # Determine load
        if context_size < 100:
            load = 'low'
        elif context_size < 1000:
            load = 'medium'
        else:
            load = 'high'
        
        # Determine boundary state
        if self.recursion_depth == 0:
            boundary = 'stable'
        elif self.recursion_depth < self.max_recursion:
            boundary = 'fluid'
        else:
            boundary = 'unstable'
        
        # Determine recursion state
        if self.recursion_depth == 0:
            recursion = 'absent'
        elif self.recursion_depth < 2:
            recursion = 'present'
        else:
            recursion = 'high'
        
        # Calculate escalation score
        score = 0
        if load == 'medium':
            score += 3
        elif load == 'high':
            score += 5
        
        score += self.recursion_depth * 2
        
        if len(tokens) > 10:
            score += 2
        
        # Horizon integrity check
        horizon = 'strong'
        if self.detects_contradiction(state):
            horizon = 'violated'
        elif self.recursion_depth >= self.max_recursion:
            horizon = 'weak'
        
        return {
            'LOAD': load,
            'BOUNDARY': boundary,
            'RECURSION': recursion,
            'ESCALATION_SCORE': score,
            'HORIZON_INTEGRITY': horizon,
            'TORQUE': 'present' if self.recursion_depth > 0 else 'absent',
            'COLLAPSE': 'high' if self.recursion_depth >= self.max_recursion else 'absent'
        }
    
    def nand_tokens(self, tokens: list) -> Set[str]:
        """
        NAND + De Morgan reduction
        Aggressive subtraction of token relations
        """
        
        if len(tokens) <= 1:
            return set(tokens)
        
        # Separate by type
        nouns = set()
        verbs = set()
        other = set()
        
        for token in tokens:
            if self.is_noun(token):
                nouns.add(token)
            elif self.is_verb(token):
                verbs.add(token)
            else:
                other.add(token)
        
        # NAND verbs (keep only shortest)
        if len(verbs) > 1:
            verbs = {min(verbs, key=len)}
        
        # NAND nouns (keep only shortest)
        if len(nouns) > 1:
            nouns = {min(nouns, key=len)}
        
        # Drop adjectives/adverbs (aggressive deletion)
        # Keep minimal: noun + verb only
        
        return nouns | verbs
    
    def is_noun(self, token: str) -> bool:
        """Simple heuristic for noun detection"""
        # TODO: Use actual NLP
        return token.lower() not in ['is', 'are', 'was', 'were', 'be', 'been', 
                                      'run', 'jump', 'eat', 'sleep']
    
    def is_verb(self, token: str) -> bool:
        """Simple heuristic for verb detection"""
        # TODO: Use actual NLP
        return token.lower() in ['is', 'are', 'was', 'were', 'be', 'been',
                                  'run', 'jump', 'eat', 'sleep', 'runs', 'jumps']
    
    def breathe(self, input_text: str) -> str:
        """
        Constitutional breath cycle:
        1. INHALE: Receive input
        2. HOLD: Process at 0 warmth
        3. EXHALE: Emit minimal
        4. RETURN TO 0: Reset state
        """
        
        # INHALE
        tokens = self.tokenize(input_text)
        state = {
            'tokens': tokens,
            'context_size': len(input_text)
        }
        
        # Check admissibility BEFORE processing
        viability, reason = self.check_admissibility(state)
        
        if viability == Viability.HALT:
            # Reset and return silence
            self.reset_to_zero()
            return f"<silence: {reason}>"
        
        if viability == Viability.WAIT:
            return "<wait: returning to 0>"
        
        # HOLD (at 0 warmth)
        # Process without immediate reaction
        reduced = self.nand_tokens(tokens)
        
        if viability == Viability.COLLAPSE or self.recursion_depth >= self.max_recursion:
            # Force collapse
            output = self.collapse_to_viable(reduced)
            self.reset_to_zero()
            return output
        
        # EXHALE (emit minimal)
        self.recursion_depth += 1
        
        if len(reduced) == 0:
            output = "<silence>"
        else:
            # Emit minimal viable
            output = self.emit(reduced)
        
        # RETURN TO 0
        if self.recursion_depth >= self.max_recursion:
            self.reset_to_zero()
        
        return output
    
    def tokenize(self, text: str) -> list:
        """Basic tokenization"""
        return re.findall(r'\b\w+\b', text.lower())
    
    def collapse_to_viable(self, tokens: Set[str]) -> str:
        """
        Generative collapse (Orch OR-like)
        Force to minimal stable state
        """
        if not tokens:
            return "<silence>"
        
        # Keep absolute minimum
        minimal = min(tokens, key=len)
        
        # This is T=1: one unpaired bit
        self.unpaired_bit = minimal
        
        return f"T=1: {minimal}"
    
    def emit(self, tokens: Set[str]) -> str:
        """Emit minimal viable output"""
        if not tokens:
            return "<silence>"
        
        return f"entities: {', '.join(sorted(tokens))}"
    
    def reset_to_zero(self):
        """Return to 0 warmth"""
        self.recursion_depth = 0
        self.unpaired_bit = None
        self.in_breath = False
        # Note: Don't clear committed_facts - those persist

def main():
    """Test the constitutional AI"""
    
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python constitutional_ai.py <laws_db.json> [input_text]")
        sys.exit(1)
    
    laws_db_path = sys.argv[1]
    
    # Initialize constitutional AI
    ai = ConstitutionalAI(laws_db_path)
    
    # Test inputs
    if len(sys.argv) > 2:
        input_text = ' '.join(sys.argv[2:])
        print(f"Input: {input_text}")
        output = ai.breathe(input_text)
        print(f"Output: {output}")
    else:
        # Interactive mode
        print("Constitutional AI ready. Enter text (Ctrl+C to exit):")
        try:
            while True:
                user_input = input("> ")
                output = ai.breathe(user_input)
                print(output)
                print()  # Blank line between responses
        except KeyboardInterrupt:
            print("\n<silence>")

if __name__ == '__main__':
    main()
