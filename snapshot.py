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
  const hlPairs = [];
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

    entry.num = idx;

    // Track for highlighting
    if (highlight && rect.width > 0 && rect.height > 0) {
      hlPairs.push({ el, ref, num: idx, color: hlColors[role] || '#6b7280' });
    }

    results.push(entry);
    idx++;
  });

  // Highlight system with repositioning
  if (highlight && hlPairs.length > 0) {
    const positionOverlays = () => {
      document.querySelectorAll('[data-bu-hl-overlay]').forEach(e => e.remove());
      hlPairs.forEach(({ el, ref, num, color }) => {
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) return;
        const ov = document.createElement('div');
        ov.setAttribute('data-bu-highlight', '1');
        ov.setAttribute('data-bu-hl-overlay', '1');
        ov.style.cssText = `position:absolute;z-index:99998;pointer-events:none;border:2px solid ${color};background:${color}11;border-radius:3px;left:${r.left+window.scrollX-1}px;top:${r.top+window.scrollY-1}px;width:${r.width+2}px;height:${r.height+2}px;`;
        const bd = document.createElement('span');
        bd.setAttribute('data-bu-highlight', '1');
        bd.setAttribute('data-bu-hl-overlay', '1');
        bd.textContent = `${num}:${ref}`;
        bd.style.cssText = `position:absolute;z-index:99999;pointer-events:none;background:${color};color:white;font:bold 10px monospace;padding:1px 4px;border-radius:2px;white-space:nowrap;left:${r.left+window.scrollX}px;top:${Math.max(0,r.top+window.scrollY-16)}px;`;
        document.body.appendChild(ov);
        document.body.appendChild(bd);
      });
    };

    positionOverlays();

    let resizeTimer;
    const onResize = () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(positionOverlays, 100); };
    window.addEventListener('resize', onResize);

    // Dismiss button
    const btn = document.createElement('div');
    btn.setAttribute('data-bu-highlight', '1');
    btn.innerHTML = '&times;';
    btn.title = 'Remove highlights';
    btn.style.cssText = `position:fixed;z-index:100001;cursor:pointer;top:8px;right:8px;width:32px;height:32px;background:#e63946;color:white;font:bold 20px sans-serif;border-radius:50%;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 8px rgba(0,0,0,0.3);user-select:none;`;
    btn.onclick = () => {
      document.querySelectorAll('[data-bu-highlight]').forEach(e => e.remove());
      window.removeEventListener('resize', onResize);
    };
    document.body.appendChild(btn);
  }

  return JSON.stringify({
    url: window.location.href,
    title: document.title,
    elements: results,
  });
})(%HIGHLIGHT%, %FORMS_ONLY%)
"""

TREE_JS = r"""
((highlight) => {
  document.querySelectorAll('[data-bu-highlight]').forEach(el => el.remove());

  const INTERESTING = new Set([
    'A','BUTTON','INPUT','SELECT','TEXTAREA',
    'H1','H2','H3','H4','H5','H6',
    'NAV','MAIN','HEADER','FOOTER','SECTION','ARTICLE','ASIDE','FORM',
    'UL','OL','LI','TABLE','DETAILS','SUMMARY','IMG','DIALOG',
  ]);
  const ARIA_ROLES = new Set([
    'button','link','tab','menuitem','navigation','search',
    'tablist','menu','dialog','alert','banner','complementary',
    'contentinfo','region','tabpanel',
  ]);

  const getRole = (el) => {
    const ar = el.getAttribute('role');
    if (ar) return ar;
    const tag = el.tagName;
    const type = el.type || '';
    const map = {
      A:'link', BUTTON:'button', SELECT:'combobox', TEXTAREA:'textbox',
      IMG:'image', NAV:'navigation', MAIN:'main', HEADER:'header',
      FOOTER:'footer', SECTION:'section', ARTICLE:'article', ASIDE:'aside',
      FORM:'form', UL:'list', OL:'list', LI:'listitem',
      TABLE:'table', DETAILS:'details', SUMMARY:'summary', DIALOG:'dialog',
    };
    if (tag === 'INPUT') {
      const im = {checkbox:'checkbox',radio:'radio',submit:'button',file:'file-input'};
      return im[type] || 'textbox';
    }
    if (/^H[1-6]$/.test(tag)) return 'heading';
    return map[tag] || null;
  };

  const getLabel = (el) => {
    const tag = el.tagName;
    if (tag === 'A' || tag === 'BUTTON' || tag === 'SUMMARY') {
      const t = el.textContent?.trim();
      if (t && t.length < 200) return t;
    }
    if (tag === 'IMG') return el.alt || el.title || '';
    if (/^H[1-6]$/.test(tag)) return el.textContent?.trim() || '';
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
    if (tag === 'NAV' || tag === 'MAIN' || tag === 'SECTION' || tag === 'FORM') {
      return el.getAttribute('aria-label') || el.getAttribute('id') || '';
    }
    if (el.id) {
      const lab = document.querySelector(`label[for="${el.id}"]`);
      if (lab) return lab.textContent.trim();
    }
    const anc = el.closest('label');
    if (anc) return anc.textContent.trim();
    let prev = el.parentElement;
    while (prev) {
      const t = prev.previousElementSibling?.textContent?.trim();
      if (t && t.length < 100) return t;
      prev = prev.parentElement;
      if (prev?.tagName === 'FORM' || prev?.tagName === 'BODY') break;
    }
    return el.getAttribute('placeholder') || el.title || '';
  };

  const getRef = (el, idx) => {
    if (el.name) return el.name;
    if (el.id) return el.id;
    if (el.tagName === 'A' && el.href) {
      try {
        const u = new URL(el.href);
        const p = u.pathname.replace(/\/+$/, '').split('/').pop();
        if (p && p.length < 50) return p;
      } catch {}
    }
    return `_idx${idx}`;
  };

  const hlColors = {
    link:'#2563eb', button:'#dc2626', textbox:'#0891b2', combobox:'#7c3aed',
    checkbox:'#16a34a', radio:'#16a34a', image:'#ea580c', heading:'#6b7280',
    navigation:'#6b7280', form:'#6b7280', section:'#6b7280',
    'file-input':'#ea580c', tab:'#7c3aed', menuitem:'#7c3aed',
  };

  const results = [];
  const hlPairs = [];
  let idx = 0;

  function walk(node, depth) {
    for (const child of node.children) {
      const tag = child.tagName;
      const ariaRole = child.getAttribute('role');
      const isInteresting = INTERESTING.has(tag) || (ariaRole && ARIA_ROLES.has(ariaRole));

      if (!isInteresting) {
        walk(child, depth);
        continue;
      }

      // Skip hidden
      if (child.offsetParent === null && child.type !== 'hidden' && tag !== 'NAV' && tag !== 'HEADER' && tag !== 'FOOTER' && tag !== 'MAIN') {
        continue;
      }
      if (child.type === 'hidden') { continue; }

      const role = getRole(child);
      if (!role) { walk(child, depth); continue; }

      const ref = getRef(child, idx);
      const label = getLabel(child);

      // Skip links/images with no label
      if ((role === 'link' || role === 'image') && !label) {
        walk(child, depth);
        continue;
      }

      const entry = { role, ref, depth };
      if (label) entry.label = label;

      if (tag === 'SELECT') {
        entry.value = child.options[child.selectedIndex]?.text || '';
        entry.options = Array.from(child.options).map(o => o.text);
      } else if (child.type === 'checkbox' || child.type === 'radio') {
        if (child.checked) entry.checked = true;
      } else if (tag === 'BUTTON' || child.type === 'submit') {
        const v = child.textContent?.trim() || child.value || '';
        if (v) entry.value = v;
      } else if (tag === 'INPUT' || tag === 'TEXTAREA') {
        if (child.value) entry.value = child.value;
      }
      if (tag === 'A' && child.href) entry.url = child.href;
      if (/^H[1-6]$/.test(tag)) entry.level = parseInt(tag[1]);
      if (child.required) entry.required = true;
      if (child.disabled) entry.disabled = true;
      if (child.validity && !child.validity.valid && child.value !== '') entry.invalid = true;

      entry.num = idx;

      // Track for highlighting
      if (highlight) {
        const rect = child.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0) {
          hlPairs.push({ el: child, ref, num: idx, color: hlColors[role] || '#6b7280' });
        }
      }

      results.push(entry);
      idx++;

      // Recurse into structural elements (nav, form, section, etc.)
      const structural = new Set(['navigation','form','section','article','main','header','footer','details','list','listitem','table','region','dialog']);
      if (structural.has(role)) {
        walk(child, depth + 1);
      }
      // Don't recurse into leaf elements (links, buttons, inputs)
    }
  }

  walk(document.body, 0);

  // Highlight system with repositioning
  if (highlight && hlPairs.length > 0) {
    const positionOverlays = () => {
      document.querySelectorAll('[data-bu-hl-overlay]').forEach(e => e.remove());
      hlPairs.forEach(({ el, ref, num, color }) => {
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) return;
        const ov = document.createElement('div');
        ov.setAttribute('data-bu-highlight', '1');
        ov.setAttribute('data-bu-hl-overlay', '1');
        ov.style.cssText = `position:absolute;z-index:99998;pointer-events:none;border:2px solid ${color};background:${color}11;border-radius:3px;left:${r.left+window.scrollX-1}px;top:${r.top+window.scrollY-1}px;width:${r.width+2}px;height:${r.height+2}px;`;
        const bd = document.createElement('span');
        bd.setAttribute('data-bu-highlight', '1');
        bd.setAttribute('data-bu-hl-overlay', '1');
        bd.textContent = `${num}:${ref}`;
        bd.style.cssText = `position:absolute;z-index:99999;pointer-events:none;background:${color};color:white;font:bold 10px monospace;padding:1px 4px;border-radius:2px;white-space:nowrap;left:${r.left+window.scrollX}px;top:${Math.max(0,r.top+window.scrollY-16)}px;`;
        document.body.appendChild(ov);
        document.body.appendChild(bd);
      });
    };

    positionOverlays();

    let resizeTimer;
    const onResize = () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(positionOverlays, 100); };
    window.addEventListener('resize', onResize);

    // Dismiss button
    const btn = document.createElement('div');
    btn.setAttribute('data-bu-highlight', '1');
    btn.innerHTML = '&times;';
    btn.title = 'Remove highlights';
    btn.style.cssText = `position:fixed;z-index:100001;cursor:pointer;top:8px;right:8px;width:32px;height:32px;background:#e63946;color:white;font:bold 20px sans-serif;border-radius:50%;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 8px rgba(0,0,0,0.3);user-select:none;`;
    btn.onclick = () => {
      document.querySelectorAll('[data-bu-highlight]').forEach(e => e.remove());
      window.removeEventListener('resize', onResize);
    };
    document.body.appendChild(btn);
  }

  return JSON.stringify({
    url: window.location.href,
    title: document.title,
    elements: results,
  });
})(%HIGHLIGHT%)
"""

FORM_ROLES = {"textbox", "combobox", "checkbox", "radio", "button", "file-input"}


def format_element(el: dict) -> str:
    """Format one element as a YAML-like line."""
    role = el["role"]
    ref = el["ref"]
    label = el.get("label", "")
    depth = el.get("depth", 0)
    indent = "  " * (depth + 1)

    num = el.get("num", "")
    parts = [f'{indent}- {role}']
    if label:
        # Truncate very long labels
        if len(label) > 80:
            label = label[:77] + "..."
        parts.append(f' "{label}"')
    parts.append(f' #{num}' if num != "" else '')
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
        url_indent = "  " * (depth + 2)
        parts.append(f'\n{url_indent}/url: {el["url"]}')

    return "".join(parts)


def main():
    forms_only = False
    highlight = False
    tree_mode = False
    extra_args = []
    for arg in sys.argv[1:]:
        if arg in ("--forms", "-f"):
            forms_only = True
        elif arg in ("--highlight", "-h"):
            highlight = True
        elif arg in ("--tree", "-t"):
            tree_mode = True
        else:
            extra_args.append(arg)

    # Choose JS scan: tree (nested) or flat
    if tree_mode:
        js = TREE_JS.replace("%HIGHLIGHT%", "true" if highlight else "false")
    else:
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
