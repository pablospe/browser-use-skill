#!/bin/bash
# browser-use skill wrapper
# Auto-bootstraps local venv on first run via uv, then delegates all args.
# Usage: bash ~/.claude/skills/browser-use/bu.sh [--connect] <command> [args...]
#        bash ~/.claude/skills/browser-use/bu.sh recipe <subcommand> [args...]

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONUTF8=1

# Collect leading flags (--connect, --headed, etc.) before the subcommand
BU_FLAGS=()
while [[ "${1:-}" == --* ]]; do
  BU_FLAGS+=("$1")
  shift
done

# Install uv if missing
if ! command -v uv &>/dev/null; then
  echo "[browser-use] uv not found — installing..." >&2
  if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OS" == "Windows_NT" ]]; then
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex" >&2
    # Reload PATH so uv is available in this session
    export PATH="$USERPROFILE/.local/bin:$PATH"
  else
    curl -LsSf https://astral.sh/uv/install.sh | sh >&2
    export PATH="$HOME/.local/bin:$PATH"
  fi
  if ! command -v uv &>/dev/null; then
    echo "[browser-use] ERROR: uv install failed. Install manually: https://docs.astral.sh/uv/getting-started/installation/" >&2
    exit 1
  fi
  echo "[browser-use] uv installed successfully." >&2
fi

# Intercept 'recipe' subcommand — route to recipe.py instead of browser-use CLI
if [ "$1" = "recipe" ]; then
  shift
  exec uv run --directory "$SKILL_DIR" python "$SKILL_DIR/recipe.py" "${BU_FLAGS[@]}" "$@"
fi

# Intercept 'fill' subcommand — batch fill fields from JSON
if [ "$1" = "fill" ]; then
  shift
  exec uv run --directory "$SKILL_DIR" python "$SKILL_DIR/batch_fill.py" "${BU_FLAGS[@]}" "$@"
fi

# Intercept 'diff' subcommand — compare two snapshots
if [ "$1" = "diff" ]; then
  shift
  exec uv run --directory "$SKILL_DIR" python "$SKILL_DIR/diff_snapshot.py" "${BU_FLAGS[@]}" "$@"
fi

# Intercept 'snapshot' subcommand — structured YAML snapshot saved to file
if [ "$1" = "snapshot" ]; then
  shift
  exec uv run --directory "$SKILL_DIR" python "$SKILL_DIR/snapshot.py" "${BU_FLAGS[@]}" "$@"
fi

# Intercept 'selected' subcommand — read user-selected elements from highlights
if [ "$1" = "selected" ]; then
  shift
  exec uv run --directory "$SKILL_DIR" browser-use "${BU_FLAGS[@]}" "$@" eval "window.__buSelected ? JSON.stringify(Array.from(window.__buSelected.values())) : '[]'"
fi

# Intercept 'clear-highlights' subcommand — remove highlight overlays
if [ "$1" = "clear-highlights" ]; then
  shift
  exec uv run --directory "$SKILL_DIR" browser-use "${BU_FLAGS[@]}" "$@" eval "document.querySelectorAll('[data-bu-highlight]').forEach(e=>e.remove());'cleared'"
fi

# Intercept 'cursor' subcommand — show/hide AI cursor
if [ "$1" = "cursor" ]; then
  shift
  exec uv run --directory "$SKILL_DIR" python "$SKILL_DIR/cursor_action.py" "$1" "${BU_FLAGS[@]}" "${@:2}"
fi

# Intercept 'click-ref' subcommand — animated cursor + click by snapshot ref
if [ "$1" = "click-ref" ]; then
  shift
  exec uv run --directory "$SKILL_DIR" python "$SKILL_DIR/cursor_action.py" click "$1" "${BU_FLAGS[@]}" "${@:2}"
fi

# Intercept 'hover-ref' subcommand — animated cursor + hover by snapshot ref
if [ "$1" = "hover-ref" ]; then
  shift
  exec uv run --directory "$SKILL_DIR" python "$SKILL_DIR/cursor_action.py" hover "$1" "${BU_FLAGS[@]}" "${@:2}"
fi

# Intercept 'scroll-to-ref' subcommand — animated cursor + scroll to snapshot ref
if [ "$1" = "scroll-to-ref" ]; then
  shift
  exec uv run --directory "$SKILL_DIR" python "$SKILL_DIR/cursor_action.py" scroll "$1" "${BU_FLAGS[@]}" "${@:2}"
fi

# Intercept 'cursor-fill' subcommand — animated cursor + batch fill (slower but visual)
if [ "$1" = "cursor-fill" ]; then
  shift
  exec uv run --directory "$SKILL_DIR" python "$SKILL_DIR/cursor_action.py" fill "$@"
fi

exec uv run --directory "$SKILL_DIR" browser-use "${BU_FLAGS[@]}" "$@"
