#!/usr/bin/env bash
#
# anthropic-env.sh — доступ к Anthropic API только в текущей сессии терминала.
#
#   source ./anthropic-env.sh on       загрузит значения из ./.secrets
#   source ./anthropic-env.sh off      снимет их
#   source ./anthropic-env.sh status   покажет, что выставлено (факт, без значений)
#
# ОБЯЗАТЕЛЬНО через `source` (или `.`). Запуск как ./anthropic-env.sh не сработает:
# дочерний процесс не может менять окружение родительской оболочки. Скрипт это ловит.
#
# Откуда берутся значения:
#   1. ANTHROPIC_SECRETS_FILE, если задана
#   2. ./.secrets в текущей директории
#   3. .secrets рядом с самим скриптом
#
# Формат файла — обычный shell, он подключается через source:
#
#     export ANTHROPIC_AUTH_TOKEN="..."
#     export ANTHROPIC_BASE_URL="https://..."
#
# Образец лежит в .secrets.example. Файл .secrets коммитить нельзя никогда:
# он в .gitignore, но перед раздачей репозитория участникам проверь ещё раз.

# --- проверка, что нас подключили через source, а не запустили ----------------

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
    echo "Этот скрипт нужно подключать, а не запускать:" >&2
    echo "    source ./anthropic-env.sh on" >&2
    exit 1
fi

_ae_dir="."
if [ -n "$_ae_self" ]; then
    _ae_dir="$(cd "$(dirname "$_ae_self")" 2>/dev/null && pwd)" || _ae_dir="."
fi

# --- команды -----------------------------------------------------------------

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
        echo "Не найден файл со значениями: $f" >&2
        echo "Создать по образцу:" >&2
        echo "    cp .secrets.example .secrets && chmod 600 .secrets" >&2
        return 1
    fi

    perms="$(stat -f '%OLp' "$f" 2>/dev/null || stat -c '%a' "$f" 2>/dev/null)"
    case "$perms" in
        600|400) : ;;
        *) echo "ВНИМАНИЕ: права на $f = ${perms:-неизвестны}, файл виден лишним." >&2
           echo "Починить: chmod 600 $f" >&2 ;;
    esac

    # shellcheck disable=SC1090
    . "$f"

    if [ -z "${ANTHROPIC_AUTH_TOKEN:-}" ]; then
        echo "В $f нет ANTHROPIC_AUTH_TOKEN." >&2
        return 1
    fi
    export ANTHROPIC_AUTH_TOKEN

    if [ -n "${ANTHROPIC_BASE_URL:-}" ]; then
        export ANTHROPIC_BASE_URL
    else
        echo "ВНИМАНИЕ: в $f нет ANTHROPIC_BASE_URL." >&2
        echo "Без него запрос уйдёт на api.anthropic.com и упадёт с 401." >&2
    fi

    if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
        echo "ВНИМАНИЕ: ANTHROPIC_API_KEY задан и перебьёт AUTH_TOKEN." >&2
        echo "Сними его в этой сессии: unset ANTHROPIC_API_KEY" >&2
    fi

    echo "Загружено из $f. Живёт только в этой сессии терминала."
    _ae_status
}

_ae_off() {
    unset ANTHROPIC_AUTH_TOKEN
    unset ANTHROPIC_BASE_URL
    echo "Снято."
    _ae_status
}

_ae_status() {
    [ -n "${ANTHROPIC_API_KEY:-}" ]    && echo "  ANTHROPIC_API_KEY    = set" || echo "  ANTHROPIC_API_KEY    = unset"
    [ -n "${ANTHROPIC_AUTH_TOKEN:-}" ] && echo "  ANTHROPIC_AUTH_TOKEN = set" || echo "  ANTHROPIC_AUTH_TOKEN = unset"
    [ -n "${ANTHROPIC_BASE_URL:-}" ]   && echo "  ANTHROPIC_BASE_URL   = set" || echo "  ANTHROPIC_BASE_URL   = unset"
}

# --- разбор аргумента --------------------------------------------------------

case "${1:-}" in
    on)     _ae_on ;;
    off)    _ae_off ;;
    status) _ae_status ;;
    *)      echo "usage: source ./anthropic-env.sh {on|off|status}" >&2; false ;;
esac
_ae_rc=$?

unset -f _ae_on _ae_off _ae_status _ae_secrets_file 2>/dev/null
unset _ae_sourced _ae_self _ae_dir

# код возврата нужен, чтобы можно было писать:
#     source ./anthropic-env.sh on && python example_tool_loop.py
if [ "$_ae_rc" -eq 0 ]; then
    unset _ae_rc
    return 0
else
    unset _ae_rc
    return 1
fi
