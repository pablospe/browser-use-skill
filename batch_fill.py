#!/usr/bin/env python3
"""Batch fill form fields in one JS eval via JSON map of name->value.

Usage:
  bu fill '{"your-surname":"Schmidt","your-firstname":"Anna","your-salutation":{"select":"Mrs."},"acceptance-543":{"check":true}}'

Keys are element name attributes (stable refs from snapshot).
Values are:
  - string or number: set input/textarea/range value
  - {"select": "option"}: select a dropdown option by visible text, or radio by value
  - {"check": true/false}: set checkbox/radio checked state
  - {"check": true, "index": N}: target the Nth element with the same name (0-based)
"""

import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent

FILL_JS = r"""
((fields) => {
  let filled = 0;
  const errors = [];

  // Find element by name or id, searching main document, same-origin iframes, and shadow DOM
  // Optional idx parameter selects the Nth element with that name (0-based)
  const findEl = (name, idx) => {
    // Escape name for CSS attribute value selectors (handle " and \ chars)
    const cssVal = name.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
    // Search a root (document or shadowRoot) and its shadow children
    const searchRoot = (root) => {
      if (typeof idx === 'number') {
        // Return all matches so caller can pick by index
        const els = root.querySelectorAll(`[name="${cssVal}"]`);
        if (els.length > idx) return els[idx];
        const byId = root.querySelectorAll(`#${CSS.escape(name)}`);
        if (byId.length > idx) return byId[idx];
      } else {
        const el = root.querySelector(`[name="${cssVal}"]`) || root.querySelector(`#${CSS.escape(name)}`);
        if (el) return el;
      }
      // Check shadow DOMs
      const allEls = root.querySelectorAll('*');
      for (const candidate of allEls) {
        if (candidate.shadowRoot) {
          const found = searchRoot(candidate.shadowRoot);
          if (found) return found;
        }
      }
      return null;
    };
    // Main document
    let el = searchRoot(document);
    if (el) return el;
    // Same-origin iframes
    const iframes = document.querySelectorAll('iframe');
    for (const iframe of iframes) {
      let iframeDoc;
      try { iframeDoc = iframe.contentDocument; } catch(e) { continue; }
      if (!iframeDoc) continue;
      el = searchRoot(iframeDoc);
      if (el) return el;
    }
    return null;
  };

  for (const [name, action] of Object.entries(fields)) {
    // Support "index" property for same-name elements (e.g. {"check":true,"index":1})
    const elIdx = (typeof action === 'object' && action !== null) ? action.index : undefined;
    const el = findEl(name, elIdx);
    if (!el) { errors.push(name + ': not found'); continue; }
    // Escape name for CSS attribute value selectors (used by radio group query)
    const cssVal = name.replace(/\\/g, '\\\\').replace(/"/g, '\\"');

    try {
      if (typeof action === 'string' || typeof action === 'number') {
        // Text/number/range input or textarea — use matching prototype setter for React compat
        const val = String(action);
        const proto = el.tagName === 'TEXTAREA'
          ? window.HTMLTextAreaElement.prototype
          : window.HTMLInputElement.prototype;
        const nativeSet = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
        if (nativeSet) nativeSet.call(el, val);
        else el.value = val;
        el.dispatchEvent(new Event('input', {bubbles: true}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
        filled++;
      } else if (action.select !== undefined) {
        // Select dropdown by visible text, or radio group by value
        if (el.tagName === 'SELECT') {
          const opts = Array.from(el.options);
          const opt = opts.find(o => o.text === action.select || o.value === action.select);
          if (opt) {
            el.value = opt.value;
            el.dispatchEvent(new Event('change', {bubbles: true}));
            filled++;
          } else {
            errors.push(name + ': option "' + action.select + '" not found');
          }
        } else if (el.type === 'radio') {
          // Find radio button in the same group with matching value or label text
          const radios = document.querySelectorAll('input[type="radio"][name="' + cssVal + '"]');
          let found = false;
          const target = action.select;
          radios.forEach(r => {
            if (found) return;
            // Match by value first
            if (r.value === target) {
              r.checked = true;
              r.dispatchEvent(new Event('change', {bubbles: true}));
              found = true;
              return;
            }
            // Match by associated label text
            const labelEl = r.id ? document.querySelector('label[for="' + r.id + '"]') : null;
            const parentLabel = r.closest('label');
            const labelText = (labelEl?.textContent || parentLabel?.textContent || '').trim();
            if (labelText === target || labelText.startsWith(target)) {
              r.checked = true;
              r.dispatchEvent(new Event('change', {bubbles: true}));
              found = true;
            }
          });
          if (found) filled++;
          else errors.push(name + ': radio value "' + action.select + '" not found');
        } else {
          errors.push(name + ': select not supported on ' + el.tagName + '[type=' + el.type + ']');
        }
      } else if (action.check !== undefined) {
        el.checked = !!action.check;
        el.dispatchEvent(new Event('change', {bubbles: true}));
        filled++;
      } else {
        errors.push(name + ': unknown action');
      }
    } catch (e) {
      errors.push(name + ': ' + e.message);
    }
  }
  return JSON.stringify({filled, total: Object.keys(fields).length, errors});
})(%FIELDS%)
"""


def main():
    extra_args = []
    json_str = None
    for arg in sys.argv[1:]:
        if arg.startswith("-"):
            extra_args.append(arg)
        elif json_str is None:
            json_str = arg

    if not json_str:
        print('Usage: bu fill \'{"your-surname":"text","your-salutation":{"select":"Mr."}}\'', file=sys.stderr)
        sys.exit(1)

    try:
        fields = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(fields, dict):
        print('Error: fill expects a JSON object, e.g. \'{"field":"value"}\'', file=sys.stderr)
        print(f'Got: {type(fields).__name__} ({json_str[:50]})', file=sys.stderr)
        sys.exit(1)

    # Inject fields into JS and run single eval
    js = FILL_JS.replace("%FIELDS%", json.dumps(fields))
    cmd = ["uv", "run", "--directory", str(SKILL_DIR), "browser-use", "--json"] + extra_args + ["eval", js]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)

    data = json.loads(result.stdout)
    result_str = data.get("data", {}).get("result", "")
    if result_str:
        out = json.loads(result_str)
        print(f"filled: {out['filled']}/{out['total']}")
        if out.get("errors"):
            for err in out["errors"]:
                print(f"  error: {err}", file=sys.stderr)
            sys.exit(1)
    else:
        print("No result from eval", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
