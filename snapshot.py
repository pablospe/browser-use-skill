#!/usr/bin/env python3
"""Parse browser-use state output into structured YAML and save to file."""

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SKILL_DIR = Path(__file__).parent
SNAPSHOT_DIR = SKILL_DIR / ".browser-use"


def parse_element(raw: str) -> dict | None:
    """Parse a browser-use element line like [62]<input maxlength=400 type=text name=your-surname required=true />"""
    m = re.match(r"\[(\d+)\]<(\w+)\s*(.*?)\s*/?>", raw)
    if not m:
        return None
    idx, tag, attrs_str = m.group(1), m.group(2), m.group(3)
    el = {"ref": int(idx), "tag": tag}

    # Parse key=value attributes
    for am in re.finditer(r'(\w[\w-]*)=([^\s]+)', attrs_str):
        key, val = am.group(1), am.group(2)
        if val in ("true", "false"):
            val = val == "true"
        el[key] = val

    # Parse compound_components for selects (options list)
    comp = re.search(r'compound_components=\((.+)\)', attrs_str)
    if comp:
        options_m = re.search(r'options=([^)]+)', comp.group(1))
        if options_m:
            el["options"] = options_m.group(1).split("|")

    return el


def classify_element(el: dict) -> str:
    """Map tag+type to a role name similar to playwright-cli."""
    tag = el["tag"]
    typ = el.get("type", "")

    if tag == "select":
        return "combobox"
    if tag == "textarea":
        return "textbox"
    if tag == "input":
        if typ == "checkbox":
            return "checkbox"
        if typ == "radio":
            return "radio"
        if typ == "submit":
            return "button"
        if typ == "file":
            return "file-input"
        return "textbox"
    if tag == "button":
        return "button"
    if tag == "a":
        return "link"
    if tag == "img":
        return "image"
    return tag


def to_yaml_line(role: str, el: dict, label: str | None, indent: int) -> str:
    """Format one element as a YAML-like line matching playwright-cli style."""
    prefix = "  " * indent + "- "
    ref = f"[ref={el['ref']}]"

    # Build display name
    name_part = f' "{label}"' if label else ""

    # Attributes to show
    extras = []
    if el.get("required"):
        extras.append("[required]")
    if el.get("invalid"):
        extras.append("[invalid]")
    if el.get("checked") is True:
        extras.append("[checked]")
    if el.get("disabled"):
        extras.append("[disabled]")
    if el.get("value"):
        extras.append(f'[value="{el["value"]}"]')

    extra_str = " " + " ".join(extras) if extras else ""

    line = f"{prefix}{role}{name_part} {ref}{extra_str}"

    return line


INTERACTIVE_ROLES = {"textbox", "combobox", "checkbox", "radio", "button", "file-input"}
SKIP_TAGS = {"div", "span", "li", "label", "img"}


def build_snapshot(raw_text: str) -> list[str]:
    """Convert browser-use state text into structured YAML lines."""
    lines = raw_text.split("\n")
    yaml_lines = []
    current_label = None
    page_meta = {}

    for line in lines:
        stripped = line.strip()

        # Page metadata
        if stripped.startswith("viewport:"):
            page_meta["viewport"] = stripped.split(":", 1)[1].strip()
            continue
        if stripped.startswith("page:"):
            page_meta["page"] = stripped.split(":", 1)[1].strip()
            continue
        if stripped.startswith("scroll:"):
            page_meta["scroll"] = stripped.split(":", 1)[1].strip()
            continue

        # Strip shadow DOM markers
        if "|SHADOW" in stripped:
            stripped = re.sub(r'\|SHADOW\(open\)\|\*?', '', stripped).strip()
            if not stripped:
                continue

        # Try to parse as an element
        el_match = re.search(r'\[(\d+)\]<\w+.*?/?>', stripped)
        if el_match:
            raw_el = stripped[el_match.start():]
            el = parse_element(raw_el)
            if el:
                role = classify_element(el)

                # Skip non-interactive, non-link noise elements
                if role in SKIP_TAGS:
                    continue

                # Use preceding text as label
                label = current_label
                current_label = None

                yaml_line = to_yaml_line(role, el, label, indent=1)
                yaml_lines.append(yaml_line)

                # Show options for combobox
                if el.get("options"):
                    for opt in el["options"]:
                        yaml_lines.append(f"      - option \"{opt}\"")

                continue

        # Plain text lines — potential labels or link text
        if stripped and not stripped.startswith("[") and not stripped.startswith("|"):
            # Indented line = child text of previous element (link text, etc.)
            if line.startswith("\t") or line.startswith("  "):
                if yaml_lines:
                    last = yaml_lines[-1]
                    role_m = re.match(r'(\s*- \w[\w-]*)(.*?)(\[ref=\d+\].*)', last)
                    if role_m and '"' not in role_m.group(2):
                        yaml_lines[-1] = f'{role_m.group(1)} "{stripped}" {role_m.group(3)}'
            else:
                # Standalone text = label for the next element
                current_label = stripped

    # Build final output
    output = []
    output.append("# page:")
    for k, v in page_meta.items():
        output.append(f"#   {k}: {v}")
    output.append("")
    output.extend(yaml_lines)

    return output


def main():
    # Get extra args to pass to browser-use (e.g. --connect, --session)
    extra_args = sys.argv[1:]

    # Run browser-use --json state
    cmd = ["uv", "run", "--directory", str(SKILL_DIR), "browser-use", "--json"] + extra_args + ["state"]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)

    data = json.loads(result.stdout)
    raw_text = data.get("data", {}).get("_raw_text", "")
    if not raw_text:
        print("No state data", file=sys.stderr)
        sys.exit(1)

    # Also grab current URL via eval
    url_cmd = ["uv", "run", "--directory", str(SKILL_DIR), "browser-use", "--json"] + extra_args + ["eval", "window.location.href"]
    url_result = subprocess.run(url_cmd, capture_output=True, text=True)
    url = ""
    if url_result.returncode == 0:
        url_data = json.loads(url_result.stdout)
        url = url_data.get("data", {}).get("result", "")

    # Build YAML
    yaml_lines = build_snapshot(raw_text)

    # Prepend URL
    if url:
        yaml_lines.insert(0, f"# url: {url}")

    content = "\n".join(yaml_lines) + "\n"

    # Save to file
    SNAPSHOT_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%f")[:-3] + "Z"
    filename = f"page-{ts}.yml"
    filepath = SNAPSHOT_DIR / filename
    filepath.write_text(content)

    print(f"[Snapshot]({filepath.relative_to(Path.cwd()) if filepath.is_relative_to(Path.cwd()) else filepath})")


if __name__ == "__main__":
    main()
