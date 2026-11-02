#!/usr/bin/env python3
"""Conservative two-column detection from Poppler TSV word coordinates."""
import csv
import sys
from collections import defaultdict


def detect(path):
    lines = defaultdict(list)
    pages = {}
    with open(path, encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            try:
                page = int(row["page_num"])
                x = float(row["left"])
                y = float(row["top"])
                w = float(row["width"])
                if row["text"] == "###PAGE###":
                    pages[page] = w
                elif row["level"] == "5" and row["text"].strip():
                    key = page, row["par_num"], row["block_num"], row["line_num"]
                    lines[key].append((x, y, x + w))
            except (ValueError, KeyError):
                continue
    if not lines:
        return "unknown", "unknown"
    by_page = defaultdict(lambda: [[], []])
    for (page, *_), words in lines.items():
        width = pages.get(page, 0)
        if not width:
            continue
        left = min(word[0] for word in words) / width
        right = max(word[2] for word in words) / width
        top = min(word[1] for word in words)
        # A column line must fit largely on one side. Ignore full-width titles/tables.
        if 0.05 <= left <= 0.44 and right < 0.54:
            by_page[page][0].append(top)
        elif 0.49 <= left <= 0.89 and right < 0.97:
            by_page[page][1].append(top)
    for left, right in by_page.values():
        if len(left) < 6 or len(right) < 6:
            continue
        # Side-by-side lines in an overlapping vertical band, not separate sections.
        overlap = min(max(left), max(right)) - max(min(left), min(right))
        if overlap > 90:
            return "multi", "2"
    return "single", "1"


if __name__ == "__main__":
    print(*detect(sys.argv[1]), sep="\t")
