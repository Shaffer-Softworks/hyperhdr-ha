#!/usr/bin/env bash
# Rebuild/recreate homeassistant-test with fresh image pull and reset HA login.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/docker-compose.test.yml"
HA_USERNAME="${HA_USERNAME:-test}"
HA_PASSWORD="${HA_PASSWORD:-230199Bal}"

cd "${REPO_ROOT}"

echo "==> Pulling Home Assistant image"
docker compose -f "${COMPOSE_FILE}" pull

echo "==> Stopping and removing homeassistant-test container"
docker rm -f homeassistant-test 2>/dev/null || true
docker compose -f "${COMPOSE_FILE}" down --remove-orphans 2>/dev/null || true

echo "==> Resetting HA login for user: ${HA_USERNAME}"
export HA_PASSWORD
PASSWORD_HASH="$(
  python3 << PY
import base64, bcrypt, os
password = os.environ["HA_PASSWORD"]
encoded = base64.b64encode(bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12))).decode()
print(encoded)
PY
)"

python3 << PY
import json
from pathlib import Path

config = Path("${REPO_ROOT}/config/.storage")
provider_path = config / "auth_provider.homeassistant"
data = {
    "version": 1,
    "minor_version": 1,
    "key": "auth_provider.homeassistant",
    "data": {
        "users": [
            {
                "username": "${HA_USERNAME}",
                "password": "${PASSWORD_HASH}",
            }
        ]
    },
}
provider_path.write_text(json.dumps(data, indent=2) + "\n")
print(f"Updated {provider_path}")
PY

echo "==> Starting homeassistant-test"
docker compose -f "${COMPOSE_FILE}" up -d

echo "==> Waiting for Home Assistant on http://127.0.0.1:8123"
for _ in $(seq 1 45); do
  if curl -sf -o /dev/null -w '%{http_code}' http://127.0.0.1:8123/api/ 2>/dev/null | grep -q 401; then
  echo "Home Assistant is ready."
  echo "Login: ${HA_USERNAME} / ${HA_PASSWORD}"
  echo "URL:   http://127.0.0.1:8123"
  exit 0
  fi
  sleep 2
done

echo "WARN: Home Assistant did not respond on :8123 yet. Check: docker logs homeassistant-test"
exit 1
