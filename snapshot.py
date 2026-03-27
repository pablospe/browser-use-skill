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

# JS that scans the entire DOM for all interactive and structural elements.
# Returns JSON with url, title, elements[].
# Default: all interactive elements (links, buttons, inputs, nav, headings, images).
# With formsOnly=true: only form elements (input, select, textarea, button).
SCAN_JS = r"""
((highlight, formsOnly) => {
  // Remove previous highlights
  document.querySelectorAll('[data-bu-highlight]').forEach(el => el.remove());

  const getLabel = (el) => {
    const tag = el.tagName;
    // Links and buttons: use text content
    if (tag === 'A' || tag === 'BUTTON') {
      const text = el.textContent?.trim();
      if (text && text.length < 200) return text;
    }
    // Images: alt text
    if (tag === 'IMG') return el.alt || el.title || '';
    // Headings: text content
    if (/^H[1-6]$/.test(tag)) return el.textContent?.trim() || '';
    // ARIA label
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
    // Form elements: explicit <label>
    if (el.id) {
      const lab = document.querySelector(`label[for="${el.id}"]`);
      if (lab) return lab.textContent.trim();
    }
    const ancestor = el.closest('label');
    if (ancestor) return ancestor.textContent.trim();
    // Walk up for preceding text
    let prev = el.parentElement;
    while (prev) {
      const text = prev.previousElementSibling?.textContent?.trim();
      if (text && text.length < 100) return text;
      prev = prev.parentElement;
      if (prev?.tagName === 'FORM' || prev?.tagName === 'BODY') break;
    }
    return el.getAttribute('placeholder') || el.title || '';
  };

  const getRole = (el) => {
    const tag = el.tagName;
    const type = el.type || '';
    const ariaRole = el.getAttribute('role');
    if (ariaRole) return ariaRole;
    if (tag === 'A') return 'link';
    if (tag === 'BUTTON') return 'button';
    if (tag === 'SELECT') return 'combobox';
    if (tag === 'TEXTAREA') return 'textbox';
    if (tag === 'IMG') return 'image';
    if (/^H[1-6]$/.test(tag)) return 'heading';
    if (tag === 'NAV') return 'navigation';
    if (tag === 'INPUT') {
      const map = {checkbox:'checkbox', radio:'radio', submit:'button', file:'file-input'};
      return map[type] || 'textbox';
    }
    return tag.toLowerCase();
  };

  const getRef = (el, idx) => {
    // Stable ref: name > id > href-based > fallback
    if (el.name) return el.name;
    if (el.id) return el.id;
    if (el.tagName === 'A' && el.href) {
      try {
        const u = new URL(el.href);
        const path = u.pathname.replace(/\/+$/, '').split('/').pop();
        if (path && path.length < 50) return path;
      } catch {}
    }
    return `_idx${idx}`;
  };

  // Selector for all interesting elements
  const selector = formsOnly
    ? 'input,select,textarea,button,[role="button"]'
    : 'a[href],button,input,select,textarea,[role="button"],[role="link"],[role="tab"],[role="menuitem"],img[alt],h1,h2,h3,h4,h5,h6,nav,[role="navigation"],details,summary';

  const els = document.querySelectorAll(selector);
  const results = [];
  let idx = 0;

  const hlColors = {
    link: '#2563eb',
    button: '#dc2626',
    textbox: '#0891b2',
    combobox: '#7c3aed',
    checkbox: '#16a34a',
    radio: '#16a34a',
    image: '#ea580c',
    heading: '#6b7280',
    navigation: '#6b7280',
    'file-input': '#ea580c',
    tab: '#7c3aed',
    menuitem: '#7c3aed',
  };

  els.forEach((el) => {
    // Skip hidden
    if (el.offsetParent === null && el.type !== 'hidden' && el.tagName !== 'NAV') return;
    if (el.type === 'hidden') return;
    // Skip tiny/invisible
    const rect = el.getBoundingClientRect();
    if (el.tagName !== 'NAV' && rect.width === 0 && rect.height === 0) return;

    const role = getRole(el);
    const ref = getRef(el, idx);
    const label = getLabel(el);

    // Skip links/images with no label
    if ((role === 'link' || role === 'image') && !label) return;
    // Skip duplicate labels for same role (common in navs)

    const entry = { role, ref };
    if (label) entry.label = label;

    // Form-specific attributes
    if (el.tagName === 'SELECT') {
      entry.value = el.options[el.selectedIndex]?.text || '';
      entry.options = Array.from(el.options).map(o => o.text);
    } else if (el.type === 'checkbox' || el.type === 'radio') {
      if (el.checked) entry.checked = true;
    } else if (el.tagName === 'BUTTON' || el.type === 'submit') {
      const v = el.textContent?.trim() || el.value || '';
      if (v) entry.value = v;
    } else if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
      if (el.value) entry.value = el.value;
    }

    // Link href
    if (el.tagName === 'A' && el.href) {
      entry.url = el.href;
    }

    // Heading level
    if (/^H[1-6]$/.test(el.tagName)) {
      entry.level = parseInt(el.tagName[1]);
    }

    if (el.required) entry.required = true;
    if (el.disabled) entry.disabled = true;
    if (el.validity && !el.validity.valid && el.value !== '') entry.invalid = true;

    // Highlight
    if (highlight && rect.width > 0 && rect.height > 0) {
      const color = hlColors[role] || '#6b7280';
      const overlay = document.createElement('div');
      overlay.setAttribute('data-bu-highlight', '1');
      overlay.style.cssText = `
        position:absolute; z-index:99998; pointer-events:none;
        border:2px solid ${color}; background:${color}11;
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
        position:absolute; z-index:99999; pointer-events:none;
        background:${color}; color:white; font:bold 10px monospace;
        padding:1px 4px; border-radius:2px; white-space:nowrap;
        left:${rect.left + window.scrollX}px;
        top:${Math.max(0, rect.top + window.scrollY - 16)}px;
      `;
      document.body.appendChild(overlay);
      document.body.appendChild(badge);
    }

    results.push(entry);
    idx++;
  });

  return JSON.stringify({
    url: window.location.href,
    title: document.title,
    elements: results,
  });
})(%HIGHLIGHT%, %FORMS_ONLY%)
"""

FORM_ROLES = {"textbox", "combobox", "checkbox", "radio", "button", "file-input"}


def format_element(el: dict) -> str:
    """Format one element as a YAML-like line."""
    role = el["role"]
    ref = el["ref"]
    label = el.get("label", "")

    parts = [f'  - {role}']
    if label:
        # Truncate very long labels
        if len(label) > 80:
            label = label[:77] + "..."
        parts.append(f' "{label}"')
    parts.append(f' [{ref}]')

    if el.get("level"):
        parts.append(f' [h{el["level"]}]')
    if el.get("required"):
        parts.append(" [required]")
    if el.get("invalid"):
        parts.append(" [invalid]")
    if el.get("checked"):
        parts.append(" [checked]")
    if el.get("disabled"):
        parts.append(" [disabled]")
    if el.get("value"):
        val = el["value"]
        if len(val) > 60:
            val = val[:57] + "..."
        parts.append(f' [value="{val}"]')
    if el.get("url"):
        parts.append(f'\n      /url: {el["url"]}')

    return "".join(parts)


def main():
    forms_only = False
    highlight = False
    extra_args = []
    for arg in sys.argv[1:]:
        if arg in ("--forms", "-f"):
            forms_only = True
        elif arg in ("--highlight", "-h"):
            highlight = True
        else:
            extra_args.append(arg)

    # Build JS with flags
    js = SCAN_JS.replace("%HIGHLIGHT%", "true" if highlight else "false")
    js = js.replace("%FORMS_ONLY%", "true" if forms_only else "false")

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
