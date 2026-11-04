#!/usr/bin/env bash
# Runs the whole game locally without Docker. Ctrl+C stops everything.
#
#   scripts/dev.sh
#
# Needs redis-server, Go, Node and backend/.venv. Ports can be moved with
# REDIS_PORT, BACKEND_PORT, GATEWAY_PORT and FRONTEND_PORT.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
logs="${CATAN_LOGS:-$root/.logs}"
bin="$logs/bin"
mkdir -p "$bin"

redis_port="${REDIS_PORT:-6379}"
backend_port="${BACKEND_PORT:-8000}"
gateway_port="${GATEWAY_PORT:-8080}"
frontend_port="${FRONTEND_PORT:-5173}"

export REDIS_URL="redis://localhost:$redis_port/0"

pids=()
cleanup() {
    trap - EXIT INT TERM
    kill "${pids[@]}" 2>/dev/null || true
    wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

wait_for() {
    local name="$1" url="$2"
    for _ in $(seq 1 100); do
        if curl -fs --noproxy '*' -m 1 -o /dev/null "$url"; then
            echo "  $name is up"
            return
        fi
        sleep 0.2
    done
    echo "$name did not start, see $logs" >&2
    exit 1
}

(cd "$root/gateway" && go build -o "$bin/gateway" ./cmd/gateway && go build -o "$bin/bots" ./cmd/bots)

redis-server --port "$redis_port" --save '' --appendonly no > "$logs/redis.log" 2>&1 &
pids+=($!)

(cd "$root/backend" && exec .venv/bin/uvicorn app.main:app --port "$backend_port" --workers "${BACKEND_WORKERS:-2}" --log-level warning) > "$logs/backend.log" 2>&1 &
pids+=($!)
wait_for backend "http://localhost:$backend_port/health"

PORT="$gateway_port" BACKEND_URL="http://localhost:$backend_port" "$bin/gateway" > "$logs/gateway.log" 2>&1 &
pids+=($!)
wait_for gateway "http://localhost:$gateway_port/health"

GATEWAY_URL="ws://localhost:$gateway_port/ws" BACKEND_URL="http://localhost:$backend_port" "$bin/bots" > "$logs/bots.log" 2>&1 &
pids+=($!)

(cd "$root/frontend" && BACKEND_URL="http://localhost:$backend_port" GATEWAY_URL="ws://localhost:$gateway_port" exec node_modules/.bin/vite --port "$frontend_port" --strictPort) > "$logs/frontend.log" 2>&1 &
pids+=($!)
wait_for frontend "http://localhost:$frontend_port/"

echo "Catan is running at http://localhost:$frontend_port (Ctrl+C stops it)"
wait
