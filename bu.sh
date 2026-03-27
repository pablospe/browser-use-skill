#!/bin/bash
# browser-use skill wrapper
# Auto-bootstraps local venv on first run via uv, then delegates all args.
# Usage: bash ~/.claude/skills/browser-use/bu.sh [--connect] <command> [args...]
#        bash ~/.claude/skills/browser-use/bu.sh recipe <subcommand> [args...]

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONUTF8=1

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
  exec uv run --directory "$SKILL_DIR" python "$SKILL_DIR/recipe.py" "$@"
fi

# Intercept 'fill' subcommand — batch fill fields from JSON
if [ "$1" = "fill" ]; then
  shift
  exec uv run --directory "$SKILL_DIR" python "$SKILL_DIR/batch_fill.py" "$@"
fi

# Intercept 'snapshot' subcommand — structured YAML snapshot saved to file
if [ "$1" = "snapshot" ]; then
  shift
  exec uv run --directory "$SKILL_DIR" python "$SKILL_DIR/snapshot.py" "$@"
fi

# Intercept 'clear-highlights' subcommand — remove highlight overlays
if [ "$1" = "clear-highlights" ]; then
  shift
  exec uv run --directory "$SKILL_DIR" browser-use "$@" eval "document.querySelectorAll('[data-bu-highlight]').forEach(e=>e.remove());'cleared'"
fi

exec uv run --directory "$SKILL_DIR" browser-use "$@"
