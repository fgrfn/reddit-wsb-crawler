#!/bin/sh
set -eu

APP_USER="crawler"
APP_GROUP="crawler"
APP_DATA_DIR="/app/data"
APP_LOG_DIR="/app/logs"

: "${PUID:=1000}"
: "${PGID:=1000}"

_is_uint() {
    case "$1" in
        ''|*[!0-9]*) return 1 ;;
        *) return 0 ;;
    esac
}

if [ "$(id -u)" = "0" ]; then
    if ! _is_uint "$PUID" || ! _is_uint "$PGID"; then
        echo "ERROR: PUID and PGID must be numeric, got PUID=$PUID PGID=$PGID" >&2
        exit 1
    fi

    current_gid="$(getent group "$APP_GROUP" | cut -d: -f3)"
    current_uid="$(id -u "$APP_USER")"

    if [ "$current_gid" != "$PGID" ]; then
        groupmod -o -g "$PGID" "$APP_GROUP"
    fi

    if [ "$current_uid" != "$PUID" ]; then
        usermod -o -u "$PUID" -g "$PGID" "$APP_USER"
    else
        usermod -g "$PGID" "$APP_USER"
    fi

    mkdir -p "$APP_DATA_DIR" "$APP_LOG_DIR"
    chown -R "$APP_USER:$APP_GROUP" "$APP_DATA_DIR" "$APP_LOG_DIR"

    exec gosu "$APP_USER:$APP_GROUP" "$@"
fi

exec "$@"
