#!/usr/bin/env bash
# Integration tests for browser-use skill against a local test form.
# Usage: ./tests/run-tests.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
BU="bash $SKILL_DIR/bu.sh"
PORT=18973
PASS=0
FAIL=0
ERRORS=""

# --- helpers ---
start_server() {
  cd "$SCRIPT_DIR"
  python3 -m http.server $PORT --bind 127.0.0.1 &>/dev/null &
  SERVER_PID=$!
  sleep 0.5
  cd - &>/dev/null
}

stop_server() {
  kill $SERVER_PID 2>/dev/null || true
  wait $SERVER_PID 2>/dev/null || true
}

cleanup() {
  $BU close &>/dev/null || true
  stop_server
  echo ""
  echo "=========================="
  echo "Results: $PASS passed, $FAIL failed (${TOTAL_MS}ms total)"
  if [ -n "$ERRORS" ]; then
    echo ""
    echo "Failures:"
    echo "$ERRORS"
  fi
  echo "=========================="
  [ "$FAIL" -eq 0 ]
}
trap cleanup EXIT

assert_eq() {
  local name="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    echo "  PASS: $name"
    PASS=$((PASS + 1))
  else
    echo "  FAIL: $name"
    echo "    expected: $expected"
    echo "    actual:   $actual"
    FAIL=$((FAIL + 1))
    ERRORS="$ERRORS\n  - $name: expected '$expected', got '$actual'"
  fi
}

assert_contains() {
  local name="$1" expected="$2" actual="$3"
  if echo "$actual" | grep -qF "$expected"; then
    echo "  PASS: $name"
    PASS=$((PASS + 1))
  else
    echo "  FAIL: $name"
    echo "    expected to contain: $expected"
    echo "    actual: $actual"
    FAIL=$((FAIL + 1))
    ERRORS="$ERRORS\n  - $name: expected to contain '$expected'"
  fi
}

eval_js() {
  $BU eval "$1" 2>/dev/null | grep -oP 'result: \K.*'
}

# Time a bu command and print duration
TOTAL_MS=0
t0() { T_START=$(date +%s%N); }
t1() {
  local ms=$(( ($(date +%s%N) - T_START) / 1000000 ))
  TOTAL_MS=$((TOTAL_MS + ms))
  echo "  [${ms}ms] $1"
}

# --- setup ---
echo "Starting local server on port $PORT..."
start_server

echo "Opening browser..."
t0; $BU open "http://127.0.0.1:$PORT/test-form.html" &>/dev/null; t1 "open"
sleep 1

# --- Test 1: Snapshot captures all field types ---
echo ""
echo "=== Test: Snapshot ==="
t0; SNAP=$($BU snapshot --forms 2>/dev/null); t1 "snapshot --forms"
SNAP_FILE=$(echo "$SNAP" | grep -oP '\(.*?\)' | tr -d '()')
SNAP_CONTENT=$(cat "$SNAP_FILE")

assert_contains "snapshot has textbox" "textbox" "$SNAP_CONTENT"
assert_contains "snapshot has radio" "radio" "$SNAP_CONTENT"
assert_contains "snapshot has checkbox" "checkbox" "$SNAP_CONTENT"
assert_contains "snapshot has combobox" "combobox" "$SNAP_CONTENT"
assert_contains "snapshot has slider" "slider" "$SNAP_CONTENT"
assert_contains "snapshot has date-input" "date-input" "$SNAP_CONTENT"
assert_contains "snapshot has time-input" "time-input" "$SNAP_CONTENT"
assert_contains "snapshot has color-input" "color-input" "$SNAP_CONTENT"
assert_contains "snapshot has range metadata" "range=0..20" "$SNAP_CONTENT"
assert_contains "snapshot has bracket names" "skills[]" "$SNAP_CONTENT"
assert_contains "snapshot has dotted names" "customer.address.street" "$SNAP_CONTENT"

# --- Test 2: Fill text inputs ---
echo ""
echo "=== Test: Fill text inputs ==="
t0; RESULT=$($BU fill '{"firstName":"Alice","lastName":"Smith","email":"alice@test.com","password":"secret123"}' 2>/dev/null); t1 "fill 4 text fields"
assert_contains "fill text fields" "filled: 4/4" "$RESULT"
t0; VAL=$(eval_js "document.querySelector('[name=firstName]').value"); t1 "eval (verify)"
assert_eq "firstName value" "Alice" "$VAL"

# --- Test 3: Fill dotted names ---
echo ""
echo "=== Test: Fill dotted names ==="
t0; RESULT=$($BU fill '{"customer.address.street":"742 Oak Ave","customer.address.city":"Portland"}' 2>/dev/null); t1 "fill 2 dotted names"
assert_contains "fill dotted names" "filled: 2/2" "$RESULT"
t0; VAL=$(eval_js "document.querySelector('[name=\"customer.address.city\"]').value"); t1 "eval (verify)"
assert_eq "dotted name value" "Portland" "$VAL"

# --- Test 4: Radio select by label text ---
echo ""
echo "=== Test: Radio select by label ==="
t0; RESULT=$($BU fill '{"employment":{"select":"Freelancer"}}' 2>/dev/null); t1 "fill radio by label"
assert_contains "radio select by label" "filled: 1/1" "$RESULT"
t0; VAL=$(eval_js "document.querySelector('[name=employment]:checked')?.value"); t1 "eval (verify)"
assert_eq "radio selected opt3" "opt3" "$VAL"

# --- Test 5: Radio select by value ---
echo ""
echo "=== Test: Radio select by value ==="
t0; RESULT=$($BU fill '{"employment":{"select":"opt1"}}' 2>/dev/null); t1 "fill radio by value"
assert_contains "radio select by value" "filled: 1/1" "$RESULT"
t0; VAL=$(eval_js "document.querySelector('[name=employment]:checked')?.value"); t1 "eval (verify)"
assert_eq "radio selected opt1" "opt1" "$VAL"

# --- Test 6: Checkbox with [] names + index ---
echo ""
echo "=== Test: Checkbox with bracket names ==="
t0; RESULT=$($BU fill '{"skills[]":{"check":true,"index":0}}' 2>/dev/null); t1 "fill checkbox[0]"
assert_contains "check skills[0]" "filled: 1/1" "$RESULT"
t0; VAL=$(eval_js "document.querySelectorAll('[name=\"skills[]\"]')[0].checked"); t1 "eval (verify)"
assert_eq "skills[0] checked" "True" "$VAL"

t0; RESULT=$($BU fill '{"skills[]":{"check":true,"index":2}}' 2>/dev/null); t1 "fill checkbox[2]"
assert_contains "check skills[2]" "filled: 1/1" "$RESULT"
t0; VAL=$(eval_js "document.querySelectorAll('[name=\"skills[]\"]')[2].checked"); t1 "eval (verify)"
assert_eq "skills[2] checked" "True" "$VAL"

# Verify skills[1] is NOT checked (wasn't targeted)
t0; VAL=$(eval_js "document.querySelectorAll('[name=\"skills[]\"]')[1].checked"); t1 "eval (verify)"
assert_eq "skills[1] unchecked" "False" "$VAL"

# --- Test 7: Native select dropdown ---
echo ""
echo "=== Test: Native select ==="
t0; RESULT=$($BU fill '{"country":{"select":"Japan"}}' 2>/dev/null); t1 "fill select dropdown"
assert_contains "select dropdown" "filled: 1/1" "$RESULT"
t0; VAL=$(eval_js "document.querySelector('[name=country]').value"); t1 "eval (verify)"
assert_eq "country value" "jp" "$VAL"

# --- Test 8: Range slider with numeric value ---
echo ""
echo "=== Test: Range slider ==="
t0; RESULT=$($BU fill '{"experience":15}' 2>/dev/null); t1 "fill range slider"
assert_contains "fill slider" "filled: 1/1" "$RESULT"
t0; VAL=$(eval_js "document.querySelector('[name=experience]').value"); t1 "eval (verify)"
assert_eq "slider value" "15" "$VAL"

# --- Test 9: Date/time inputs ---
echo ""
echo "=== Test: Date/time inputs ==="
t0; RESULT=$($BU fill '{"birthdate":"1990-06-15","meetingTime":"14:30","appointment":"2026-01-15T09:00"}' 2>/dev/null); t1 "fill 3 date/time fields"
assert_contains "fill dates" "filled: 3/3" "$RESULT"
t0; VAL=$(eval_js "document.querySelector('[name=birthdate]').value"); t1 "eval (verify)"
assert_eq "birthdate value" "1990-06-15" "$VAL"

# --- Test 10: Textarea ---
echo ""
echo "=== Test: Textarea ==="
t0; RESULT=$($BU fill '{"comments":"This is a test comment.\nWith multiple lines."}' 2>/dev/null); t1 "fill textarea"
assert_contains "fill textarea" "filled: 1/1" "$RESULT"
t0; VAL=$(eval_js "document.querySelector('[name=comments]').value.length > 10"); t1 "eval (verify)"
assert_eq "textarea has content" "True" "$VAL"

# --- Test 11: Autocomplete ---
echo ""
echo "=== Test: Autocomplete ==="
t0; RESULT=$($BU autocomplete framework "React" 2>/dev/null); t1 "autocomplete"
assert_contains "autocomplete React" "React" "$RESULT"
t0; VAL=$(eval_js "document.querySelector('[name=framework]').value"); t1 "eval (verify)"
assert_eq "autocomplete value" "React" "$VAL"

# --- Test 12: Click by #N (same-name elements) ---
echo ""
echo "=== Test: Click #N with same-name elements ==="
# Uncheck all skills checkboxes first
t0; $BU fill '{"skills[]":{"check":false,"index":0}}' &>/dev/null; t1 "fill uncheck[0]"
t0; $BU fill '{"skills[]":{"check":false,"index":1}}' &>/dev/null; t1 "fill uncheck[1]"
t0; $BU fill '{"skills[]":{"check":false,"index":2}}' &>/dev/null; t1 "fill uncheck[2]"
t0; $BU fill '{"skills[]":{"check":false,"index":3}}' &>/dev/null; t1 "fill uncheck[3]"
# Take a fresh snapshot and find the Rust checkbox #N
t0; SNAP2=$($BU snapshot --forms 2>/dev/null); t1 "snapshot --forms"
SNAP2_FILE=$(echo "$SNAP2" | grep -oP '\(.*?\)' | tr -d '()')
RUST_NUM=$(grep 'Rust.*skills' "$SNAP2_FILE" | grep -oP '#\d+' | tr -d '#' || echo "")
if [ -n "$RUST_NUM" ]; then
  t0; $BU click "#$RUST_NUM" &>/dev/null; t1 "click #$RUST_NUM"
  sleep 0.5  # click uses setTimeout(100ms) internally
  t0; VAL=$(eval_js "document.querySelectorAll('[name=\"skills[]\"]')[3].checked"); t1 "eval (verify)"
  assert_eq "click #N targets correct same-name element" "True" "$VAL"
else
  echo "  SKIP: click #N (couldn't find Rust checkbox number)"
fi

# --- Test 13: Error handling ---
echo ""
echo "=== Test: Error handling ==="
t0; RESULT=$($BU fill '42' 2>&1 || true); t1 "fill invalid JSON"
assert_contains "reject non-object JSON" "expects a JSON object" "$RESULT"

t0; RESULT=$($BU fill '{"nonexistent":"value"}' 2>&1 || true); t1 "fill missing field"
assert_contains "report missing field" "not found" "$RESULT"

# --- Test 14: Submit and verify result ---
echo ""
echo "=== Test: Submit form ==="
# Re-fill key fields for a clean submission
t0; $BU fill '{"firstName":"Final","lastName":"Test","email":"final@test.com","country":{"select":"Germany"},"employment":{"select":"Employed"}}' &>/dev/null; t1 "fill 5 fields for submit"
t0; $BU click submitBtn &>/dev/null; t1 "click submit"
sleep 0.5
t0; VAL=$(eval_js "document.getElementById('result').style.display"); t1 "eval (verify)"
assert_eq "result shown after submit" "block" "$VAL"
t0; VAL=$(eval_js "document.getElementById('result').textContent.includes('Final')"); t1 "eval (verify)"
assert_eq "result contains submitted data" "True" "$VAL"
