#!/usr/bin/env python3
"""Full-DOM snapshot via JS eval — no viewport limits, stable refs, optional highlighting."""

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SKILL_DIR = Path(__file__).parent
SNAPSHOT_DIR = SKILL_DIR / ".browser-use"

# JS that scans the entire DOM for interactive elements and their labels.
# Returns JSON with url, title, elements[]. Uses name/id as stable ref.
# Optionally injects highlight overlays.
SCAN_JS = r"""
((highlight) => {
  // Remove previous highlights
  document.querySelectorAll('[data-bu-highlight]').forEach(el => el.remove());

  const getLabel = (el) => {
    // 1. Explicit <label for="id">
    if (el.id) {
      const lab = document.querySelector(`label[for="${el.id}"]`);
      if (lab) return lab.textContent.trim();
    }
    // 2. Ancestor <label>
    const ancestor = el.closest('label');
    if (ancestor) return ancestor.textContent.trim();
    // 3. Previous sibling or parent text
    let prev = el.parentElement;
    while (prev) {
      const text = prev.previousElementSibling?.textContent?.trim();
      if (text && text.length < 100) return text;
      prev = prev.parentElement;
      if (prev?.tagName === 'FORM' || prev?.tagName === 'BODY') break;
    }
    // 4. Placeholder or aria-label
    return el.getAttribute('aria-label') || el.getAttribute('placeholder') || '';
  };

  const roleMap = {
    'SELECT': 'combobox',
    'TEXTAREA': 'textbox',
    'BUTTON': 'button',
  };
  const inputTypeRole = {
    'checkbox': 'checkbox',
    'radio': 'radio',
    'submit': 'button',
    'file': 'file-input',
  };

  const els = document.querySelectorAll('input,select,textarea,button,[role="button"]');
  const results = [];
  let idx = 0;

  els.forEach((el) => {
    // Skip hidden elements
    if (el.offsetParent === null && el.type !== 'hidden') return;
    if (el.type === 'hidden') return;

    const tag = el.tagName;
    let role = roleMap[tag] || 'textbox';
    if (tag === 'INPUT') {
      role = inputTypeRole[el.type] || 'textbox';
    }

    const ref = el.name || el.id || `_idx${idx}`;
    const label = getLabel(el);

    const entry = { role, ref, label };

    // Value
    if (tag === 'SELECT') {
      entry.value = el.options[el.selectedIndex]?.text || '';
      entry.options = Array.from(el.options).map(o => o.text);
    } else if (el.type === 'checkbox' || el.type === 'radio') {
      if (el.checked) entry.checked = true;
    } else if (tag === 'BUTTON' || el.type === 'submit') {
      entry.value = el.textContent?.trim() || el.value || '';
    } else {
      if (el.value) entry.value = el.value;
    }

    // Attributes
    if (el.required) entry.required = true;
    if (el.disabled) entry.disabled = true;
    if (!el.validity?.valid && el.value !== '') entry.invalid = true;

    // Highlight overlay
    if (highlight) {
      const rect = el.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        const overlay = document.createElement('div');
        overlay.setAttribute('data-bu-highlight', '1');
        overlay.style.cssText = `
          position:absolute; z-index:99999; pointer-events:none;
          border:2px solid #e63946; background:rgba(230,57,70,0.08);
          border-radius:3px;
          left:${rect.left + window.scrollX - 1}px;
          top:${rect.top + window.scrollY - 1}px;
          width:${rect.width + 2}px;
          height:${rect.height + 2}px;
        `;
        const badge = document.createElement('span');
        badge.setAttribute('data-bu-highlight', '1');
        badge.textContent = ref;
        badge.style.cssText = `
          position:absolute; z-index:100000; pointer-events:none;
          background:#e63946; color:white; font:bold 10px monospace;
          padding:1px 4px; border-radius:2px; white-space:nowrap;
          left:${rect.left + window.scrollX}px;
          top:${Math.max(0, rect.top + window.scrollY - 16)}px;
        `;
        document.body.appendChild(overlay);
        document.body.appendChild(badge);
      }
    }

    results.push(entry);
    idx++;
  });

  return JSON.stringify({
    url: window.location.href,
    title: document.title,
    elements: results,
  });
})(%HIGHLIGHT%)
"""


def format_element(el: dict) -> str:
    """Format one element as a YAML-like line."""
    role = el["role"]
    ref = el["ref"]
    label = el.get("label", "")

    parts = [f'  - {role}']
    if label:
        parts.append(f' "{label}"')
    parts.append(f' [{ref}]')

    if el.get("required"):
        parts.append(" [required]")
    if el.get("invalid"):
        parts.append(" [invalid]")
    if el.get("checked"):
        parts.append(" [checked]")
    if el.get("disabled"):
        parts.append(" [disabled]")
    if el.get("value"):
        parts.append(f' [value="{el["value"]}"]')

    return "".join(parts)


def main():
    interactive_only = False
    highlight = False
    extra_args = []
    for arg in sys.argv[1:]:
        if arg in ("--interactive", "-i"):
            interactive_only = True
        elif arg in ("--highlight", "-h"):
            highlight = True
        else:
            extra_args.append(arg)

    # Build JS with highlight flag
    js = SCAN_JS.replace("%HIGHLIGHT%", "true" if highlight else "false")

    # Run single JS eval — scans full DOM, no viewport limits
    cmd = ["uv", "run", "--directory", str(SKILL_DIR), "browser-use", "--json"] + extra_args + ["eval", js]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)

    data = json.loads(result.stdout)
    result_str = data.get("data", {}).get("result", "")
    if not result_str:
        print("No data returned from eval", file=sys.stderr)
        sys.exit(1)

    page = json.loads(result_str)
    elements = page.get("elements", [])

    # Filter if interactive only (skip links — though we don't collect them via this JS)
    # All elements from this scan are interactive by nature

    # Detect CDP port
    cdp_port = ""
    try:
        ps = subprocess.run(["ps", "aux"], capture_output=True, text=True)
        m = re.search(r'remote-debugging-port=(\d+)', ps.stdout)
        if m:
            cdp_port = m.group(1)
    except Exception:
        pass

    # Build output
    lines = []
    lines.append(f'# url: {page.get("url", "")}')
    if cdp_port:
        lines.append(f"# cdp: localhost:{cdp_port}")
    lines.append(f'# title: {page.get("title", "")}')
    lines.append("")

    for el in elements:
        if interactive_only and el["role"] not in {"textbox", "combobox", "checkbox", "radio", "button", "file-input"}:
            continue
        lines.append(format_element(el))
        if el.get("options"):
            for opt in el["options"]:
                lines.append(f'      - option "{opt}"')

    content = "\n".join(lines) + "\n"

    # Save to file
    SNAPSHOT_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%f")[:-3] + "Z"
    filename = f"page-{ts}.yml"
    filepath = SNAPSHOT_DIR / filename
    filepath.write_text(content)

    print(f"[Snapshot]({filepath.relative_to(Path.cwd()) if filepath.is_relative_to(Path.cwd()) else filepath})")


if __name__ == "__main__":
    main()
