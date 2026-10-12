"""Text-content matches with explicit ambiguity, independent from raster evidence."""

from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher

from slidetransit.models import TextBlock


def match_blocks(
    reference: list[TextBlock], candidate: list[TextBlock]
) -> tuple[list[tuple[TextBlock, TextBlock, str]], list[TextBlock], list[TextBlock]]:
    pairs: list[tuple[TextBlock, TextBlock, str]] = []
    left, right = list(reference), list(candidate)
    lc, rc = Counter(b.normalized for b in left), Counter(b.normalized for b in right)
    for block in list(left):
        if lc[block.normalized] == 1 and rc[block.normalized] == 1:
            match = next(b for b in right if b.normalized == block.normalized)
            pairs.append((block, match, "unique-exact-text"))
            left.remove(block)
            right.remove(match)
    # Duplicate occurrences may be paired only with a mutual unique geometry match.
    # They remain ambiguous for source-object attribution even then.
    for block in list(left):
        possible = [
            b
            for b in right
            if b.normalized == block.normalized
            and abs(b.bbox.x0 - block.bbox.x0) <= 36
            and abs(b.bbox.y0 - block.bbox.y0) <= 36
        ]
        if len(possible) != 1:
            continue
        match = possible[0]
        reverse = [
            b
            for b in left
            if b.normalized == match.normalized
            and abs(b.bbox.x0 - match.bbox.x0) <= 36
            and abs(b.bbox.y0 - match.bbox.y0) <= 36
        ]
        if len(reverse) == 1:
            pairs.append((block, match, "duplicate-text-geometry; source identity ambiguous"))
            left.remove(block)
            right.remove(match)
    # Changed content requires both a similar sequence and a bounded location.
    for block in list(left):
        possible = [
            b
            for b in right
            if SequenceMatcher(None, block.normalized, b.normalized, autojunk=False).ratio() >= 0.55
            and abs(b.bbox.x0 - block.bbox.x0) < 36
            and abs(b.bbox.y0 - block.bbox.y0) < 36
        ]
        if len(possible) != 1:
            continue
        match = possible[0]
        reverse = [
            b
            for b in left
            if SequenceMatcher(None, b.normalized, match.normalized, autojunk=False).ratio() >= 0.55
            and abs(b.bbox.x0 - match.bbox.x0) < 36
            and abs(b.bbox.y0 - match.bbox.y0) < 36
        ]
        if len(reverse) == 1:
            pairs.append((block, match, "unique-similar-text-and-geometry"))
            left.remove(block)
            right.remove(match)
    return pairs, left, right
