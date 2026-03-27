#!/usr/bin/env python3
"""AI cursor: visible animated cursor that moves to elements before acting.

Injects a red glowing dot into the page that smoothly animates to target
elements. Shows a click ripple on click actions. Persists across calls.
"""

import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

SKILL_DIR = Path(__file__).parent

# JS: inject cursor element + helpers (idempotent — safe to call repeatedly)
CURSOR_INIT_JS = r"""
if (!window.__buCursor || !window.__buCursor.moveToEl) {
  // Remove old cursor if upgrading
  if (window.__buCursor) {
    var old = document.getElementById('__bu-cursor-dot');
    if (old) old.remove();
    old = document.getElementById('__bu-cursor-trail');
    if (old) old.remove();
    window.__buCursor = null;
  }
  // Cursor dot
  const dot = document.createElement('div');
  dot.id = '__bu-cursor-dot';
  dot.style.cssText = `
    position:fixed; z-index:100010; pointer-events:none;
    width:20px; height:20px; border-radius:50%;
    background:radial-gradient(circle, #ff4444 0%, #ff4444 40%, rgba(255,68,68,0.4) 70%, transparent 100%);
    box-shadow:0 0 15px 3px rgba(255,68,68,0.5);
    transform:translate(-50%,-50%);
    transition:opacity 0.2s;
    left:-50px; top:-50px; opacity:0;
  `;
  document.body.appendChild(dot);

  // Trail (smaller, follows with delay)
  const trail = document.createElement('div');
  trail.id = '__bu-cursor-trail';
  trail.style.cssText = `
    position:fixed; z-index:100009; pointer-events:none;
    width:10px; height:10px; border-radius:50%;
    background:rgba(255,68,68,0.3);
    transform:translate(-50%,-50%);
    transition:opacity 0.2s;
    left:-50px; top:-50px; opacity:0;
  `;
  document.body.appendChild(trail);

  let scrollTimer;
  const onScroll = () => {
    clearTimeout(scrollTimer);
    scrollTimer = setTimeout(() => {
      const c = window.__buCursor;
      if (!c._targetEl || dot.style.opacity === '0') return;
      const r = c._targetEl.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) return;
      const cx = r.left + r.width/2;
      const cy = r.top + r.height/2;
      dot.style.left = cx + 'px';
      dot.style.top = cy + 'px';
      trail.style.left = cx + 'px';
      trail.style.top = cy + 'px';
    }, 50);
  };
  window.addEventListener('scroll', onScroll, true);

  window.__buCursor = {
    dot: dot,
    trail: trail,
    _targetEl: null,

    moveToEl: function(el) {
      this._targetEl = el;
      const r = el.getBoundingClientRect();
      const cx = r.left + r.width/2;
      const cy = r.top + r.height/2;
      return this.moveTo(cx, cy);
    },

    moveTo: function(x, y) {
      return new Promise(resolve => {
        dot.style.opacity = '1';
        trail.style.opacity = '1';
        dot.style.left = x + 'px';
        dot.style.top = y + 'px';
        // Trail follows slightly behind
        setTimeout(() => {
          trail.style.left = x + 'px';
          trail.style.top = y + 'px';
        }, 50);
        // Wait for animation to complete
        setTimeout(resolve, 450);
      });
    },

    ripple: function(x, y) {
      const r = document.createElement('div');
      r.style.cssText = `
        position:fixed; z-index:100008; pointer-events:none;
        left:${x}px; top:${y}px;
        width:0; height:0; border-radius:50%;
        transform:translate(-50%,-50%);
        border:2px solid rgba(255,68,68,0.8);
        background:rgba(255,68,68,0.15);
        transition:width 0.4s ease-out, height 0.4s ease-out, opacity 0.4s ease-out;
        opacity:1;
      `;
      document.body.appendChild(r);
      requestAnimationFrame(() => {
        r.style.width = '40px';
        r.style.height = '40px';
        r.style.opacity = '0';
      });
      setTimeout(() => r.remove(), 500);
    },

    hide: function() {
      dot.style.opacity = '0';
      trail.style.opacity = '0';
    }
  };
}
"""

# JS: find element by ref (same logic as bu.sh _find_by_ref)
FIND_BY_REF_JS = r"""
function __buFindRef(ref) {
  var e = document.querySelector('[name="' + ref + '"]') || document.getElementById(ref);
  if (!e) {
    var as = document.querySelectorAll('a[href]');
    for (var i = 0; i < as.length; i++) {
      try {
        var u = new URL(as[i].href);
        var p = u.pathname.replace(/\/+$/, '').split('/').pop();
        if (p === ref) { e = as[i]; break; }
      } catch(x) {}
    }
  }
  return e;
}
"""

ACTION_TEMPLATES = {
    "click": r"""
(function() {
  %CURSOR_INIT%
  %FIND_BY_REF%

  var el = __buFindRef('%REF%');
  if (!el) return JSON.stringify({error: 'no element found for ref=%REF%'});

  el.scrollIntoView({block:'center'});

  var r = el.getBoundingClientRect();
  var cx = r.left + r.width/2;
  var cy = r.top + r.height/2;

  // Animate cursor to target (tracks element for scroll repositioning)
  window.__buCursor.moveToEl(el);

  // Click after brief delay (JS fallback)
  setTimeout(function() {
    window.__buCursor.ripple(cx, cy);
    el.focus();
    el.click();
    el.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, clientX:cx, clientY:cy}));
  }, 100);

  return JSON.stringify({ok: true, tag: el.tagName.toLowerCase(), ref: '%REF%', x: cx, y: cy});
})()
""",
    "hover": r"""
(function() {
  %CURSOR_INIT%
  %FIND_BY_REF%

  var el = __buFindRef('%REF%');
  if (!el) return JSON.stringify({error: 'no element found for ref=%REF%'});

  el.scrollIntoView({block:'center'});

  var r = el.getBoundingClientRect();
  var cx = r.left + r.width/2;
  var cy = r.top + r.height/2;

  window.__buCursor.moveToEl(el);

  // Also dispatch JS events as fallback
  setTimeout(function() {
    var r2 = el.getBoundingClientRect();
    el.dispatchEvent(new MouseEvent('mouseover', {bubbles:true, clientX:r2.left+r2.width/2, clientY:r2.top+r2.height/2}));
    el.dispatchEvent(new MouseEvent('mouseenter', {bubbles:true, clientX:r2.left+r2.width/2, clientY:r2.top+r2.height/2}));
  }, 100);

  return JSON.stringify({ok: true, tag: el.tagName.toLowerCase(), ref: '%REF%', x: cx, y: cy});
})()
""",
    "scroll": r"""
(function() {
  %CURSOR_INIT%
  %FIND_BY_REF%

  var el = __buFindRef('%REF%');
  if (!el) return 'ERROR: no element found for ref=%REF%';

  el.scrollIntoView({behavior:'smooth', block:'center'});

  // Cursor follows after scroll settles (tracks element for scroll repositioning)
  setTimeout(function() {
    window.__buCursor.moveToEl(el);
  }, 300);

  return 'scrolled to: ' + el.tagName.toLowerCase() + '[ref=%REF%]';
})()
""",
    "fill": r"""
(function() {
  %CURSOR_INIT%

  var fields = %FIELDS_JSON%;
  var entries = Object.entries(fields);
  var filled = 0;
  var errors = [];

  // Animate through fields sequentially with delays
  function fillNext(i) {
    if (i >= entries.length) return;
    var name = entries[i][0];
    var value = entries[i][1];
    var el = document.querySelector('[name="' + name + '"]');
    if (!el) { errors.push(name + ': not found'); fillNext(i+1); return; }

    el.scrollIntoView({block:'center'});

    setTimeout(function() {
      window.__buCursor.moveToEl(el);

      setTimeout(function() {
        var r2 = el.getBoundingClientRect();
        window.__buCursor.ripple(r2.left+r2.width/2, r2.top+r2.height/2);

        if (typeof value === 'object' && value.select) {
          var opts = el.options;
          for (var j = 0; j < opts.length; j++) {
            if (opts[j].text === value.select || opts[j].value === value.select) {
              el.selectedIndex = j; break;
            }
          }
          el.dispatchEvent(new Event('change', {bubbles:true}));
        } else if (typeof value === 'object' && 'check' in value) {
          el.checked = !!value.check;
          el.dispatchEvent(new Event('change', {bubbles:true}));
        } else {
          el.focus();
          var setter = el.tagName === 'TEXTAREA'
            ? Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set
            : Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
          setter.call(el, value);
          el.dispatchEvent(new Event('input', {bubbles:true}));
          el.dispatchEvent(new Event('change', {bubbles:true}));
        }
        filled++;
        fillNext(i+1);
      }, 500);
    }, 150);
  }

  fillNext(0);
  return 'filling: ' + entries.length + ' fields (animated)';
})()
""",
    "show": r"""
(function() {
  %CURSOR_INIT%
  window.__buCursor.dot.style.opacity = '1';
  window.__buCursor.trail.style.opacity = '1';
  return 'cursor: visible';
})()
""",
    "hide": r"""
(function() {
  if (window.__buCursor) {
    window.__buCursor.hide();
  }
  return 'cursor: hidden';
})()
""",
}


def _detect_cdp_port() -> str | None:
    """Detect the Chrome remote-debugging-port from process list or /proc."""
    # Try ps first
    try:
        ps = subprocess.run(["ps", "aux"], capture_output=True, text=True)
        m = re.search(r"remote-debugging-port=(\d+)", ps.stdout)
        if m:
            return m.group(1)
    except Exception:
        pass
    # Fallback: scan /proc cmdlines (works in minimal containers without ps)
    try:
        from pathlib import Path
        for cmdline in Path("/proc").glob("*/cmdline"):
            try:
                data = cmdline.read_bytes().replace(b"\x00", b" ").decode("utf-8", errors="ignore")
                m = re.search(r"remote-debugging-port=(\d+)", data)
                if m:
                    return m.group(1)
            except (OSError, PermissionError):
                continue
    except Exception:
        pass
    return None


def _get_debugger_ws_url(cdp_port: str) -> str:
    """Get the page's WebSocket debugger URL from CDP /json endpoint."""
    url = f"http://localhost:{cdp_port}/json"
    with urllib.request.urlopen(url, timeout=5) as resp:
        targets = json.loads(resp.read())
    for t in targets:
        if t.get("type") == "page":
            return t["webSocketDebuggerUrl"]
    for t in targets:
        if "webSocketDebuggerUrl" in t:
            return t["webSocketDebuggerUrl"]
    raise RuntimeError(f"No debuggable page target found on CDP port {cdp_port}")


def _cdp_send(ws_url: str, method: str, params: dict | None = None) -> dict:
    """Send a single CDP command over WebSocket and return the result."""
    import websocket  # websocket-client

    ws = websocket.create_connection(ws_url, timeout=10, suppress_origin=True)
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


def _cdp_mouse(x: float, y: float, click: bool = False) -> bool:
    """Move the real browser cursor to (x, y) via CDP. Optionally click."""
    cdp_port = _detect_cdp_port()
    if not cdp_port:
        return False
    try:
        ws_url = _get_debugger_ws_url(cdp_port)
        # Move cursor (triggers JS mouseover/mouseenter + some CSS :hover)
        _cdp_send(ws_url, "Input.dispatchMouseEvent", {
            "type": "mouseMoved",
            "x": int(x),
            "y": int(y),
        })
        if click:
            _cdp_send(ws_url, "Input.dispatchMouseEvent", {
                "type": "mousePressed",
                "x": int(x),
                "y": int(y),
                "button": "left",
                "clickCount": 1,
            })
            _cdp_send(ws_url, "Input.dispatchMouseEvent", {
                "type": "mouseReleased",
                "x": int(x),
                "y": int(y),
                "button": "left",
                "clickCount": 1,
            })
        return True
    except Exception as e:
        print(f"CDP mouse fallback: {e}", file=sys.stderr)
        return False


def _cdp_force_hover(ref: str) -> bool:
    """Force CSS :hover on an element via CDP CSS.forcePseudoState.

    Uses DOM.performSearch to find the element by name/id/ref, then
    forces the :hover pseudo-class. This reliably triggers CSS :hover
    rules (dropdown menus, tooltips, etc.).
    """
    cdp_port = _detect_cdp_port()
    if not cdp_port:
        return False
    try:
        import websocket  # websocket-client

        ws_url = _get_debugger_ws_url(cdp_port)
        ws = websocket.create_connection(ws_url, timeout=10, suppress_origin=True)
        msg_id = [0]

        def cdp(method, params=None):
            msg_id[0] += 1
            ws.send(json.dumps({"id": msg_id[0], "method": method, "params": params or {}}))
            while True:
                resp = json.loads(ws.recv())
                if resp.get("id") == msg_id[0]:
                    if "error" in resp:
                        raise RuntimeError(f"CDP error: {resp['error']}")
                    return resp.get("result", {})

        try:
            cdp("DOM.enable")
            cdp("CSS.enable")

            # Find the element's node ID — try name attr, then id, then text search
            selectors = [
                f'[name="{ref}"]',
                f'#{ref}',
                f'a[href*="{ref}"]',
            ]
            node_id = None
            for sel in selectors:
                search = cdp("DOM.performSearch", {"query": sel})
                if search.get("resultCount", 0) > 0:
                    results = cdp("DOM.getSearchResults", {
                        "searchId": search["searchId"],
                        "fromIndex": 0,
                        "toIndex": 1,
                    })
                    if results.get("nodeIds"):
                        node_id = results["nodeIds"][0]
                        break

            if not node_id:
                return False

            # Walk up to find nearest hoverable parent (often the hover target
            # is a parent <li> or <div>, not the link itself)
            # Force :hover on the element AND its parent (covers both patterns)
            cdp("CSS.forcePseudoState", {
                "nodeId": node_id,
                "forcedPseudoClasses": ["hover"],
            })

            # Also force :hover on the parent node
            try:
                node_info = cdp("DOM.describeNode", {"nodeId": node_id})
                parent_id = node_info.get("node", {}).get("parentId")
                if parent_id:
                    cdp("CSS.forcePseudoState", {
                        "nodeId": parent_id,
                        "forcedPseudoClasses": ["hover"],
                    })
            except Exception:
                pass  # Parent hover is best-effort

            return True
        finally:
            ws.close()
    except Exception as e:
        print(f"CDP forcePseudoState fallback: {e}", file=sys.stderr)
        return False


def resolve_ref(ref: str) -> str:
    """If ref is a number, look up the actual ref name from the latest snapshot."""
    if not ref.lstrip("#").isdigit():
        return ref
    num = int(ref.lstrip("#"))
    # Find the latest snapshot
    snapshot_dir = SKILL_DIR / ".browser-use"
    if not snapshot_dir.exists():
        return ref
    files = sorted(snapshot_dir.glob("page-*.yml"))
    if not files:
        return ref
    import re as _re
    for line in files[-1].read_text().splitlines():
        m = _re.search(r'#(\d+)\s+\[([^\]]+)\]', line)
        if m and int(m.group(1)) == num:
            return m.group(2)
    print(f"Warning: #{num} not found in latest snapshot, using as-is", file=sys.stderr)
    return ref


def main():
    if len(sys.argv) < 2:
        print("Usage: cursor_action.py <action> [ref] [extra_args...]", file=sys.stderr)
        print("  actions: click, hover, scroll, fill, show, hide", file=sys.stderr)
        sys.exit(1)

    action = sys.argv[1]
    extra_args = []

    if action in ("click", "hover", "scroll"):
        if len(sys.argv) < 3:
            print(f"Usage: cursor_action.py {action} <ref>", file=sys.stderr)
            sys.exit(1)
        ref = resolve_ref(sys.argv[2])
        extra_args = sys.argv[3:]
        js = ACTION_TEMPLATES[action]
        js = js.replace("%CURSOR_INIT%", CURSOR_INIT_JS)
        js = js.replace("%FIND_BY_REF%", FIND_BY_REF_JS)
        js = js.replace("%REF%", ref)

    elif action == "fill":
        if len(sys.argv) < 3:
            print("Usage: cursor_action.py fill '<json>'", file=sys.stderr)
            sys.exit(1)
        fields_json = sys.argv[2]
        extra_args = sys.argv[3:]
        # Validate JSON
        try:
            json.loads(fields_json)
        except json.JSONDecodeError as e:
            print(f"Invalid JSON: {e}", file=sys.stderr)
            sys.exit(1)
        js = ACTION_TEMPLATES["fill"]
        js = js.replace("%CURSOR_INIT%", CURSOR_INIT_JS)
        js = js.replace("%FIELDS_JSON%", fields_json)

    elif action in ("show", "hide"):
        extra_args = sys.argv[2:]
        js = ACTION_TEMPLATES[action]
        js = js.replace("%CURSOR_INIT%", CURSOR_INIT_JS)

    else:
        print(f"Unknown action: {action}", file=sys.stderr)
        sys.exit(1)

    cmd = ["uv", "run", "--directory", str(SKILL_DIR), "browser-use", "--json"] + extra_args + ["eval", js]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)

    try:
        data = json.loads(result.stdout)
        output = data.get("data", {}).get("result", "")
    except (json.JSONDecodeError, KeyError):
        output = result.stdout

    # For hover/click: dispatch real CDP mouse events
    if action in ("hover", "click") and output:
        try:
            act_data = json.loads(output)
            if act_data.get("ok") and "x" in act_data and "y" in act_data:
                is_click = action == "click"
                used_cdp = _cdp_mouse(act_data["x"], act_data["y"], click=is_click)
                # For hover: also force CSS :hover via CDP (reliable for dropdown menus)
                if action == "hover":
                    ref_used = act_data.get("ref", "")
                    _cdp_force_hover(ref_used)
                method = "CDP" if used_cdp else "JS-only"
                verb = "clicked" if is_click else "hovered"
                print(f"{verb} ({method}): {act_data['tag']}[ref={act_data['ref']}]")
            elif act_data.get("error"):
                print(f"ERROR: {act_data['error']}")
            else:
                print(output)
        except (json.JSONDecodeError, KeyError):
            print(output)
    else:
        print(output)


if __name__ == "__main__":
    main()
