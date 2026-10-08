#!/usr/bin/env bash
# Local simulated stack for UI work and browser tests: fake KiwiSDR + fake
# decoder-agent + real bridge. No Docker, no real decoding (see make acceptance).
#   tools/dev-stack.sh                         # bridge on :8073
#   BRIDGE_PORT=18073 tools/dev-stack.sh
#   GHOSTNET=1 SEED_NET=1 tools/dev-stack.sh   # GhostNet autopilot + a seeded recording
set -euo pipefail
cd "$(dirname "$0")/../bridge"
KIWI_PORT=${KIWI_PORT:-18070}
AGENT_PORT=${AGENT_PORT:-18074}
BRIDGE_PORT=${BRIDGE_PORT:-8073}
PERIOD=${PERIOD:-15}
DATA_DIR=${DATA_DIR:-$(mktemp -d)}
GHOSTNET=${GHOSTNET:-0}
DB_PATH=""
if [ "$GHOSTNET" = 1 ]; then
  DB_PATH="$DATA_DIR/ghostjs8.sqlite3"
  if [ "${SEED_NET:-0}" = 1 ]; then
    uv run --all-extras python -m ghostjs8 seed-net --db "$DB_PATH" --recordings "$DATA_DIR/nets" \
      --region "${GHOSTNET_REGION:-na}"
  fi
fi
trap 'kill 0' EXIT
uv run --all-extras python -m ghostjs8 fake-kiwi --host 127.0.0.1 --port "$KIWI_PORT" --align 0 &
uv run --all-extras python -m ghostjs8 fake-agent --port "$AGENT_PORT" --period "$PERIOD" &
GHOSTJS8_LISTEN_HOST=127.0.0.1 GHOSTJS8_LISTEN_PORT=$BRIDGE_PORT \
GHOSTJS8_AGENT_URL=ws://127.0.0.1:$AGENT_PORT/agent \
GHOSTJS8_RECEIVER_HOST=${RECEIVER_HOST-127.0.0.1} GHOSTJS8_RECEIVER_PORT=$KIWI_PORT \
GHOSTJS8_DB_PATH=$DB_PATH GHOSTJS8_LOG_FORMAT=text GHOSTJS8_ALLOW_PRIVATE_RECEIVERS=true \
GHOSTJS8_DIRECTORY_URL=${DIRECTORY_URL:-http://rx.linkfanel.net/kiwisdr_com.js} \
GHOSTJS8_GHOSTNET=$([ "$GHOSTNET" = 1 ] && echo on || echo off) \
GHOSTJS8_GHOSTNET_REGION=${GHOSTNET_REGION:-na} GHOSTJS8_HOME_GRID=${HOME_GRID:-EN34} \
GHOSTJS8_RECORDINGS_DIR=$DATA_DIR/nets \
  uv run --all-extras python -m ghostjs8 bridge &
wait
