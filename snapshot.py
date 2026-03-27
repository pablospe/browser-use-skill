#!/usr/bin/env python3
"""Full-DOM snapshot via JS eval — no viewport limits, stable refs, optional highlighting.

--aria mode uses Chrome's native Accessibility API via CDP (Accessibility.getFullAXTree)
instead of DOM walking, giving the same rich accessibility tree that devtools exposes.
"""

import json
import re
import subprocess
import sys
import urllib.request
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

  // Process a single element, optionally tagged with a frame descriptor
  const processEl = (el, frameDesc) => {
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

    const entry = { role, ref };
    if (label) entry.label = label;
    if (frameDesc) entry.frame = frameDesc;

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
  };

  // Scan a root (document or shadowRoot) for matching elements, including shadow DOM
  const scanRoot = (root, frameDesc) => {
    const els = root.querySelectorAll(selector);
    els.forEach(el => processEl(el, frameDesc));
    // Recurse into Shadow DOM: find all elements with a shadowRoot
    root.querySelectorAll('*').forEach(el => {
      if (el.shadowRoot) {
        scanRoot(el.shadowRoot, frameDesc);
      }
    });
  };

  // Scan main document
  scanRoot(document, null);

  // Scan same-origin iframes
  document.querySelectorAll('iframe').forEach(iframe => {
    let iframeDoc;
    try { iframeDoc = iframe.contentDocument; } catch(e) { /* cross-origin */ }
    if (!iframeDoc) {
      // Record cross-origin iframe as a comment marker
      const id = iframe.id ? '#' + iframe.id : (iframe.name ? '[name=' + iframe.name + ']' : '');
      results.push({ role: 'iframe-boundary', ref: 'iframe' + id, label: '(cross-origin, not accessible)', num: idx++ });
      return;
    }
    const id = iframe.id ? '#' + iframe.id : (iframe.name ? '[name=' + iframe.name + ']' : '');
    const frameDesc = 'iframe' + id;
    scanRoot(iframeDoc, frameDesc);
  });

  // Highlight system with repositioning + selection
  if (highlight && hlPairs.length > 0) {
    if (!window.__buSelected) window.__buSelected = new Map();
    const sel = window.__buSelected;

    const positionOverlays = () => {
      document.querySelectorAll('[data-bu-hl-overlay]').forEach(e => e.remove());
      hlPairs.forEach(({ el, ref, num, color }) => {
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) return;
        const isSel = sel.has(num);
        const borderColor = isSel ? '#f59e0b' : color;
        const borderWidth = isSel ? '3px' : '2px';
        const ov = document.createElement('div');
        ov.setAttribute('data-bu-highlight', '1');
        ov.setAttribute('data-bu-hl-overlay', '1');
        ov.style.cssText = `position:absolute;z-index:99998;pointer-events:none;border:${borderWidth} solid ${borderColor};background:${borderColor}11;border-radius:3px;left:${r.left+window.scrollX-1}px;top:${r.top+window.scrollY-1}px;width:${r.width+2}px;height:${r.height+2}px;`;
        const bd = document.createElement('span');
        bd.setAttribute('data-bu-highlight', '1');
        bd.setAttribute('data-bu-hl-overlay', '1');
        bd.setAttribute('data-bu-badge-num', String(num));
        bd.textContent = (isSel ? '\u2713 ' : '') + `${num}:${ref}`;
        bd.style.cssText = `position:absolute;z-index:99999;cursor:pointer;background:${isSel ? '#f59e0b' : color};color:white;font:bold 10px monospace;padding:1px 4px;border-radius:2px;white-space:nowrap;left:${r.left+window.scrollX}px;top:${Math.max(0,r.top+window.scrollY-16)}px;`;
        bd.onclick = (e) => {
          e.stopPropagation();
          if (sel.has(num)) sel.delete(num); else sel.set(num, { num, ref });
          positionOverlays();
        };
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
  const structural = new Set(['navigation','form','section','article','main','header','footer','details','list','listitem','table','region','dialog']);

  function walk(node, depth, frameDesc) {
    const children = node.children || [];
    for (const child of children) {
      const tag = child.tagName;

      // Handle iframes: try to walk into same-origin contentDocument
      if (tag === 'IFRAME') {
        let iframeDoc;
        try { iframeDoc = child.contentDocument; } catch(e) { /* cross-origin */ }
        const id = child.id ? '#' + child.id : (child.name ? '[name=' + child.name + ']' : '');
        if (iframeDoc && iframeDoc.body) {
          const iframeFrame = 'iframe' + id;
          results.push({ role: 'iframe-boundary', ref: iframeFrame, depth, label: '', num: idx++ });
          walk(iframeDoc.body, depth + 1, iframeFrame);
        } else {
          results.push({ role: 'iframe-boundary', ref: 'iframe' + id, depth, label: '(cross-origin, not accessible)', num: idx++ });
        }
        continue;
      }

      // Walk into Shadow DOM if present
      if (child.shadowRoot) {
        const shadowLabel = tag.toLowerCase() + (child.id ? '#' + child.id : '');
        results.push({ role: 'shadow-root', ref: shadowLabel, depth, label: '', num: idx++ });
        walk(child.shadowRoot, depth + 1, frameDesc);
        // Also continue walking the light DOM children below
      }

      const ariaRole = child.getAttribute ? child.getAttribute('role') : null;
      const isInteresting = INTERESTING.has(tag) || (ariaRole && ARIA_ROLES.has(ariaRole));

      if (!isInteresting) {
        walk(child, depth, frameDesc);
        continue;
      }

      // Skip hidden
      if (child.offsetParent === null && child.type !== 'hidden' && tag !== 'NAV' && tag !== 'HEADER' && tag !== 'FOOTER' && tag !== 'MAIN') {
        continue;
      }
      if (child.type === 'hidden') { continue; }

      const role = getRole(child);
      if (!role) { walk(child, depth, frameDesc); continue; }

      const ref = getRef(child, idx);
      const label = getLabel(child);

      // Skip links/images with no label
      if ((role === 'link' || role === 'image') && !label) {
        walk(child, depth, frameDesc);
        continue;
      }

      const entry = { role, ref, depth };
      if (label) entry.label = label;
      if (frameDesc) entry.frame = frameDesc;

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
      if (structural.has(role)) {
        walk(child, depth + 1, frameDesc);
      }
      // Don't recurse into leaf elements (links, buttons, inputs)
    }
  }

  walk(document.body, 0, null);

  // Highlight system with repositioning + selection
  if (highlight && hlPairs.length > 0) {
    if (!window.__buSelected) window.__buSelected = new Map();
    const sel = window.__buSelected;

    const positionOverlays = () => {
      document.querySelectorAll('[data-bu-hl-overlay]').forEach(e => e.remove());
      hlPairs.forEach(({ el, ref, num, color }) => {
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) return;
        const isSel = sel.has(num);
        const borderColor = isSel ? '#f59e0b' : color;
        const borderWidth = isSel ? '3px' : '2px';
        const ov = document.createElement('div');
        ov.setAttribute('data-bu-highlight', '1');
        ov.setAttribute('data-bu-hl-overlay', '1');
        ov.style.cssText = `position:absolute;z-index:99998;pointer-events:none;border:${borderWidth} solid ${borderColor};background:${borderColor}11;border-radius:3px;left:${r.left+window.scrollX-1}px;top:${r.top+window.scrollY-1}px;width:${r.width+2}px;height:${r.height+2}px;`;
        const bd = document.createElement('span');
        bd.setAttribute('data-bu-highlight', '1');
        bd.setAttribute('data-bu-hl-overlay', '1');
        bd.setAttribute('data-bu-badge-num', String(num));
        bd.textContent = (isSel ? '\u2713 ' : '') + `${num}:${ref}`;
        bd.style.cssText = `position:absolute;z-index:99999;cursor:pointer;background:${isSel ? '#f59e0b' : color};color:white;font:bold 10px monospace;padding:1px 4px;border-radius:2px;white-space:nowrap;left:${r.left+window.scrollX}px;top:${Math.max(0,r.top+window.scrollY-16)}px;`;
        bd.onclick = (e) => {
          e.stopPropagation();
          if (sel.has(num)) sel.delete(num); else sel.set(num, { num, ref });
          positionOverlays();
        };
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

# --- ARIA / CDP helpers ---

# Roles to skip entirely (internal Chrome scaffolding, not useful for agents)
_SKIP_ROLES = {
    "none", "generic", "InlineTextBox", "LineBreak",
}

# Structural roles that act as containers — rendered as tree nesting
_STRUCTURAL_ROLES = {
    "RootWebArea", "navigation", "main", "banner", "contentinfo",
    "complementary", "region", "form", "search", "dialog", "alert",
    "alertdialog", "application", "group", "list", "listitem", "tree",
    "treeitem", "tablist", "tabpanel", "toolbar", "menu", "menubar",
    "grid", "row", "rowgroup", "table", "article", "section", "figure",
    "directory", "feed", "log", "marquee", "status", "timer",
    "math", "note", "document", "cell", "columnheader", "rowheader",
    "definition", "term", "paragraph", "blockquote", "details",
}


def _detect_cdp_port() -> str | None:
    """Detect the Chrome remote-debugging-port from the process list."""
    try:
        ps = subprocess.run(["ps", "aux"], capture_output=True, text=True)
        m = re.search(r"remote-debugging-port=(\d+)", ps.stdout)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


def _cdp_send(ws_url: str, method: str, params: dict | None = None) -> dict:
    """Send a single CDP command over WebSocket and return the result."""
    import websocket  # websocket-client

    ws = websocket.create_connection(ws_url, timeout=10)
    try:
        msg = {"id": 1, "method": method, "params": params or {}}
        ws.send(json.dumps(msg))
        while True:
            resp = json.loads(ws.recv())
            if resp.get("id") == 1:
                if "error" in resp:
                    raise RuntimeError(f"CDP error: {resp['error']}")
                return resp.get("result", {})
    finally:
        ws.close()


def _get_debugger_ws_url(cdp_port: str) -> str:
    """Get the page's WebSocket debugger URL from CDP /json endpoint."""
    url = f"http://localhost:{cdp_port}/json"
    with urllib.request.urlopen(url, timeout=5) as resp:
        targets = json.loads(resp.read())
    # Pick the first 'page' target
    for t in targets:
        if t.get("type") == "page":
            return t["webSocketDebuggerUrl"]
    # Fallback: first target with a WS URL
    for t in targets:
        if "webSocketDebuggerUrl" in t:
            return t["webSocketDebuggerUrl"]
    raise RuntimeError(f"No debuggable page target found on CDP port {cdp_port}")


def _get_page_info_via_cdp(ws_url: str) -> tuple[str, str]:
    """Return (url, title) of the current page via CDP Runtime.evaluate."""
    result = _cdp_send(ws_url, "Runtime.evaluate", {
        "expression": "JSON.stringify({url: location.href, title: document.title})",
        "returnByValue": True,
    })
    val = result.get("result", {}).get("value", "{}")
    info = json.loads(val)
    return info.get("url", ""), info.get("title", "")


def _ax_prop(node: dict, name: str) -> str:
    """Extract a named property value from an AX node's properties list."""
    for p in node.get("properties", []):
        if p.get("name") == name:
            v = p.get("value", {})
            return str(v.get("value", ""))
    return ""


def _format_aria_tree(nodes: list[dict]) -> list[str]:
    """Build a YAML-like tree from Accessibility.getFullAXTree nodes."""
    if not nodes:
        return []

    # Build lookup: nodeId -> node
    by_id = {}
    for n in nodes:
        by_id[n["nodeId"]] = n

    # Build children map from parentId
    children: dict[str, list[str]] = {}
    root_id = None
    for n in nodes:
        nid = n["nodeId"]
        pid = n.get("parentId")
        if pid:
            children.setdefault(pid, []).append(nid)
        else:
            root_id = nid

    if root_id is None and nodes:
        root_id = nodes[0]["nodeId"]

    lines: list[str] = []
    counter = [0]  # mutable counter for numbering interactive elements

    def _node_name(node: dict) -> str:
        nm = node.get("name", {})
        return str(nm.get("value", "")) if isinstance(nm, dict) else str(nm)

    def _node_role(node: dict) -> str:
        role = node.get("role", {})
        return str(role.get("value", "")) if isinstance(role, dict) else str(role)

    def _is_interactive(role: str) -> bool:
        return role in {
            "link", "button", "textbox", "combobox", "checkbox", "radio",
            "menuitem", "menuitemcheckbox", "menuitemradio", "tab",
            "switch", "slider", "spinbutton", "searchbox", "option",
            "treeitem",
        }

    def walk(nid: str, depth: int) -> None:
        node = by_id.get(nid)
        if node is None:
            return

        role = _node_role(node)
        name = _node_name(node)
        ignored = node.get("ignored", False)

        # Skip ignored nodes but still walk children
        if ignored or role in _SKIP_ROLES:
            for cid in children.get(nid, []):
                walk(cid, depth)
            return

        indent = "  " * (depth + 1)
        interactive = _is_interactive(role)

        # Build the display line
        parts = [f"{indent}- {role}"]
        if name:
            display_name = name[:77] + "..." if len(name) > 80 else name
            parts.append(f' "{display_name}"')

        # Number interactive elements for ref compatibility
        if interactive:
            num = counter[0]
            counter[0] += 1
            parts.append(f" #{num}")

        # Extra properties: value
        value = _ax_prop(node, "value")
        if not value:
            v = node.get("value")
            if isinstance(v, dict):
                value = str(v.get("value", ""))
        if value:
            display_val = value[:57] + "..." if len(value) > 60 else value
            parts.append(f' [value="{display_val}"]')

        checked = _ax_prop(node, "checked")
        if checked == "true":
            parts.append(" [checked]")
        elif checked == "mixed":
            parts.append(" [mixed]")

        disabled = _ax_prop(node, "disabled")
        if disabled == "true":
            parts.append(" [disabled]")

        required = _ax_prop(node, "required")
        if required == "true":
            parts.append(" [required]")

        expanded = _ax_prop(node, "expanded")
        if expanded == "true":
            parts.append(" [expanded]")
        elif expanded == "false":
            parts.append(" [collapsed]")

        selected = _ax_prop(node, "selected")
        if selected == "true":
            parts.append(" [selected]")

        level = _ax_prop(node, "level")
        if level and role == "heading":
            parts.append(f" [h{level}]")

        focused = _ax_prop(node, "focused")
        if focused == "true":
            parts.append(" [focused]")

        line = "".join(parts)
        lines.append(line)

        # Recurse into children
        for cid in children.get(nid, []):
            walk(cid, depth + 1 if role in _STRUCTURAL_ROLES else depth)

    walk(root_id, 0)
    return lines


def run_aria_snapshot(cdp_port: str) -> None:
    """Fetch the accessibility tree via CDP and save as YAML snapshot."""
    ws_url = _get_debugger_ws_url(cdp_port)

    # Get page URL and title
    page_url, page_title = _get_page_info_via_cdp(ws_url)

    # Fetch the full accessibility tree
    result = _cdp_send(ws_url, "Accessibility.getFullAXTree")
    ax_nodes = result.get("nodes", [])

    tree_lines = _format_aria_tree(ax_nodes)

    # Build output
    lines = []
    lines.append(f"# url: {page_url}")
    lines.append(f"# cdp: localhost:{cdp_port}")
    lines.append(f"# title: {page_title}")
    lines.append("# mode: aria (CDP Accessibility.getFullAXTree)")
    lines.append("")
    lines.extend(tree_lines)

    content = "\n".join(lines) + "\n"

    # Save to file
    SNAPSHOT_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%f")[:-3] + "Z"
    filename = f"page-{ts}.yml"
    filepath = SNAPSHOT_DIR / filename
    filepath.write_text(content)

    print(f"[Snapshot]({filepath.relative_to(Path.cwd()) if filepath.is_relative_to(Path.cwd()) else filepath})")


def format_element(el: dict) -> str:
    """Format one element as a YAML-like line."""
    role = el["role"]
    ref = el["ref"]
    label = el.get("label", "")
    depth = el.get("depth", 0)
    indent = "  " * (depth + 1)

    # Special boundary markers for iframes and shadow DOM
    if role == "iframe-boundary":
        if label:
            # Cross-origin iframe
            return f"{indent}- # iframe {ref} {label}"
        return f"{indent}- [iframe: {ref}]"
    if role == "shadow-root":
        return f"{indent}- [shadow-root: {ref}]"

    num = el.get("num", "")
    parts = [f'{indent}- {role}']
    if label:
        # Truncate very long labels
        if len(label) > 80:
            label = label[:77] + "..."
        parts.append(f' "{label}"')
    parts.append(f' #{num}' if num != "" else '')
    parts.append(f' [{ref}]')

    if el.get("frame"):
        parts.append(f' [frame={el["frame"]}]')
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
    aria_mode = False
    cdp_port_override = None
    extra_args = []
    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--forms", "-f"):
            forms_only = True
        elif arg in ("--highlight", "-h"):
            highlight = True
        elif arg in ("--tree", "-t"):
            tree_mode = True
        elif arg in ("--aria", "-a"):
            aria_mode = True
        elif arg == "--cdp-port" and i + 1 < len(argv):
            i += 1
            cdp_port_override = argv[i]
        elif arg.startswith("--cdp-port="):
            cdp_port_override = arg.split("=", 1)[1]
        else:
            extra_args.append(arg)
        i += 1

    # ARIA mode: use CDP Accessibility.getFullAXTree instead of DOM walking
    if aria_mode:
        port = cdp_port_override or _detect_cdp_port()
        if not port:
            print("ERROR: Could not detect CDP port. Is Chrome running with "
                  "--remote-debugging-port? Use --cdp-port=PORT to specify.",
                  file=sys.stderr)
            sys.exit(1)
        run_aria_snapshot(port)
        return

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
