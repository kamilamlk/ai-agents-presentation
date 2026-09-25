#!/usr/bin/env bash
#
# anthropic-env.sh -- API access for the current terminal session only.
#
#   source ./anthropic-env.sh on       load values from ./.secrets
#   source ./anthropic-env.sh off      unset them
#   source ./anthropic-env.sh status   show what is set (the fact, never the value)
#
# MUST be used with `source` (or `.`). Running it as ./anthropic-env.sh will not
# work: a child process cannot change its parent shell's environment. The script
# detects that and says so.
#
# Where the values come from:
#   1. ANTHROPIC_SECRETS_FILE, if set
#   2. ./.secrets in the current directory
#   3. .secrets next to this script
#
# The file is plain shell, sourced as-is:
#
#     export ANTHROPIC_AUTH_TOKEN="..."
#     export ANTHROPIC_BASE_URL="https://..."
#
# A template lives in .secrets.example. Never commit .secrets: it is in
# .gitignore, but check again before handing the repository to anyone.

# -- were we sourced, or run? ------------------------------------------------

_ae_sourced=0
_ae_self=""
if [ -n "${BASH_VERSION:-}" ]; then
    _ae_self="${BASH_SOURCE[0]}"
    [ "$_ae_self" != "$0" ] && _ae_sourced=1
elif [ -n "${ZSH_VERSION:-}" ]; then
    _ae_self="$0"
    case "${ZSH_EVAL_CONTEXT:-}" in *:file*) _ae_sourced=1 ;; esac
fi

if [ "$_ae_sourced" -ne 1 ]; then
    echo "This script must be sourced, not executed:" >&2
    echo "    source ./anthropic-env.sh on" >&2
    exit 1
fi

_ae_dir="."
if [ -n "$_ae_self" ]; then
    _ae_dir="$(cd "$(dirname "$_ae_self")" 2>/dev/null && pwd)" || _ae_dir="."
fi

# -- commands ---------------------------------------------------------------

_ae_secrets_file() {
    if [ -n "${ANTHROPIC_SECRETS_FILE:-}" ]; then
        printf '%s' "$ANTHROPIC_SECRETS_FILE"
    elif [ -f "./.secrets" ]; then
        printf '%s' "./.secrets"
    else
        printf '%s' "$_ae_dir/.secrets"
    fi
}

_ae_on() {
    local f perms
    f="$(_ae_secrets_file)"

    if [ ! -f "$f" ]; then
        echo "No secrets file found at: $f" >&2
        echo "Create one from the template:" >&2
        echo "    cp .secrets.example .secrets && chmod 600 .secrets" >&2
        return 1
    fi

    perms="$(stat -f '%OLp' "$f" 2>/dev/null || stat -c '%a' "$f" 2>/dev/null)"
    case "$perms" in
        600|400) : ;;
        *) echo "WARNING: permissions on $f are ${perms:-unknown}; others can read it." >&2
           echo "Fix with: chmod 600 $f" >&2 ;;
    esac

    # shellcheck disable=SC1090
    . "$f"

    if [ -z "${ANTHROPIC_AUTH_TOKEN:-}" ]; then
        echo "$f does not define ANTHROPIC_AUTH_TOKEN." >&2
        return 1
    fi
    export ANTHROPIC_AUTH_TOKEN

    if [ -n "${ANTHROPIC_BASE_URL:-}" ]; then
        export ANTHROPIC_BASE_URL
    else
        echo "WARNING: $f does not define ANTHROPIC_BASE_URL." >&2
        echo "Without it the request goes to api.anthropic.com and fails with 401." >&2
    fi

    if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
        echo "WARNING: ANTHROPIC_API_KEY is set and will win over AUTH_TOKEN." >&2
        echo "Drop it for this session: unset ANTHROPIC_API_KEY" >&2
    fi

    echo "Loaded from $f. Lives in this terminal session only."
    _ae_status
}

_ae_off() {
    unset ANTHROPIC_AUTH_TOKEN
    unset ANTHROPIC_BASE_URL
    echo "Unset."
    _ae_status
}

_ae_status() {
    [ -n "${ANTHROPIC_API_KEY:-}" ]    && echo "  ANTHROPIC_API_KEY    = set" || echo "  ANTHROPIC_API_KEY    = unset"
    [ -n "${ANTHROPIC_AUTH_TOKEN:-}" ] && echo "  ANTHROPIC_AUTH_TOKEN = set" || echo "  ANTHROPIC_AUTH_TOKEN = unset"
    [ -n "${ANTHROPIC_BASE_URL:-}" ]   && echo "  ANTHROPIC_BASE_URL   = set" || echo "  ANTHROPIC_BASE_URL   = unset"
}

# -- dispatch ---------------------------------------------------------------

case "${1:-}" in
    on)     _ae_on ;;
    off)    _ae_off ;;
    status) _ae_status ;;
    *)      echo "usage: source ./anthropic-env.sh {on|off|status}" >&2; false ;;
esac
_ae_rc=$?

unset -f _ae_on _ae_off _ae_status _ae_secrets_file 2>/dev/null
unset _ae_sourced _ae_self _ae_dir

# The exit code matters so you can write:
#     source ./anthropic-env.sh on && python3 example_tool_loop.py
if [ "$_ae_rc" -eq 0 ]; then
    unset _ae_rc
    return 0
else
    unset _ae_rc
    return 1
fi
