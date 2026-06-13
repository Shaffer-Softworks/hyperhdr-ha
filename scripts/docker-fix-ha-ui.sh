#!/usr/bin/env bash
# Fix stuck Home Assistant login / authorize page (logo only, no form).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/docker-compose.test.yml"
STORAGE="${REPO_ROOT}/config/.storage"

echo "==> Stopping homeassistant-test"
docker rm -f homeassistant-test 2>/dev/null || true

echo "==> Clearing stale auth sessions and frontend cache in config/.storage"
python3 << PY
import json
from pathlib import Path

storage = Path("${STORAGE}")

auth_path = storage / "auth"
if auth_path.exists():
    data = json.loads(auth_path.read_text())
    tokens = data.get("data", {}).get("refresh_tokens", [])
    data["data"]["refresh_tokens"] = []
    auth_path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Removed {len(tokens)} refresh tokens from auth")

for name in ("frontend.system_data",):
    p = storage / name
    if p.exists():
        p.unlink()
        print(f"Removed {p.name}")

for p in storage.glob("frontend.user_data_*"):
    p.unlink()
    print(f"Removed {p.name}")
PY

echo "==> Starting homeassistant-test"
cd "${REPO_ROOT}"
docker compose -f "${COMPOSE_FILE}" up -d

echo "==> Waiting for Home Assistant"
for _ in $(seq 1 60); do
  if curl -sf -o /dev/null -w '%{http_code}' http://127.0.0.1:8123/api/ 2>/dev/null | grep -q 401; then
    echo ""
    echo "Home Assistant is ready."
    echo "Open:  http://127.0.0.1:8123"
    echo "Login: test / 230199Bal"
    echo ""
    echo "If the page still shows only the logo:"
    echo "  1. Use http://127.0.0.1:8123 (not localhost)"
    echo "  2. Clear site data for localhost:8123 and 127.0.0.1:8123"
    echo "  3. Or open an Incognito window"
    exit 0
  fi
  sleep 2
done

echo "WARN: HA not ready yet. Check: docker logs homeassistant-test"
exit 1
