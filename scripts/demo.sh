#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

command_name="${1:-start}"

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

show_urls() {
  printf '\nLexGuard demo URLs\n'
  printf '  Demo UI:     http://localhost:8088\n'
  printf '  API docs:    http://localhost:8000/docs\n'
  printf '  RabbitMQ:    http://localhost:15672  (guest / guest)\n'
  printf '  Grafana:     http://localhost:3000   (admin / admin)\n'
  printf '  Prometheus:  http://localhost:9090\n\n'
}

wait_for_url() {
  local name="$1"
  local url="$2"
  local attempts=90

  printf 'Waiting for %s' "$name"
  for ((attempt = 1; attempt <= attempts; attempt += 1)); do
    if curl --fail --silent --max-time 2 "$url" >/dev/null 2>&1; then
      printf ' ready\n'
      return 0
    fi
    printf '.'
    sleep 2
  done

  printf ' timed out\n' >&2
  return 1
}

case "$command_name" in
  start)
    require_command docker
    require_command curl
    if [[ ! -f .env ]]; then
      echo "No .env file found. Create it with the R2 variables described in README.md." >&2
      exit 1
    fi
    echo "Starting the LexGuard demo stack..."
    docker compose up --build --detach
    wait_for_url "retrieval API" "http://localhost:8000/health"
    wait_for_url "demo UI" "http://localhost:8088"
    show_urls
    echo "Demo is ready at http://localhost:8088."
    ;;
  status)
    docker compose ps
    show_urls
    ;;
  logs)
    docker compose logs --follow --tail=120 ingestion-service embedding-worker supervisor api frontend
    ;;
  stop)
    echo "Stopping LexGuard containers while preserving database and model volumes..."
    docker compose down
    ;;
  reset)
    echo "Reset intentionally does not delete volumes. Run 'docker compose down --volumes' yourself if you want to erase demo data."
    exit 2
    ;;
  *)
    echo "Usage: ./scripts/demo.sh {start|status|logs|stop}" >&2
    exit 2
    ;;
esac
