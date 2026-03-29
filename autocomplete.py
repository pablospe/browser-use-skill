#!/usr/bin/env python3
"""Autocomplete/typeahead widget handler.

Handles React Select, Select2, MUI Autocomplete, and similar widgets by:
1. Clicking the input to focus it
2. Clearing any existing text
3. Typing real keystrokes to trigger the dropdown
4. Polling for an option to appear (multiple selector strategies)
5. Clicking the matched option, with Tab fallback

IMPORTANT: Avoid using `bu keys "Enter"` on autocomplete fields inside forms —
Enter often submits the form. This script uses JS click on the option instead,
and falls back to Tab which selects without submitting.

Usage:
  bu autocomplete <ref|#N> "value" [--wait 2.0]
"""

import json
import subprocess
import sys
import time
from pathlib import Path

SKILL_DIR = Path(__file__).parent

# Selectors to try for dropdown options, ordered by likelihood.
# Each is tried against the live DOM when polling for the dropdown to appear.
OPTION_SELECTORS = [
    '[role="option"]',                              # ARIA standard (React Select, MUI, Headless UI, Radix)
    '[role="listbox"] > *',                         # ARIA listbox children
    '[class*="option"]:not([class*="container"])',   # React Select CSS modules
    '.select2-results__option',                      # Select2
    '[class*="menu"] [class*="item"]',               # Generic menu items
    'li[class*="result"]',                           # jQuery UI autocomplete
    '.dropdown-item',                                # Bootstrap
    '.autocomplete-suggestion',                      # Various autocomplete libs
    '[class*="listbox"] > *',                        # MUI variants
    '[data-value]',                                  # Custom data-attribute based
]


def run_bu(args: list[str]) -> str:
    """Run a browser-use CLI command and return stdout."""
    cmd = ["uv", "run", "--directory", str(SKILL_DIR), "browser-use"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ""


def run_bu_eval(js: str) -> str | None:
    """Run JS eval and return the result string."""
    out = run_bu(["--json", "eval", js])
    if not out:
        return None
    try:
        data = json.loads(out)
        return data.get("data", {}).get("result")
    except (json.JSONDecodeError, AttributeError):
        return None


def click_ref(ref: str, extra_args: list[str]) -> None:
    """Click an element by ref or #N via cursor_action."""
    cmd = ["uv", "run", "--directory", str(SKILL_DIR), "python",
           str(SKILL_DIR / "cursor_action.py"), "click", ref] + extra_args
    subprocess.run(cmd, capture_output=True, text=True)


def type_text(text: str) -> None:
    """Type text using real keystrokes."""
    run_bu(["type", text])


def send_keys(keys: str) -> None:
    """Send keyboard keys."""
    run_bu(["keys", keys])


def clear_input() -> None:
    """Select all text in focused input and delete it."""
    send_keys("Control+a")
    send_keys("Backspace")


def poll_for_options(value: str, timeout: float) -> str | None:
    """Poll for dropdown options matching value. Returns JS to click, or None."""
    selectors_js = json.dumps(OPTION_SELECTORS)
    target_js = json.dumps(value.lower())
    deadline = time.monotonic() + timeout
    poll_interval = 0.15

    while time.monotonic() < deadline:
        # Find and click the first option whose text matches
        js = f"""
        (() => {{
            const selectors = {selectors_js};
            const target = {target_js};
            for (const sel of selectors) {{
                const opts = document.querySelectorAll(sel);
                for (const opt of opts) {{
                    const text = opt.textContent.trim();
                    if (text.toLowerCase().includes(target)) {{
                        opt.scrollIntoView({{block: 'nearest'}});
                        opt.click();
                        return JSON.stringify({{text, selector: sel, count: opts.length}});
                    }}
                }}
            }}
            // Check if any options exist at all (dropdown open but no match)
            for (const sel of selectors) {{
                const opts = document.querySelectorAll(sel);
                if (opts.length > 0) {{
                    return JSON.stringify({{noMatch: true, selector: sel, count: opts.length,
                        available: Array.from(opts).slice(0, 5).map(o => o.textContent.trim())}});
                }}
            }}
            return null;
        }})()
        """
        result = run_bu_eval(js)
        if not result or result == "null":
            time.sleep(poll_interval)
            continue

        try:
            info = json.loads(result)
        except (json.JSONDecodeError, AttributeError):
            time.sleep(poll_interval)
            continue

        if info.get("noMatch"):
            # Dropdown is open but no option matches our text
            available = info.get("available", [])
            print(f"  warning: no option matching '{value}', "
                  f"available: {available}", file=sys.stderr)
            return None

        # Option was clicked
        return info.get("text", value)

    return None


def verify_selection(value: str) -> bool:
    """Check if the dropdown closed (option was actually selected)."""
    # If no options are visible anymore, selection worked
    result = run_bu_eval("""
    (() => {
        const checks = ['[role="option"]', '[role="listbox"]', '[class*="menu-list"]', '[class*="dropdown-menu"]'];
        for (const sel of checks) {
            const el = document.querySelector(sel);
            if (el && el.offsetParent !== null) return 'open';
        }
        return 'closed';
    })()
    """)
    return result == "closed"


def main():
    extra_args = []
    ref = None
    value = None
    wait = 3.0  # total polling timeout

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
        print('Usage: bu autocomplete <ref|#N> "value" [--wait 3.0]', file=sys.stderr)
        sys.exit(1)

    # 1. Click to focus
    click_ref(ref, extra_args)
    time.sleep(0.1)

    # 2. Clear any existing text
    clear_input()
    time.sleep(0.05)

    # 3. Type to trigger dropdown (real keystrokes)
    type_text(value)

    # 4. Poll for option and click it via JS
    selected = poll_for_options(value, wait)

    if selected:
        # 5. Verify the dropdown actually closed
        time.sleep(0.1)
        if verify_selection(value):
            print(f"autocomplete {ref}: {selected}")
        else:
            # Dropdown still open — JS click didn't fully work, try Tab
            send_keys("Escape")
            time.sleep(0.05)
            print(f"autocomplete {ref}: {selected}")
    else:
        # No option found — try Tab as last resort (selects highlighted option)
        send_keys("Tab")
        print(f"autocomplete {ref}: {value} (Tab fallback)", file=sys.stderr)
        print(f"autocomplete {ref}: {value}")


if __name__ == "__main__":
    main()
