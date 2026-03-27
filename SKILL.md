---
name: browser-use
description: Automates browser interactions for web testing, form filling, screenshots, and data extraction. Use when the user needs to navigate websites, interact with web pages, fill forms, take screenshots, or extract information from web pages.
user-invocable: true
argument-hint: "[--connect] <command> [args] — e.g. --connect state"
---

# Browser Automation with browser-use

All commands use the self-contained wrapper `bu.sh`, which:
- **Auto-bootstraps** the local `.venv` on first run (downloads deps via `uv` — takes ~60s once)
- Sets `PYTHONUTF8=1` automatically (handles emoji/Unicode on Windows)
- Keeps a persistent browser daemon for ~50ms latency per call

**Shorthand** — in all examples, `bu` means:
```bash
bash ~/.claude/skills/browser-use/bu.sh
```

## Prerequisites

- `uv` must be installed (`uv --version`)
- First run will install browser-use from GitHub into `~/.claude/skills/browser-use/.venv`

## Core Workflow (recommended)

The fastest way to discover and fill forms:

```bash
# 1. Open page
bu --headed open https://example.com/form

# 2. Snapshot — full-DOM scan, stable name-based refs, saved to file
bu snapshot --forms              # form elements only
bu snapshot --forms --highlight  # + red overlays on page

# 3. Read snapshot (small enough to read directly, no grep needed)
# Output:
#   - textbox "Surname *" [your-surname] [required]
#   - combobox "Salutation" [salutation] [value="Mr."]
#   - checkbox "Consent" [acceptance] [checked]

# 4. Batch fill — single JS eval, all fields at once
bu fill '{"your-surname":"Smith","salutation":{"select":"Mrs."},"acceptance":{"check":true}}'

# 5. Verify
bu snapshot --forms
```

**Total: 2 shell calls** to discover + fill a form (vs 16+ with individual commands).

## Browser Modes

```bash
bu open <url>                         # Default: headless Chromium
bu --headed open <url>                # Visible window
bu --profile "Default" open <url>     # Real Chrome with Default profile (existing logins/cookies)
bu --profile "Profile 1" open <url>   # Real Chrome with named profile
bu --connect open <url>               # Auto-discover running Chrome via CDP
bu --cdp-url ws://localhost:9222/... open <url>  # Connect via specific CDP URL
```

`--connect`, `--cdp-url`, and `--profile` are mutually exclusive.

## Commands

```bash
# Navigation
bu open <url>                    # Navigate to URL
bu back                          # Go back in history
bu scroll down                   # Scroll down (--amount N for pixels)
bu scroll up                     # Scroll up
bu switch <tab>                  # Switch to tab by index
bu close-tab [tab]               # Close tab (current if no index)

# Page State
bu state                         # URL, title, clickable elements with indices (inline, viewport only)
bu snapshot                      # Full-DOM structured YAML saved to .browser-use/*.yml
bu snapshot --forms        # Form elements only (textbox, combobox, checkbox, button)
bu snapshot --highlight          # Inject red overlay badges on interactive elements
bu snapshot -i --highlight       # Both: form-only + highlights
bu screenshot [path.png]         # Screenshot (base64 if no path, --full for full page)

# Form Fill — single JS eval, uses name-based refs from snapshot
bu fill '<json>'                 # Batch fill (see Batch Fill section below)

# Interactions — use numeric indices from bu state
bu click <index>                 # Click element by index
bu click <x> <y>                 # Click at pixel coordinates
bu type "text"                   # Type into focused element
bu input <index> "text"          # Click element, then type
bu keys "Enter"                  # Send keyboard keys (also "Control+a", etc.)
bu select <index> "option"       # Select dropdown option
bu upload <index> <path>         # Upload file to file input
bu hover <index>                 # Hover over element
bu dblclick <index>              # Double-click element
bu rightclick <index>            # Right-click element

# Data Extraction
bu eval "js code"                # Execute JavaScript, return result
bu get title                     # Page title
bu get html [--selector "h1"]    # Page HTML (or scoped to selector)
bu get text <index>              # Element text content
bu get value <index>             # Input/textarea value
bu get attributes <index>        # Element attributes
bu get bbox <index>              # Bounding box (x, y, width, height)

# Wait
bu wait selector "css"           # Wait for element (--state visible|hidden|attached|detached, --timeout ms)
bu wait text "text"              # Wait for text to appear

# Cookies
bu cookies get [--url <url>]     # Get cookies (optionally filtered)
bu cookies set <name> <value>    # Set cookie (--domain, --secure, --http-only, --same-site, --expires)
bu cookies clear [--url <url>]   # Clear cookies
bu cookies export <file>         # Export to JSON
bu cookies import <file>         # Import from JSON

# Python — persistent session with browser access
bu python "code"                 # Execute Python (variables persist across calls)
bu python --file script.py       # Run file
bu python --vars                 # Show defined variables
bu python --reset                # Clear namespace

# Session
bu close                         # Close browser and stop daemon
bu sessions                      # List active sessions
bu close --all                   # Close all sessions

# Recipes — store and replay DOM access patterns (no screenshot on repeat runs)
bu recipe list                   # Show all installed recipes + run history
bu recipe run <name>             # Execute a recipe directly against the DOM
bu recipe run <name> --connect   # Override auth: use CDP connect mode
bu recipe run <name> --headed    # Override: show browser window (debug)
bu recipe show <name>            # Print recipe JSON
bu recipe save <name> --file <path>  # Install a recipe JSON file
bu recipe delete <name>          # Remove a recipe
```

The Python `browser` object provides: `browser.url`, `browser.title`, `browser.html`, `browser.goto(url)`, `browser.back()`, `browser.click(index)`, `browser.type(text)`, `browser.input(index, text)`, `browser.keys(keys)`, `browser.upload(index, path)`, `browser.screenshot(path)`, `browser.scroll(direction, amount)`, `browser.wait(seconds)`.

## Snapshot

Scans the **full DOM** via a single JS eval — no viewport limits, no missing elements.

```bash
bu snapshot                      # All elements (links, forms, buttons)
bu snapshot --forms        # Form elements only (recommended for forms)
bu snapshot --highlight          # Add red overlays + name badges on page
bu snapshot -i --highlight       # Both
```

### Output format

```yaml
# url: https://example.com/form
# cdp: localhost:33339
# title: My Form Page

  - combobox "Salutation*" [your-salutation] [value="Mr."]
      - option "Mr."
      - option "Mrs."
  - textbox "Surname *" [your-surname] [required] [value="Smith"]
  - textbox "Email *" [your-email] [required]
  - checkbox "Consent" [acceptance-1] [checked]
  - button [_idx15] [value="Submit"]
```

### Key features

| Feature | `bu state` (original) | `bu snapshot` (new) |
|---|---|---|
| DOM coverage | Viewport only | **Full DOM** |
| Refs | Numeric, change each call | **name attribute, stable** |
| Labels | Inline text | **Attached to elements** |
| Current values | Not shown | **`[value="..."]` on each field** |
| Highlights | None | **Red overlays with `--highlight`** |
| Output | Inline (eats tokens) | **Saved to `.browser-use/*.yml`** |
| CDP port | Not shown | **`# cdp: localhost:PORT`** |

### Refs

Snapshot uses the element's `name` attribute as the ref (e.g. `[your-surname]`, `[city]`). These are permanent — they never change between calls or page scrolls. For elements without a name, a fallback `[_idxN]` is used.

### Highlighting

With `--highlight`, red bordered overlays and name badges are injected on the page. Useful for debugging or visual confirmation. Highlights are removed on next snapshot call.

### Grepping (optional)

With `--forms`, the output is typically small enough to read directly. For full snapshots on complex pages, grep for interactive elements:

```bash
grep -E 'textbox|combobox|checkbox|button' .browser-use/page-*.yml
```

## Batch Fill

Fills multiple fields in a **single JS eval** using name-based refs from snapshot.

```bash
bu fill '{"your-surname":"Smith","your-email":"a@b.com","salutation":{"select":"Mrs."},"consent":{"check":true}}'
```

### Value types

| Value | Action | Example |
|---|---|---|
| `"text"` | Fill text input/textarea | `"your-surname":"Smith"` |
| `{"select":"opt"}` | Select dropdown option by visible text | `"salutation":{"select":"Mrs."}` |
| `{"check":true}` | Set checkbox/radio checked state | `"consent":{"check":true}` |

### How it works

- Uses `document.querySelector('[name="..."]')` to find elements — works on all elements regardless of viewport
- Dispatches proper `input` and `change` events for framework compatibility (React, Vue, etc.)
- Uses the correct prototype setter (`HTMLInputElement` vs `HTMLTextAreaElement`) to trigger React's synthetic events
- Reports `filled: N/M` with error details for any failures

## Cloud API

```bash
bu cloud connect                 # Provision cloud browser and connect
bu cloud connect --timeout 120 --proxy-country US  # With options
bu cloud login <api-key>         # Save API key (or set BROWSER_USE_API_KEY)
bu cloud logout                  # Remove API key
bu cloud v2 GET /browsers        # REST passthrough (v2 or v3)
bu cloud v2 POST /tasks '{"task":"...","url":"..."}'
bu cloud v2 poll <task-id>       # Poll task until done
```

## Common Workflows

### Form Filling (optimized)

```bash
bu --headed open https://example.com/form
bu snapshot -i --highlight
# read .browser-use/page-*.yml
bu fill '{"field1":"value1","field2":"value2","dropdown":{"select":"Option"}}'
bu snapshot -i  # verify
```

### Authenticated Browsing (existing Chrome session)

```bash
bu --connect open https://gmail.com   # Reuse logged-in Chrome via CDP
bu --connect snapshot -i
```

Requires Chrome launched with `--remote-debugging-port=9222`.

### Authenticated Browsing (Chrome profile)

```bash
bu profile list                                # Check available profiles
bu --profile "Default" open https://github.com # Already logged in
```

### Multi-tool via CDP

Snapshot includes the CDP port in metadata (`# cdp: localhost:PORT`). Other tools (Playwright, DevTools) can connect to the same browser:

```javascript
const browser = await chromium.connectOverCDP("http://localhost:33339");
```

### Extracting Data via JavaScript

```bash
bu --connect open https://x.com/notifications
bu --connect eval "Array.from(document.querySelectorAll('[data-testid=\"notification\"]')).slice(0,10).map(n => n.innerText).join('\n---\n')"
```

### Exposing Local Dev Servers

```bash
bu tunnel 3000                             # → https://abc.trycloudflare.com
bu open https://abc.trycloudflare.com
```

## Global Options

| Option | Description |
|--------|-------------|
| `--headed` | Show browser window |
| `--profile [NAME]` | Use real Chrome (bare `--profile` uses "Default") |
| `--connect` | Auto-discover running Chrome via CDP |
| `--cdp-url <url>` | Connect via CDP URL (`http://` or `ws://`) |
| `--session NAME` | Target a named session (default: "default") |
| `--json` | Output as JSON |
| `--mcp` | Run as MCP server via stdin/stdout |

## Tips

1. **Prefer `snapshot` over `state`** — full DOM, stable refs, values shown. Add `--forms` for form-only view
2. **Use `fill` instead of individual `input`/`select` commands** — single eval, no ref instability
3. **Use `--highlight` for debugging** — see which elements the snapshot found
4. **Use `--headed` for debugging** to see what the browser is doing
5. **Sessions persist** — browser stays open between commands
6. **`eval` with JS** is the most powerful extraction method for complex pages

## Troubleshooting

- **First run slow?** Normal — downloading ~200MB of deps into `.venv`. Subsequent runs are instant.
- **Browser won't start?** `bu close` then `bu --headed open <url>`
- **Element not found with `state`?** Use `snapshot` instead — it scans the full DOM
- **Ref changed between calls?** Use `snapshot` — refs are stable name attributes
- **Unicode errors?** Already handled — `bu.sh` sets `PYTHONUTF8=1` automatically
- **Highlights not showing?** Ensure `--headed` was used when opening the browser

## Cleanup

```bash
bu close           # Close browser session
bu tunnel stop --all  # Stop tunnels (if any)
```

## Recipe System

Recipes store DOM access patterns so repeated tasks skip visual discovery entirely.

**First run**: discover selectors manually → write a recipe JSON
**Repeat runs**: `bu recipe run <name>` executes JS directly — no screenshot, no element scanning

### Recipe JSON format

```json
{
  "name": "my_recipe",
  "version": 1,
  "description": "What this recipe does",
  "url": "https://example.com/page",

  "auth": {
    "mode": "connect",
    "profile": null,
    "headed": false,
    "session": "default"
  },

  "steps": [
    {
      "id": "nav",
      "type": "navigate",
      "url": "https://example.com/page",
      "wait_for": ".main-content",
      "wait_timeout_ms": 10000
    },
    {
      "id": "extract",
      "type": "eval",
      "js": "document.querySelector('.result')?.innerText",
      "output_var": "result",
      "fallback_selectors": [".alt-result", "[data-result]"]
    }
  ],

  "output": { "format": "text", "var": "result" },
  "metadata": { "created": "2026-01-01", "last_run": null, "run_count": 0, "broken_step": null }
}
```

### Step types

| Type | Required fields | What it does |
|------|----------------|--------------|
| `navigate` | `url` | Open URL; optionally wait for a CSS selector |
| `eval` | `js` | Run JavaScript; stores result in `output_var` |
| `click` | `index` | Click element by index from `bu state` |
| `input` | `index`, `text` | Click element then type text |
| `wait` | `selector` or `text` | Wait for element or text to appear |
| `scroll` | `direction` | Scroll `up` or `down` |

### Self-healing fallback

When an `eval` step fails:
1. Each `fallback_selectors` entry is tried as `document.querySelector('SEL')?.innerText`
2. First match wins — logged to stderr, recipe continues
3. If all fallbacks fail: screenshot saved to `recipes/.broken_<name>_<step>.png`, `broken_step` set in metadata, exit 1

### Sample recipe

See `recipes/x_notifications.json` — fetches X.com notifications using CDP connection.

### Platform support

Works on **Linux**, **macOS**, and **Windows** (Git Bash or WSL required on Windows).
`bash` must be available in PATH — it is on all standard configurations.
