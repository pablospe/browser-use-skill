#!/usr/bin/env python3
"""Batch fill form fields in one invocation via JSON map of ref->value.

Usage:
  bu fill '{"62":"Schmidt","63":"Anna","61":{"select":"Mrs."},"75":{"check":true}}'

Keys are ref numbers (as strings). Values are:
  - string: fill/input text into the element
  - {"select": "option"}: select a dropdown option
  - {"check": true/false}: check/uncheck a checkbox
"""

import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent


def run_bu(extra_args: list[str], cmd: list[str]) -> tuple[bool, str]:
    """Run a browser-use command and return (success, output)."""
    full = ["uv", "run", "--directory", str(SKILL_DIR), "browser-use"] + extra_args + cmd
    result = subprocess.run(full, capture_output=True, text=True)
    out = (result.stdout + result.stderr).strip()
    return result.returncode == 0, out


def main():
    # Separate extra flags (--connect, --session, etc.) from the JSON argument
    extra_args = []
    json_str = None
    for arg in sys.argv[1:]:
        if arg.startswith("-"):
            extra_args.append(arg)
        elif json_str is None:
            json_str = arg

    if not json_str:
        print("Usage: bu fill '{\"62\":\"text\",\"61\":{\"select\":\"Mr.\"}}'", file=sys.stderr)
        sys.exit(1)

    try:
        fields = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    errors = []
    filled = 0

    for ref, value in fields.items():
        if isinstance(value, str):
            ok, out = run_bu(extra_args, ["input", ref, value])
        elif isinstance(value, dict):
            if "select" in value:
                ok, out = run_bu(extra_args, ["select", ref, value["select"]])
            elif "check" in value:
                # click toggles checkbox state
                ok, out = run_bu(extra_args, ["click", ref])
            else:
                print(f"ref {ref}: unknown action {value}", file=sys.stderr)
                errors.append(ref)
                continue
        else:
            print(f"ref {ref}: unsupported value type {type(value).__name__}", file=sys.stderr)
            errors.append(ref)
            continue

        if ok:
            filled += 1
        else:
            print(f"ref {ref}: {out}", file=sys.stderr)
            errors.append(ref)

    print(f"filled: {filled}/{len(fields)}")
    if errors:
        print(f"errors: {', '.join(errors)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
