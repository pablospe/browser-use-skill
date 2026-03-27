#!/usr/bin/env python3
"""AI cursor: visible animated cursor that moves to elements before acting.

Injects a red glowing dot into the page that smoothly animates to target
elements. Shows a click ripple on click actions. Persists across calls.
"""

import json
import subprocess
import sys
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
  if (!el) return 'ERROR: no element found for ref=%REF%';

  el.scrollIntoView({block:'center'});

  var r = el.getBoundingClientRect();
  var cx = r.left + r.width/2;
  var cy = r.top + r.height/2;

  // Animate cursor to target (tracks element for scroll repositioning)
  window.__buCursor.moveToEl(el);

  // Click after animation delay
  setTimeout(function() {
    window.__buCursor.ripple(cx, cy);
    el.focus();
    el.click();
    el.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, clientX:cx, clientY:cy}));
  }, 450);

  return 'clicked: ' + el.tagName.toLowerCase() + '[ref=%REF%]';
})()
""",
    "hover": r"""
(function() {
  %CURSOR_INIT%
  %FIND_BY_REF%

  var el = __buFindRef('%REF%');
  if (!el) return 'ERROR: no element found for ref=%REF%';

  el.scrollIntoView({block:'center'});

  var r = el.getBoundingClientRect();
  var cx = r.left + r.width/2;
  var cy = r.top + r.height/2;

  window.__buCursor.moveToEl(el);

  setTimeout(function() {
    var r2 = el.getBoundingClientRect();
    el.dispatchEvent(new MouseEvent('mouseover', {bubbles:true, clientX:r2.left+r2.width/2, clientY:r2.top+r2.height/2}));
    el.dispatchEvent(new MouseEvent('mouseenter', {bubbles:true, clientX:r2.left+r2.width/2, clientY:r2.top+r2.height/2}));
  }, 450);

  return 'hovered: ' + el.tagName.toLowerCase() + '[ref=%REF%]';
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
        print(output)
    except (json.JSONDecodeError, KeyError):
        print(result.stdout)


if __name__ == "__main__":
    main()
