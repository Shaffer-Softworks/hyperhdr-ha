#!/usr/bin/env bash
# Run Clear Priority E2E tests using the homeassistant-test Docker container.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONTAINER="${HYPERHDR_HA_CONTAINER:-homeassistant-test}"
HYPERHDR_HOST="${HYPERHDR_HOST:-10.12.0.12}"
HYPERHDR_PORT="${HYPERHDR_PORT:-19444}"
PRIORITY="${HYPERHDR_PRIORITY:-128}"

echo "==> Starting ${CONTAINER} (if stopped)"
docker start "${CONTAINER}" >/dev/null 2>&1 || true

echo "==> Waiting for Home Assistant API on :8123"
for _ in $(seq 1 40); do
  if curl -sf -o /dev/null -w '%{http_code}' http://127.0.0.1:8123/api/ 2>/dev/null | grep -q 401; then
    break
  fi
  sleep 2
done

echo "==> Checking integration loaded Clear Priority button"
if ! docker logs "${CONTAINER}" 2>&1 | grep -q 'button.basement_tv_strip_clear_priority'; then
  echo "WARN: button entity not found in logs yet (reload integration or restart HA)"
fi

echo "==> HyperHDR API E2E (set_color -> clear -> LEDDEVICE off)"
docker cp "${REPO_ROOT}/scripts/docker_test_clear_priority.py" "${CONTAINER}:/tmp/docker_test_clear_priority.py"
docker exec "${CONTAINER}" python3 /tmp/docker_test_clear_priority.py \
  --host "${HYPERHDR_HOST}" --port "${HYPERHDR_PORT}" --priority "${PRIORITY}"

echo "==> Done. UI test: Developer Tools -> Services"
echo "    light.turn_off  entity_id: light.basement_tv_strip"
echo "    button.press    entity_id: button.basement_tv_strip_clear_priority"
echo "    Watch logs: docker logs -f ${CONTAINER} 2>&1 | grep -i clear"
