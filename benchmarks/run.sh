#!/usr/bin/env bash
# Repeats every measurement in docs/benchmarks.md and writes benchmarks/results/.
# Needs backend/.venv, Go, redis-server and a venv with python-socketio in $SIO_VENV.
set -uo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
results="$root/benchmarks/results"
work="${BENCH_DIR:-$(mktemp -d)}"
venv="$root/backend/.venv/bin"
mkdir -p "$results"

export REDIS_URL=redis://localhost:6380/0

(cd "$root/gateway" && go build -o "$work/gateway" ./cmd/gateway && go build -o "$work/loadtest" ./cmd/loadtest)

redis-server --port 6380 --save '' --appendonly no > /dev/null 2>&1 &
redis_pid=$!

backend_pid=""
start_backend() {
    (cd "$root/backend" && exec "$venv/uvicorn" app.main:app --port 8100 --workers "$1" --log-level critical) &
    backend_pid=$!
    until curl -fs --noproxy '*' -m 1 -o /dev/null http://localhost:8100/health; do sleep 0.2; done
}
stop_backend() {
    kill "$backend_pid" 2>/dev/null
    wait "$backend_pid" 2>/dev/null
}
start_gateway() {
    PORT="$1" BACKEND_URL=http://localhost:8100 "$work/gateway" 2> /dev/null &
    gateway_pid=$!
    until curl -fs --noproxy '*' -m 1 -o /dev/null "http://localhost:$1/health"; do sleep 0.1; done
}
usage() {
    awk '/VmRSS/ { printf "rss=%.0fMB ", $2 / 1024 }' "/proc/$1/status"
    awk '{ printf "cpu=%.1fs\n", ($14 + $15) / 100 }' "/proc/$1/stat"
}
trap 'kill $redis_pid 2>/dev/null' EXIT

{
    echo "# CPU: $(grep -c ^processor /proc/cpuinfo) threads, $(awk '/MemTotal/ { printf "%.0f GB", $2 / 1048576 }' /proc/meminfo)"
    start_backend 2
    for spec in "400 1" "4000 0.25" "4000 1" "10000 0.25" "4000 4"; do
        read -r players rate <<< "$spec"

        echo "## python-socketio players=$players rate=$rate/room/s"
        (cd "$root/benchmarks" && exec "$SIO_VENV/bin/uvicorn" socketio_baseline:app --port 8090 --log-level critical) &
        pid=$!
        until curl -fs --noproxy '*' -m 1 -o /dev/null 'http://localhost:8090/socket.io/?EIO=4&transport=polling'; do sleep 0.2; done
        "$work/loadtest" -redis redis://127.0.0.1:6380/0 -players "$players" -rate "$rate" \
            -socketio 'ws://127.0.0.1:8090/socket.io/?EIO=4&transport=websocket' | tail -1
        usage "$pid"
        kill "$pid"; wait "$pid" 2>/dev/null

        echo "## gateway players=$players rate=$rate/room/s"
        start_gateway 8180
        "$work/loadtest" -api http://127.0.0.1:8100 -ws ws://127.0.0.1:8180/ws -redis redis://127.0.0.1:6380/0 \
            -players "$players" -rate "$rate" | tail -1
        usage "$gateway_pid"
        kill "$gateway_pid"; wait "$gateway_pid" 2>/dev/null
    done
    stop_backend
} 2>&1 | tee "$results/fanout.txt"

{
    start_gateway 8180
    for workers in 1 2 4 8; do
        echo "## backend workers=$workers"
        start_backend "$workers"
        for rooms in 100 400 800; do
            timeout 120 "$venv/python" "$root/benchmarks/throughput.py" --rooms "$rooms" || echo "rooms=$rooms did not finish"
        done
        stop_backend
    done
    kill "$gateway_pid"; wait "$gateway_pid" 2>/dev/null
} 2>&1 | tee "$results/throughput.txt"

{
    start_backend 4
    start_gateway 8180
    first=$gateway_pid
    start_gateway 8181
    echo "## two gateways, players of each room split between them"
    timeout 120 "$venv/python" "$root/benchmarks/throughput.py" --rooms 200 --ws ws://localhost:8180/ws,ws://localhost:8181/ws
    kill "$first" "$gateway_pid"
    stop_backend
} 2>&1 | tee "$results/two_gateways.txt"
