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
bu snapshot --forms --highlight  # + color-coded overlays with numbered badges

# 3. Read snapshot (small enough to read directly, no grep needed)
# Output:
#   - combobox "Salutation" #0 [salutation] [value="Mr."]
#   - textbox "Surname *" #1 [your-surname] [required]
#   - checkbox "Consent" #2 [acceptance] [checked]
#   - combobox "Country" #3 [react-select-1-input]    ← autocomplete widget

# 4. Batch fill standard fields — single JS eval, all at once
bu fill '{"your-surname":"Smith","salutation":{"select":"Mrs."},"acceptance":{"check":true}}'

# 5. Autocomplete widgets — real keystrokes + option click
bu autocomplete '#3' "Germany"

# 6. Verify
bu snapshot --forms
```

**Standard fields**: use `bu fill` (one call for all text, checkbox, radio, native select).
**Autocomplete/typeahead widgets**: use `bu autocomplete` (React Select, Select2, MUI, etc.).

### User selection workflow

With `--highlight`, the user can click badges in the browser to select elements:

```bash
bu snapshot --forms --highlight  # badges appear on page
# User clicks badges to select elements (turns gold with checkmark)
bu selected                      # returns selected elements as JSON
# result: [{"num":1,"ref":"your-surname"},{"num":3,"ref":"address"}]
```

This enables conversations like "fix the selected elements" or "element #3 has the wrong value".

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
bu open <url>                    # Navigate current tab to URL
bu back                          # Go back in history
bu scroll down                   # Scroll down (--amount N for pixels)
bu scroll up                     # Scroll up
bu switch <tab>                  # Switch to tab by index
bu close-tab [tab]               # Close tab (current if no index)

# Tabs — bu open navigates the current tab; use eval to open a new tab
bu eval "window.open('https://example.com', '_blank')"  # Open URL in new tab
bu switch 0                      # Switch to first tab
bu switch 1                      # Switch to second tab

# Page State
bu state                         # URL, title, clickable elements with indices (inline, viewport only)
bu snapshot                      # Full-DOM structured YAML saved to .browser-use/*.yml
bu snapshot --forms              # Form elements only (textbox, combobox, checkbox, button)
bu snapshot --highlight          # Color-coded overlays with numbered clickable badges
bu snapshot --forms --highlight  # Form-only + highlights
bu snapshot --tree               # Nested DOM hierarchy (shows parent-child structure)
bu snapshot --tree --highlight   # Tree mode + highlights
bu snapshot --aria               # Accessibility tree via CDP (roles, names, values)
bu snapshot --aria --cdp-port 9222  # Aria mode with explicit CDP port
bu screenshot [path.png]         # Screenshot (base64 if no path, --full for full page)

# Highlight Interaction
bu selected                      # Read user-selected elements (click badges to select)
bu clear-highlights              # Remove all highlight overlays from page

# Form Fill — single JS eval, uses name/id refs from snapshot
bu fill '<json>'                 # Batch fill (see Batch Fill section below)
bu autocomplete <ref> "value"    # Typeahead/autocomplete widgets (see Autocomplete section)

# Interactions — ref-based (from snapshot) or index-based (from bu state)
bu click <ref>                   # Click by ref name (e.g. "your-surname")
bu click <#N>                    # Click by snapshot number (e.g. "#5")
bu click <x> <y>                 # Click at pixel coordinates
bu hover <ref>                   # Hover via CDP (triggers real CSS :hover for dropdown menus)
bu hover <#N>                    # Hover by snapshot number
bu scroll-to <ref>               # Scroll to element by ref name
bu scroll-to <#N>                # Scroll to element by snapshot number
bu type "text"                   # Type into focused element
bu input <index> "text"          # Click element by index, then type
bu keys "Enter"                  # Send keyboard keys (also "Control+a", etc.)
bu select <index> "option"       # Select dropdown option
bu upload <index> <path>         # Upload file to file input
bu dblclick <index>              # Double-click element
bu rightclick <index>            # Right-click element

# AI Cursor — visible red dot that moves to elements
bu cursor show                   # Show cursor dot
bu cursor hide                   # Hide cursor dot
bu cursor-fill '<json>'          # Animated cursor: moves to each field before filling

# Snapshot Comparison
bu diff                          # Compare two most recent snapshots
bu diff <old.yml> <new.yml>      # Compare specific snapshot files

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
bu snapshot                      # All elements (links, forms, buttons, headings, nav)
bu snapshot --forms              # Form elements only (recommended for forms)
bu snapshot --highlight          # Color-coded overlays with numbered clickable badges
bu snapshot --forms --highlight  # Both
bu snapshot --tree               # Nested DOM hierarchy (parent-child structure)
bu snapshot --tree --highlight   # Tree + highlights
bu snapshot --aria               # Accessibility tree via CDP
```

Flags: `--forms` / `-f`, `--highlight` / `-h`, `--tree` / `-t`, `--aria` / `-a`.

### Output format

```yaml
# url: https://example.com/form
# cdp: localhost:33339
# title: My Form Page

  - combobox "Salutation*" #0 [your-salutation] [value="Mr."]
      - option "Mr."
      - option "Mrs."
  - textbox "Surname *" #1 [your-surname] [required] [value="Smith"]
  - textbox "Email *" #2 [your-email] [required]
  - checkbox "Consent" #3 [acceptance-1] [checked]
  - button #4 [_idx15] [value="Submit"]
```

### Element numbering

Each element gets a sequential `#N` in the YAML output and on visual badges (`0:your-salutation`). Use `#N` as a quick conversation handle ("element #3 is wrong") while name-based refs (`[your-surname]`) remain the stable key for `bu fill`.

### Key features

| Feature | `bu state` (original) | `bu snapshot` (new) |
|---|---|---|
| DOM coverage | Viewport only | **Full DOM** |
| Refs | Numeric, change each call | **name attribute, stable** |
| Numbering | Indices only | **#N in YAML + visual badges** |
| Labels | Inline text | **Attached to elements** |
| Current values | Not shown | **`[value="..."]` on each field** |
| Highlights | None | **Color-coded overlays with `--highlight`** |
| Selection | None | **Click badges to select, `bu selected` to read** |
| Output | Inline (eats tokens) | **Saved to `.browser-use/*.yml`** |
| CDP port | Not shown | **`# cdp: localhost:PORT`** |
| Structure | Flat list | **Nested tree with `--tree`** |

### Refs

Snapshot uses the element's `name` attribute as the ref (e.g. `[your-surname]`, `[city]`). These are permanent — they never change between calls or page scrolls. For elements without a name, a fallback `[_idxN]` is used.

### Highlighting

With `--highlight`, color-coded bordered overlays and numbered badges are injected on the page:
- **Color by role**: blue (links), red (buttons), cyan (textboxes), purple (dropdowns), green (checkboxes)
- **Numbered badges**: show `N:ref` (e.g. `3:your-surname`) for quick identification
- **Clickable**: click a badge to select/deselect it (turns gold with checkmark)
- **Resize-safe**: overlays reposition automatically when the window is resized
- **Dismiss button**: red X button in the top-right corner removes all highlights
- Highlights are also cleared on the next snapshot call

### Selection

Click badges to toggle selection. Selected elements get a gold border and checkmark prefix.

```bash
bu selected   # Returns JSON: [{"num":1,"ref":"your-surname"},{"num":3,"ref":"address"}]
```

Selections persist across snapshot calls (stored in `window.__buSelected`). Use `bu clear-highlights` to remove all overlays and reset.

### Tree mode

With `--tree`, the output shows nested DOM structure (parent-child relationships):

```yaml
  - navigation "Main-menu" #0 [_idx4]
    - list "Skip to content" #1 [menu-main-menu]
      - listitem "Toggle Navigation" #2 [menu-item-7024]
        - link "Range of treatment" #3 [range-of-treatment]
  - main "main" #10 [main]
    - section "content" #11 [content]
      - form "Contact form" #12 [_idx73]
        - textbox "Surname *" #13 [your-surname] [value="Smith"]
```

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
| `{"select":"opt"}` | Select dropdown option by text or value | `"salutation":{"select":"Mrs."}` |
| `{"select":"val"}` | Select radio button by value | `"size":{"select":"medium"}` |
| `{"check":true}` | Set checkbox checked state | `"consent":{"check":true}` |

### How it works

- Finds elements by `name` attribute first, falls back to `id` — works with most forms
- Works on all elements regardless of viewport position
- Dispatches proper `input` and `change` events for framework compatibility (React, Vue, etc.)
- Uses the correct prototype setter (`HTMLInputElement` vs `HTMLTextAreaElement`) to trigger React's synthetic events
- Reports `filled: N/M` with error details for any failures
- **Does not handle autocomplete/typeahead widgets** — use `bu autocomplete` for those

## Autocomplete

Handles typeahead/autocomplete widgets (React Select, Select2, MUI Autocomplete, Headless UI, etc.) that need real keystrokes to trigger a dropdown.

```bash
bu autocomplete <ref|#N> "value"          # Type and select matching option
bu autocomplete <ref|#N> "value" --wait 5 # Custom timeout (default: 3s)
```

### How it works

1. **Clicks** the input to focus it
2. **Clears** any existing text (Ctrl+A + Backspace)
3. **Types** real keystrokes to trigger the dropdown
4. **Polls** for a matching option using multiple CSS selectors
5. **Clicks** the matched option via JS
6. **Verifies** the dropdown closed; sends Escape if not
7. **Falls back** to Tab if no option found (selects highlighted item)

### Supported widgets

Polls 10 CSS selectors covering most autocomplete libraries:

| Selector | Widget |
|----------|--------|
| `[role="option"]` | React Select, MUI, Headless UI, Radix |
| `[role="listbox"] > *` | ARIA listbox pattern |
| `[class*="option"]` | React Select CSS modules |
| `.select2-results__option` | Select2 |
| `[class*="menu"] [class*="item"]` | Generic menu items |
| `li[class*="result"]` | jQuery UI autocomplete |
| `.dropdown-item` | Bootstrap |

### Why not `bu keys "Enter"`?

**Enter often submits the form** when used inside autocomplete fields. The autocomplete command avoids this by clicking the option via JS or falling back to Tab. Never use `bu keys "Enter"` to select autocomplete options inside forms.

### Example

```bash
bu snapshot --forms
# Shows: combobox "Select State" #14 [react-select-3-input]

bu autocomplete '#14' "NCR"
# autocomplete #14: NCR
```

## Click, Hover, and Scroll by Ref

Use ref names or `#N` numbers from snapshots to interact with elements:

```bash
bu click custname                # Click by ref name
bu click '#5'                    # Click by snapshot number
bu click 400 300                 # Click at pixel coordinates (x y)
bu hover range-of-treatment      # Hover — triggers CSS :hover (dropdown menus)
bu hover '#3'                    # Hover by number
bu scroll-to custtel             # Scroll to element
bu scroll-to '#12'               # Scroll to element by number
```

### CDP-powered hover

`bu hover` uses Chrome DevTools Protocol to trigger **real CSS `:hover`** states, not just JavaScript events. This means dropdown menus, tooltips, and other CSS `:hover` effects actually work. The implementation:

1. **JS `mouseover`/`mouseenter`** — dispatched as fallback for JS event handlers
2. **`Input.dispatchMouseEvent`** — real browser cursor movement via CDP
3. **`CSS.forcePseudoState`** — forces `:hover` on the element and its parent (reliable for CSS dropdown menus)

Output shows the method used: `hovered (CDP): a[ref=foo]` vs `hovered (JS-only): a[ref=foo]`.

### CDP-powered click

`bu click <ref>` also dispatches real CDP `mousePressed`/`mouseReleased` events in addition to JS `.click()`, ensuring native click handlers work.

## AI Cursor

A visual red glowing dot that moves to elements, showing where the AI is acting:

```bash
bu cursor show                   # Show the cursor dot
bu cursor hide                   # Hide the cursor dot
bu click custname                # Cursor moves to element, shows click ripple
bu hover about-us                # Cursor moves to element
bu cursor-fill '{"custname":"John","custemail":"j@test.com"}'  # Animated fill
```

The cursor persists across commands (stored in `window.__buCursor`) and repositions on scroll.

## Diff Snapshots

Compare two snapshots to see what changed:

```bash
bu diff                          # Compare two most recent snapshots
bu diff old.yml new.yml          # Compare specific files
```

Output shows added (`+`), removed (`-`), and changed (`~`) elements:

```
~ [custname] value: "" → "John Smith"
~ [topping] checked: false → true
+ [new-field] textbox "New Field"
- [removed-field] button "Old Button"
```

## Accessibility Tree (--aria)

The `--aria` flag uses CDP `Accessibility.getFullAXTree` to get the browser's accessibility tree instead of scanning the DOM:

```bash
bu snapshot --aria               # Auto-detect CDP port
bu snapshot --aria --cdp-port 9222  # Explicit CDP port
```

This provides semantic roles, computed names, and states as the browser sees them — useful for accessibility testing and when DOM scanning misses ARIA attributes.

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
bu snapshot --forms --highlight
# read .browser-use/page-*.yml
bu fill '{"field1":"value1","field2":"value2","dropdown":{"select":"Option"},"checkbox1":{"check":true}}'
bu autocomplete '#5' "Search term"   # for any typeahead/autocomplete widgets
bu snapshot --forms  # verify
```

### Interactive Review with User

```bash
bu --headed open https://example.com/form
bu snapshot --forms --highlight       # user sees numbered badges
# user clicks badges to select problematic elements
bu selected                           # AI reads which elements were selected
# AI can now address specific elements by #N
```

### Authenticated Browsing (existing Chrome session)

```bash
bu --connect open https://gmail.com   # Reuse logged-in Chrome via CDP
bu --connect snapshot --forms
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

1. **Prefer `snapshot` over `state`** — full DOM, stable refs, values shown, numbered elements
2. **Use `fill` instead of individual `input`/`select` commands** — single eval, no ref instability
3. **Use `--highlight` for visual debugging** — color-coded overlays with clickable numbered badges
4. **Use `--forms` for form pages** — filters to form elements only, keeps output small
5. **Use `--tree` for structural context** — shows nested DOM hierarchy
6. **Use `bu selected` for interactive workflows** — let users click to select elements
7. **Use `bu hover` for dropdown menus** — CDP-powered hover triggers real CSS `:hover`
8. **Use `bu click <ref>` or `bu click '#N'`** — click by ref name or snapshot number
9. **Use `bu diff` to track changes** — compare before/after snapshots
10. **Use `--headed` for debugging** to see what the browser is doing
11. **New tabs via eval** — `bu open` navigates the current tab; use `bu eval "window.open('url', '_blank')"` then `bu switch N`
12. **Sessions persist** — browser stays open between commands
13. **`eval` with JS** is the most powerful extraction method for complex pages
14. **Use `bu autocomplete` for typeahead widgets** — React Select, Select2, MUI, etc. Never use `bu keys "Enter"` to select autocomplete options inside forms (it submits the form)

## Troubleshooting

- **First run slow?** Normal — downloading ~200MB of deps into `.venv`. Subsequent runs are instant.
- **Browser won't start?** `bu close` then `bu --headed open <url>`
- **Element not found with `state`?** Use `snapshot` instead — it scans the full DOM
- **Ref changed between calls?** Use `snapshot` — refs are stable name attributes
- **Unicode errors?** Already handled — `bu.sh` sets `PYTHONUTF8=1` automatically
- **Highlights not showing?** Ensure `--headed` was used when opening the browser
- **Highlights mispositioned?** They auto-reposition on resize; click X to dismiss and re-snapshot

## Cleanup

```bash
bu close           # Close browser session
bu clear-highlights  # Remove highlight overlays without closing
bu tunnel stop --all  # Stop tunnels (if any)
```

## Recipe System

Recipes store DOM access patterns so repeated tasks skip visual discovery entirely.

**First run**: discover selectors manually -> write a recipe JSON
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
