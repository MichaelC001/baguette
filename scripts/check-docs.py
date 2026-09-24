#!/usr/bin/env python3
"""Check the docs against docs/documentation-design/README.md.

Reports every problem; exits non-zero only with --strict.
Usage: scripts/check-docs.py [--strict]
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUDGETS = {"README.md": 150, "AGENTS.md": 100}
CHAR_BUDGETS = {"AGENTS.md": 12_000}
FEATURE_BUDGET = 200
DESCRIPTION_CHARS = 250
BULLET_CHARS = 300
SCANNED = ["*.md", "docs/**/*.md", "skills/**/*.md", ".claude/skills/**/*.md"]
# Website pages and design sketches live under docs/ but aren't docs.
NOT_DOCS = {"mockups", "prototypes", "announcements"}

LINK = re.compile(r"\]\(([^)\s]+)\)")
URL = re.compile(r"\(https?://[^)]*\)")
FENCE = re.compile(r"^\s*(```|~~~)")

problems = []


def report(path, msg):
    problems.append(f"{path.relative_to(ROOT)}: {msg}")


def lines_outside_fences(text):
    fenced = False
    for n, line in enumerate(text.splitlines(), 1):
        if FENCE.match(line):
            fenced = not fenced
        elif not fenced:
            yield n, line


def feature_docs():
    """Folder features (the target shape) and flat ones still to be moved."""
    features = ROOT / "docs" / "features"
    return sorted(features.glob("*/README.md")) + sorted(features.glob("*.md"))


def description(path):
    m = re.match(r"^---\n(.*?)\n---\n", path.read_text(), re.S)
    if not m:
        return None
    d = re.search(r"^description:\s*(.+)$", m.group(1), re.M)
    return d.group(1).strip() if d else None


def check_budgets():
    for name, limit in BUDGETS.items():
        path = ROOT / name
        n = len(path.read_text().splitlines())
        if n > limit:
            report(path, f"{n} lines, budget {limit}")
    for name, limit in CHAR_BUDGETS.items():
        path = ROOT / name
        n = len(path.read_text())
        if n > limit:
            report(path, f"{n:,} chars, budget {limit:,}")
    for path in feature_docs():
        n = len(path.read_text().splitlines())
        if n > FEATURE_BUDGET:
            report(path, f"{n} lines, budget {FEATURE_BUDGET}")


def check_descriptions():
    for path in feature_docs():
        d = description(path)
        if not d:
            report(path, "missing frontmatter `description`")
        elif len(d) > DESCRIPTION_CHARS:
            report(path, f"description is {len(d)} chars, limit {DESCRIPTION_CHARS}")


def bullets(text):
    """Each list item as one string, joining its wrapped continuation lines."""
    items, open_item = [], False
    for line in text.splitlines():
        if line.startswith(("- ", "* ")):
            items.append(line)
            open_item = True
        elif open_item and line.startswith((" ", "\t")) and line.strip():
            items[-1] += " " + line.strip()
        else:
            open_item = False
    return items


def check_changelog():
    path = ROOT / "CHANGELOG.md"
    text = path.read_text()
    unreleased = re.search(r"^## \[Unreleased\]\n(.*?)(?=^---$|^## \[|\Z)", text, re.S | re.M)
    if unreleased:
        for bullet in bullets(unreleased.group(1)):
            n = len(URL.sub("()", bullet))
            if n > BULLET_CHARS:
                report(path, f"[Unreleased] bullet is {n} chars, limit {BULLET_CHARS}: {bullet[:60]}…")
    minors = []
    for v in re.findall(r"^## \[(\d+\.\d+)\.\d+\]", text, re.M):
        if v not in minors:
            minors.append(v)
    if len(minors) > 1:
        report(path, f"holds minors {', '.join(minors)}; run scripts/changelog-rollover.py")


def anchors(path):
    """GitHub's heading slugs: lowercase, punctuation dropped, spaces → `-`, repeats get `-1`, `-2`…"""
    seen, slugs = {}, set()
    for _, line in lines_outside_fences(path.read_text()):
        m = re.match(r"^#{1,6}\s+(.*?)\s*#*\s*$", line)
        if not m:
            continue
        slug = re.sub(r"[^\w\- ]", "", m.group(1).lower()).replace(" ", "-")
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        slugs.add(slug if count == 0 else f"{slug}-{count}")
    return slugs


def check_links():
    files = {p for pattern in SCANNED for p in ROOT.glob(pattern)}
    for path in sorted(files):
        if NOT_DOCS & set(path.relative_to(ROOT).parts):
            continue
        for n, line in lines_outside_fences(path.read_text()):
            line = re.sub(r"`[^`]*`", "", line)  # links inside inline code are examples
            for target in LINK.findall(line):
                if re.match(r"^(https?:|mailto:|#)", target):
                    continue
                target, _, anchor = target.partition("#")
                dest = (path.parent / target) if target else path
                if not dest.exists():
                    report(path, f"line {n}: broken link {target}")
                elif anchor and dest.suffix == ".md" and anchor not in anchors(dest):
                    report(path, f"line {n}: no heading for #{anchor} in {dest.resolve().relative_to(ROOT)}")


def main():
    check_budgets()
    check_descriptions()
    check_changelog()
    check_links()
    for p in problems:
        print(p)
    print(f"{len(problems)} problem(s)")
    if problems and "--strict" in sys.argv:
        sys.exit(1)


if __name__ == "__main__":
    main()
