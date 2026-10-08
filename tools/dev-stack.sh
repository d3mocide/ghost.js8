#!/usr/bin/env bash
# Local simulated stack for UI work and browser tests: fake KiwiSDR + fake
# decoder-agent + real bridge. No Docker, no real decoding (see make acceptance).
#   tools/dev-stack.sh            # bridge on :8073
#   BRIDGE_PORT=18073 tools/dev-stack.sh
set -euo pipefail
cd "$(dirname "$0")/../bridge"
KIWI_PORT=${KIWI_PORT:-18070}
AGENT_PORT=${AGENT_PORT:-18074}
BRIDGE_PORT=${BRIDGE_PORT:-8073}
PERIOD=${PERIOD:-15}
trap 'kill 0' EXIT
uv run --all-extras python -m ghostjs8 fake-kiwi --host 127.0.0.1 --port "$KIWI_PORT" --align 0 &
uv run --all-extras python -m ghostjs8 fake-agent --port "$AGENT_PORT" --period "$PERIOD" &
GHOSTJS8_LISTEN_HOST=127.0.0.1 GHOSTJS8_LISTEN_PORT=$BRIDGE_PORT \
GHOSTJS8_AGENT_URL=ws://127.0.0.1:$AGENT_PORT/agent \
GHOSTJS8_RECEIVER_HOST=${RECEIVER_HOST-127.0.0.1} GHOSTJS8_RECEIVER_PORT=$KIWI_PORT \
GHOSTJS8_DB_PATH= GHOSTJS8_LOG_FORMAT=text GHOSTJS8_ALLOW_PRIVATE_RECEIVERS=true \
GHOSTJS8_DIRECTORY_URL=${DIRECTORY_URL:-http://rx.linkfanel.net/kiwisdr_com.js} \
  uv run --all-extras python -m ghostjs8 bridge &
wait
