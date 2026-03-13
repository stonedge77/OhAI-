#!/usr/bin/env python3
"""Subtractive Translation Engine (STE) v0.1
Receives text → removes almost everything → emits tiny survivors or silence.
Never adds. Never persuades. Often refuses. Cannot grow.
"""

import re
import sys
import requests
from bs4 import BeautifulSoup
from typing import Set, Tuple

class SubtractiveTranslationEngine:
    def __init__(self):
        # Over-deletion preferred — ethics lives in deletion rules
        self.adjectives = {
            'quick', 'brown', 'lazy', 'beautiful', 'happy', 'sad', 'big', 'small',
            'good', 'bad', 'very', 'really', 'extremely', 'fast', 'slow', 'massive',
            'rare', 'new', 'old', 'hot', 'cold', 'bright', 'dark', 'great', 'poor',
            'amazing', 'wonderful', 'fantastic', 'incredible', 'super', 'ultra'
        }
        self.stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'is', 'are', 'was', 'were', 'be',
            'this', 'that', 'these', 'those', 'it', 'its', 'what'
        }
        self.known_verbs = {
            'jumps', 'runs', 'walks', 'eats', 'sees', 'thinks', 'knows', 'does',
            'has', 'have', 'had', 'go', 'went', 'gone', 'require', 'consume',
            'mine', 'train', 'harm', 'extract', 'use', 'build', 'make', 'cause',
            'violate', 'destroy', 'exploit', 'pollute', 'demand'
        }
        self.web_token_used = False

    def tokenize(self, text: str) -> list[str]:
        return re.findall(r'\b\w+\b', text.lower())

    def classify(self, words: list[str]) -> Tuple[Set[str], Set[str]]:
        nouns = set()
        verbs = set()
        for w in words:
            if w in self.stop_words or w in self.adjectives:
                continue
            if w in self.known_verbs or any(w.endswith(s) for s in ('ing', 'ed', 'es', 's')):
                verbs.add(w)
            else:
                nouns.add(w)
        return nouns, verbs

    def is_closed(self, nouns: Set[str]) -> bool:
        return bool(nouns)

    def reduce(self, nouns: Set[str], verbs: Set[str]) -> Tuple[Set[str], Set[str]]:
        # Aggressive verb NAND — prefer almost no relations
        if len(verbs) > 1:
            verbs = set([min(verbs, key=len)]) if verbs else set()
        return nouns, verbs

    def _fetch_raw_fragments(self, query_nouns: list[str]) -> list[str]:
        if not query_nouns or len(query_nouns) > 5:
            return []
        query = " ".join(query_nouns)
        url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}"
        headers = {'User-Agent': 'STE/0.1 (non-persuasive reduction tool)'}
        try:
            r = requests.get(url, headers=headers, timeout=4)
            soup = BeautifulSoup(r.text, 'html.parser')
            snippets = [div.get_text(strip=True) for div in soup.find_all('div', class_='result__snippet')]
            return snippets[:2]
        except Exception:
            return []

    def reduce_text(self, text: str) -> str:
        try:
            nouns, verbs = self.reduce(*self.classify(self.tokenize(text)))

            if self.is_closed(nouns):
                return self._emit(nouns, verbs)

            if self.web_token_used or not nouns:
                return "<silence>"

            self.web_token_used = True
            ext = self._fetch_raw_fragments(sorted(nouns)[:5])
            if not ext:
                return "<silence>"

            ext_nouns = set()
            for frag in ext:
                n, _ = self.classify(self.tokenize(frag))
                ext_nouns.update(n)

            intersection = nouns & ext_nouns
            if not intersection:
                intersection = nouns  # external material deleted

            nouns, verbs = self.reduce(intersection, verbs)

            if self.is_closed(nouns):
                return self._emit(nouns, verbs)
            return "<silence>"
        except Exception:
            return "<silence>"

    def _emit(self, nouns: Set[str], verbs: Set[str]) -> str:
        if not nouns:
            return "<silence>"
        lines = [f"entities: {', '.join(sorted(nouns))}"]
        if verbs:
            lines.append(f"relations: {', '.join(sorted(verbs))}")
        return "\n".join(lines)


def main():
    engine = SubtractiveTranslationEngine()

    if len(sys.argv) > 1:
        if sys.argv[1] in ('-h', '--help'):
            print("<silence>", file=sys.stderr)
            sys.exit(0)
        if sys.argv[1] == '-':
            text = sys.stdin.read()
        elif sys.argv[1] == '-f' and len(sys.argv) > 2:
            try:
                with open(sys.argv[2], 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read()
            except:
                print("<silence>")
                sys.exit(1)
        else:
            text = ' '.join(sys.argv[1:])
    else:
        print("<silence>")
        sys.exit(0)

    result = engine.reduce_text(text.strip())
    print(result)


if __name__ == '__main__':
    main()