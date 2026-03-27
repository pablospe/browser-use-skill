#!/usr/bin/env python3
"""Compare two snapshot files and show what changed between page states."""

import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent
SNAPSHOT_DIR = SKILL_DIR / ".browser-use"


def parse_snapshot(filepath: Path) -> dict[str, dict]:
    """Parse a snapshot YAML file into a dict keyed by ref.

    Each entry contains: role, label, ref, num, value, checked, required,
    disabled, invalid, level, and the raw line text.
    """
    elements: dict[str, dict] = {}
    text = filepath.read_text()

    for line in text.splitlines():
        stripped = line.strip()
        # Skip comments, blank lines, option lines, url lines
        if not stripped or stripped.startswith("#") or stripped.startswith("- option") or stripped.startswith("/url:"):
            continue
        if not stripped.startswith("- "):
            continue

        entry: dict = {"raw": stripped}

        # Remove leading "- "
        rest = stripped[2:]

        # Extract role (first word)
        role_match = re.match(r"(\S+)", rest)
        if not role_match:
            continue
        entry["role"] = role_match.group(1)
        rest = rest[role_match.end():]

        # Extract label (quoted string after role)
        label_match = re.match(r'\s+"([^"]*)"', rest)
        if label_match:
            entry["label"] = label_match.group(1)
            rest = rest[label_match.end():]

        # Extract num (#N)
        num_match = re.search(r"#(\d+)", rest)
        if num_match:
            entry["num"] = num_match.group(1)

        # Extract all bracket attributes
        brackets = re.findall(r"\[([^\]]+)\]", rest)
        ref = None
        for b in brackets:
            if b.startswith("value="):
                # value="..."
                val_match = re.match(r'value="(.*)"', b)
                if val_match:
                    entry["value"] = val_match.group(1)
            elif b == "checked":
                entry["checked"] = True
            elif b == "required":
                entry["required"] = True
            elif b == "disabled":
                entry["disabled"] = True
            elif b == "invalid":
                entry["invalid"] = True
            elif b.startswith("h") and b[1:].isdigit():
                entry["level"] = b
            elif ref is None:
                # First non-special bracket is the ref
                ref = b

        if ref is None:
            continue
        entry["ref"] = ref

        # Use ref as key; if duplicate refs, append num to disambiguate
        key = ref
        if key in elements:
            key = f"{ref}#{entry.get('num', '')}"
        elements[key] = entry

    return elements


def format_entry(entry: dict) -> str:
    """Format an entry for display (role + label + num + ref + attrs)."""
    parts = [entry["role"]]
    if entry.get("label"):
        parts.append(f'"{entry["label"]}"')
    if entry.get("num"):
        parts.append(f'#{entry["num"]}')
    parts.append(f'[{entry["ref"]}]')
    if entry.get("required"):
        parts.append("[required]")
    if entry.get("checked"):
        parts.append("[checked]")
    if entry.get("disabled"):
        parts.append("[disabled]")
    if entry.get("invalid"):
        parts.append("[invalid]")
    if entry.get("level"):
        parts.append(f'[{entry["level"]}]')
    if entry.get("value"):
        parts.append(f'[value="{entry["value"]}"]')
    return " ".join(parts)


def diff_snapshots(old_path: Path, new_path: Path) -> None:
    old_els = parse_snapshot(old_path)
    new_els = parse_snapshot(new_path)

    old_keys = set(old_els.keys())
    new_keys = set(new_els.keys())

    added = new_keys - old_keys
    removed = old_keys - new_keys
    common = old_keys & new_keys

    lines: list[str] = []
    lines.append(f"# diff: {old_path.name} -> {new_path.name}")
    lines.append("")

    has_changes = False

    # Removed elements
    for key in sorted(removed):
        has_changes = True
        lines.append(f"- {format_entry(old_els[key])}")

    # Changed elements
    for key in sorted(common):
        old_e = old_els[key]
        new_e = new_els[key]
        changes: list[str] = []

        # Compare value
        old_val = old_e.get("value")
        new_val = new_e.get("value")
        if old_val != new_val:
            old_disp = f'[value="{old_val}"]' if old_val else "[no value]"
            new_disp = f'[value="{new_val}"]' if new_val else "[no value]"
            changes.append(f"{old_disp} -> {new_disp}")

        # Compare checked
        old_chk = old_e.get("checked", False)
        new_chk = new_e.get("checked", False)
        if old_chk != new_chk:
            changes.append(f"[checked={old_chk}] -> [checked={new_chk}]")

        # Compare disabled
        old_dis = old_e.get("disabled", False)
        new_dis = new_e.get("disabled", False)
        if old_dis != new_dis:
            changes.append(f"[disabled={old_dis}] -> [disabled={new_dis}]")

        # Compare label
        old_lab = old_e.get("label", "")
        new_lab = new_e.get("label", "")
        if old_lab != new_lab:
            changes.append(f'label "{old_lab}" -> "{new_lab}"')

        if changes:
            has_changes = True
            # Show the new state with the change detail
            base = format_entry(new_e)
            lines.append(f"~ {base}  {'; '.join(changes)}")

    # Added elements
    for key in sorted(added):
        has_changes = True
        lines.append(f"+ {format_entry(new_els[key])}")

    if not has_changes:
        lines.append("(no changes)")

    print("\n".join(lines))


def find_latest_snapshots() -> tuple[Path, Path]:
    """Find the two most recent snapshot files."""
    if not SNAPSHOT_DIR.exists():
        print("No .browser-use/ directory found.", file=sys.stderr)
        sys.exit(1)

    files = sorted(SNAPSHOT_DIR.glob("page-*.yml"), key=lambda p: p.name)
    if len(files) < 2:
        print(
            f"Need at least 2 snapshots to diff, found {len(files)}.",
            file=sys.stderr,
        )
        sys.exit(1)

    return files[-2], files[-1]


def main() -> None:
    args = sys.argv[1:]

    if len(args) == 0:
        old_path, new_path = find_latest_snapshots()
    elif len(args) == 2:
        old_path = Path(args[0])
        new_path = Path(args[1])
        if not old_path.exists():
            print(f"File not found: {old_path}", file=sys.stderr)
            sys.exit(1)
        if not new_path.exists():
            print(f"File not found: {new_path}", file=sys.stderr)
            sys.exit(1)
    else:
        print("Usage: bu diff [<old-snapshot> <new-snapshot>]", file=sys.stderr)
        sys.exit(1)

    diff_snapshots(old_path, new_path)


if __name__ == "__main__":
    main()
