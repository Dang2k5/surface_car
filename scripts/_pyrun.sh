#!/usr/bin/env bash
# Cross-platform Python launcher for AI log hooks.
# Tries py -3 → python3 → python on PATH; on Windows, falls back to common
# Python install locations because Git Bash launched by some hooks gets a
# stripped PATH that omits the Windows Python directory.
#
# `py` is tried first because Windows puts "app execution alias" stubs for
# `python`/`python3` in WindowsApps ahead of any real install on PATH — those
# stubs don't run Python, they just print a Microsoft Store prompt and exit
# non-zero. We also explicitly skip python/python3 if they resolve to such a
# stub, so a real interpreter further down PATH (or the fallback probe) gets
# used instead.
# Designed to be sourced or called as: bash scripts/_pyrun.sh <script> [args...]
#
# Exits 0 silently if no Python is found — hooks must never block the AI tool.
set -u

is_store_stub() {
  case "$1" in
    *WindowsApps*|*windowsapps*) return 0 ;;
    *) return 1 ;;
  esac
}

PY=""

if command -v py >/dev/null 2>&1; then
  PY="py -3"
elif command -v python3 >/dev/null 2>&1 && ! is_store_stub "$(command -v python3)"; then
  PY=python3
elif command -v python >/dev/null 2>&1 && ! is_store_stub "$(command -v python)"; then
  PY=python
fi

if [ -z "$PY" ]; then
  # PATH lookup failed (or only found Store stubs) — probe standard Windows install locations.
  shopt -s nullglob 2>/dev/null || true
  for cand in \
    /c/Users/*/AppData/Local/Programs/Python/Python*/python.exe \
    "/c/Program Files/Python"*/python.exe \
    "/c/Program Files (x86)/Python"*/python.exe \
    /c/Python*/python.exe; do
    if [ -x "$cand" ]; then PY="$cand"; break; fi
  done
  shopt -u nullglob 2>/dev/null || true
fi

[ -n "$PY" ] || exit 0

# shellcheck disable=SC2086
exec $PY "$@"
