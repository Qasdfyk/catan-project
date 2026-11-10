#!/usr/bin/env bash
# Plays bot levels against each other over the whole stack and writes the
# report to benchmarks/results/tournament_<name>.txt. Every other argument goes
# to the tournament, for example:
#
#   benchmarks/tournament.sh easy_vs_medium -games 400 -levels easy,medium,medium,medium
#
# Needs backend/.venv, Go and redis-server. BACKEND_WORKERS sets the uvicorn workers.
set -uo pipefail

if [ $# -lt 1 ]; then
    echo "usage: $0 <name> [tournament flags]" >&2
    exit 2
fi
name="$1"
shift

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
results="$root/benchmarks/results"
work="$(mktemp -d)"
venv="$root/backend/.venv/bin"
mkdir -p "$results"

export REDIS_URL=redis://localhost:6380/0

(cd "$root/gateway" && go build -o "$work/gateway" ./cmd/gateway && go build -o "$work/tournament" ./cmd/tournament) || exit 1

pids=()
cleanup() {
    kill "${pids[@]}" 2>/dev/null
    wait 2>/dev/null
    rm -rf "$work"
}
trap cleanup EXIT

redis-server --port 6380 --save '' --appendonly no > /dev/null 2>&1 &
pids+=($!)
until redis-cli -p 6380 ping > /dev/null 2>&1; do sleep 0.1; done

# The tournament keeps its own copies with -records; these would only pile up
(cd "$root/backend" && RECORDS_DIR="$work/records" exec "$venv/uvicorn" app.main:app --port 8100 --workers "${BACKEND_WORKERS:-4}" --log-level critical) &
pids+=($!)
until curl -fs --noproxy '*' -m 1 -o /dev/null http://localhost:8100/health; do sleep 0.2; done

PORT=8180 BACKEND_URL=http://localhost:8100 "$work/gateway" 2> /dev/null &
pids+=($!)
until curl -fs --noproxy '*' -m 1 -o /dev/null http://localhost:8180/health; do sleep 0.1; done

# The per-game log goes to the terminal, the report to the results file
"$work/tournament" -api http://127.0.0.1:8100 -ws ws://127.0.0.1:8180/ws "$@" | tee "$results/tournament_$name.txt"
