#!/usr/bin/env bash
# Run the bundled Day06 without depending on the caller's working directory.
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
day06_root="$project_root/Day06/K5-L3B-Day06-2A202603876-DataIngestionEngineering"
fetch_source=false

case "${1:-}" in
  --fetch) fetch_source=true ;;
  --help|-h)
    echo 'Usage: bash scripts/reproduce_day06.sh [--fetch]'
    echo 'Build, validate, ingest, evaluate dev/test, and run Day06 tests.'
    echo '--fetch also downloads the pinned source PDF and regenerates the corpus.'
    exit 0
    ;;
  '') ;;
  *) echo 'Unknown argument. Use --help.' >&2; exit 2 ;;
esac
if (( $# > 1 )); then
  echo 'Too many arguments. Use --help.' >&2
  exit 2
fi

command -v docker >/dev/null || { echo 'Install Docker Engine/Desktop and Compose first.' >&2; exit 1; }
docker compose version >/dev/null
if ! docker info >/dev/null 2>&1; then
  echo 'Docker is unavailable: start the daemon and grant this account Docker access.' >&2
  echo 'No build or database changes have been performed.' >&2
  exit 1
fi

compose=(docker compose -f "$day06_root/starter/docker-compose.yml" -p day07-day06)
"${compose[@]}" build pipeline
"${compose[@]}" up -d --wait postgres
"${compose[@]}" run --rm pipeline scripts/check_setup.py
"${compose[@]}" run --rm pipeline -m src.run preflight
if "$fetch_source"; then
  "${compose[@]}" run --rm pipeline -m src.run fetch
fi
"${compose[@]}" run --rm pipeline -m src.run validate
"${compose[@]}" run --rm pipeline -m scripts.smoke_embedding
"${compose[@]}" run --rm pipeline -m scripts.smoke_embedding --database --offline
"${compose[@]}" run --rm pipeline -m src.run ingest
"${compose[@]}" run --rm pipeline -m src.run evaluate --split dev
"${compose[@]}" run --rm pipeline -m src.run evaluate --split test
"${compose[@]}" run --rm --workdir /workspace pipeline -m pytest -q
echo "Day06 reproduction complete. Results: $day06_root/results/"
echo 'PostgreSQL remains available on 127.0.0.1:55433 for subsequent Day07 work.'
