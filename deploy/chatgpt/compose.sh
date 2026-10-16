#!/usr/bin/env sh
set -eu
umask 077
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
STATE_DIR=${NOTEBOOKLM_CHATGPT_STATE_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/notebooklm-chatgpt}
[ -f "$STATE_DIR/runtime.env" ] || {
  printf '%s\n' 'Run prepare.py first; the private runtime.env is missing.' >&2
  exit 1
}
# Do not source runtime.env or print `docker compose config`: it contains secrets.
exec docker compose --project-name notebooklm-chatgpt \
  --env-file "$STATE_DIR/runtime.env" \
  -f "$HERE/../docker-compose.yml" \
  -f "$HERE/../docker-compose.build.yml" \
  -f "$HERE/compose.yml" --profile cloudflare "$@"
