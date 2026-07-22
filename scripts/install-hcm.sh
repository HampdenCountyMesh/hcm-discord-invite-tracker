#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="/meshdata/hcm-invite-tracker"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required." >&2
  exit 1
fi

sudo mkdir -p "$DATA_DIR/backups"
sudo chown -R 10001:10001 "$DATA_DIR"

cd "$ROOT_DIR"
if [[ ! -f .env ]]; then
  cp .env.hcm.example .env
  chmod 600 .env
  echo "Created .env. Fill in the Discord token and IDs, then run this script again."
  exit 2
fi

if grep -q 'replace-with-' .env; then
  echo ".env still contains placeholder values." >&2
  exit 2
fi

docker compose -f compose.hcm.yml build
docker compose -f compose.hcm.yml up -d
docker compose -f compose.hcm.yml ps
