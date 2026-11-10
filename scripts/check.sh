#!/usr/bin/env bash
# Runs every check before a merge. GitHub Actions is off for this repository, so this is the CI.
#
#   scripts/check.sh          lint and tests of the backend, gateway and frontend
#   scripts/check.sh --e2e    also plays a game in a browser against 3 hard bots
#
# Needs what scripts/dev.sh needs. Backend tests use Redis on localhost:6379, started here if absent,
# in database 14, so a game running in scripts/dev.sh (database 0) is left alone.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
step() { printf '\n== %s\n' "$1"; }

if ! redis-cli -p 6379 ping > /dev/null 2>&1; then
    redis-server --port 6379 --save '' --appendonly no --daemonize yes > /dev/null
fi

step backend
(cd "$root/backend" && .venv/bin/ruff check . && .venv/bin/python -m pytest -q --cov=app --cov-report=term --cov-fail-under=90)

step gateway
cd "$root/gateway"
unformatted="$(gofmt -l .)"
if [ -n "$unformatted" ]; then
    echo "not formatted: $unformatted" >&2
    exit 1
fi
go vet ./...
# The race detector needs cgo, which a bare WSL install may lack
if command -v gcc > /dev/null; then
    go test -race -count=2 ./...
else
    echo "no C compiler, testing without -race"
    go test -count=2 ./...
fi

step frontend
(cd "$root/frontend" && npm run lint && npm test && npm run build)

if [ "${1:-}" = "--e2e" ]; then
    step end-to-end
    # Ports of their own, so a running scripts/dev.sh is not disturbed
    export REDIS_PORT=6390 BACKEND_PORT=8190 GATEWAY_PORT=8191 FRONTEND_PORT=5190 BOT_DELAY_MS=150
    CATAN_LOGS="$root/.logs/check" "$root/scripts/dev.sh" > /dev/null 2>&1 &
    stack=$!
    trap 'kill $stack 2>/dev/null; wait $stack 2>/dev/null || true' EXIT
    until curl -fs --noproxy '*' -m 1 -o /dev/null "http://localhost:$FRONTEND_PORT/"; do
        kill -0 $stack 2>/dev/null || { echo "the stack did not start, see .logs/check" >&2; exit 1; }
        sleep 1
    done
    (cd "$root/e2e" && BASE_URL="http://localhost:$FRONTEND_PORT" PLAYERS=1 BOTS=3 BOT_LEVEL=hard npm test)
fi

printf '\nAll checks passed.\n'
