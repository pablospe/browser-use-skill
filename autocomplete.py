#!/usr/bin/env python3
"""Autocomplete/typeahead widget handler.

Handles React Select, Select2, MUI Autocomplete, and similar widgets by:
1. Clicking the input to focus it
2. Typing real keystrokes to trigger the dropdown
3. Polling for an option to appear (multiple selector strategies)
4. Clicking the matched option via JS

Usage:
  bu autocomplete <ref|#N> "value" [--wait 1.0]
"""

import json
import subprocess
import sys
import time
from pathlib import Path

SKILL_DIR = Path(__file__).parent

# Selectors to try for dropdown options, ordered by specificity
OPTION_SELECTORS = [
    '[role="option"]',                          # ARIA standard (React Select, MUI, Headless UI)
    '[class*="option"]:not([class*="container"])',  # React Select CSS modules
    '.select2-results__option',                 # Select2
    '[class*="menu"] [class*="item"]',          # Generic menu items
    'li[class*="result"]',                      # jQuery UI autocomplete
    '[data-value]',                             # Custom data-attribute based
    '.dropdown-item',                           # Bootstrap
    '.autocomplete-suggestion',                 # Various autocomplete libs
]


def run_bu(args: list[str], json_output: bool = False) -> str:
    """Run a browser-use CLI command and return output."""
    cmd = ["uv", "run", "--directory", str(SKILL_DIR), "browser-use"]
    if json_output:
        cmd.append("--json")
    cmd.extend(args)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def run_bu_eval(js: str) -> str | None:
    """Run JS eval and return the result string."""
    out = run_bu(["--json", "eval", js], json_output=False)
    if not out:
        return None
    try:
        data = json.loads(out)
        return data.get("data", {}).get("result")
    except (json.JSONDecodeError, AttributeError):
        return None


def click_ref(ref: str, extra_args: list[str]) -> None:
    """Click an element by ref or #N."""
    cmd = ["uv", "run", "--directory", str(SKILL_DIR), "python",
           str(SKILL_DIR / "cursor_action.py"), "click", ref] + extra_args
    subprocess.run(cmd, capture_output=True, text=True)


def type_text(text: str) -> None:
    """Type text using real keystrokes."""
    run_bu(["type", text])


def poll_and_click_option(value: str, timeout: float) -> str | None:
    """Poll for a dropdown option matching value and click it.

    Tries multiple CSS selectors. Returns the selected option text or None.
    """
    selectors_js = json.dumps(OPTION_SELECTORS)
    deadline = time.monotonic() + timeout
    poll_interval = 0.15

    while time.monotonic() < deadline:
        # Try all selectors, find the first option whose text contains our value
        js = f"""
        (() => {{
            const selectors = {selectors_js};
            const target = {json.dumps(value.lower())};
            for (const sel of selectors) {{
                const opts = document.querySelectorAll(sel);
                for (const opt of opts) {{
                    const text = opt.textContent.trim();
                    if (text.toLowerCase().includes(target)) {{
                        opt.click();
                        return JSON.stringify({{text, selector: sel}});
                    }}
                }}
            }}
            return null;
        }})()
        """
        result = run_bu_eval(js)
        if result and result != "null":
            try:
                info = json.loads(result)
                return info.get("text", value)
            except (json.JSONDecodeError, AttributeError):
                return result
        time.sleep(poll_interval)

    return None


def main():
    extra_args = []
    ref = None
    value = None
    wait = 2.0  # total polling timeout

    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--wait" and i + 1 < len(argv):
            i += 1
            wait = float(argv[i])
        elif arg.startswith("--"):
            extra_args.append(arg)
        elif ref is None:
            ref = arg
        elif value is None:
            value = arg
        i += 1

    if not ref or not value:
        print('Usage: bu autocomplete <ref|#N> "value" [--wait 2.0]', file=sys.stderr)
        sys.exit(1)

    # 1. Click to focus
    click_ref(ref, extra_args)

    # 2. Small delay for focus to settle
    time.sleep(0.1)

    # 3. Type to trigger dropdown (real keystrokes)
    type_text(value)

    # 4. Poll for option and click it
    selected = poll_and_click_option(value, wait)

    if selected:
        print(f"autocomplete {ref}: {selected}")
    else:
        # Fallback: try Tab to select whatever is highlighted
        run_bu(["keys", "Tab"])
        print(f"autocomplete {ref}: {value} (Tab fallback)")


if __name__ == "__main__":
    main()
