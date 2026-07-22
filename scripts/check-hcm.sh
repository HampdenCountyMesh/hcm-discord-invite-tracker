#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
docker compose -f compose.hcm.yml ps
docker logs --tail 100 hcm-invite-tracker
printf '\nDashboard health:\n'
curl -fsS http://127.0.0.1:8091/healthz || true
printf '\n'
