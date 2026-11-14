#!/usr/bin/env bash
# Run HDR Tone Mapping Mode E2E (Off/On/Auto) using homeassistant-test + live HyperHDR.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONTAINER="${HYPERHDR_HA_CONTAINER:-homeassistant-test}"
HA_HOST="${HA_HOST:-127.0.0.1}"
HA_PORT="${HA_PORT:-8123}"
HA_USERNAME="${HA_USERNAME:-test}"
HA_PASSWORD="${HA_PASSWORD:?Set HA_PASSWORD (e.g. export HA_PASSWORD=...)}"
HYPERHDR_HOST="${HYPERHDR_HOST:-10.12.0.12}"
HYPERHDR_PORT="${HYPERHDR_PORT:-19444}"
# Prefer explicit env; otherwise read from docker HA config entry (local only).
if [[ -z "${HYPERHDR_ADMIN_PASSWORD:-}" ]]; then
  HYPERHDR_ADMIN_PASSWORD="$(
    python3 - <<PY
import json
from pathlib import Path
entries = json.loads(Path("${REPO_ROOT}/config/.storage/core.config_entries").read_text())
for e in entries["data"]["entries"]:
    if e.get("domain") == "hyperhdr":
        print(e.get("data", {}).get("admin_password") or "")
        break
PY
  )"
fi
if [[ -z "${HYPERHDR_ADMIN_PASSWORD}" ]]; then
  echo "WARN: no HyperHDR admin password; Auto config step may fail if auth is required"
fi

export HA_HOST HA_PORT HA_USERNAME HA_PASSWORD

echo "==> Syncing hyperhdr custom_component into ${CONTAINER}"
docker start "${CONTAINER}" >/dev/null 2>&1 || \
  docker compose -f "${REPO_ROOT}/docker-compose.test.yml" up -d

# Volume mount already maps ./custom_components; still restart so Python reloads modules.
docker cp "${REPO_ROOT}/custom_components/hyperhdr" \
  "${CONTAINER}:/config/custom_components/"
docker cp "${REPO_ROOT}/scripts/docker_test_hdr_mode.py" \
  "${CONTAINER}:/tmp/docker_test_hdr_mode.py"

echo "==> Restart ${CONTAINER} (reload integration code)"
docker restart "${CONTAINER}"

echo "==> Waiting for Home Assistant API on :${HA_PORT}"
for _ in $(seq 1 45); do
  if curl -sf -o /dev/null -w '%{http_code}' "http://${HA_HOST}:${HA_PORT}/api/" 2>/dev/null | grep -q 401; then
    break
  fi
  sleep 2
done

echo "==> Obtaining HA access token for ${HA_USERNAME}"
HA_TOKEN="$(
  python3 <<'PY'
import json, urllib.request, time, os

host, port = os.environ["HA_HOST"], int(os.environ["HA_PORT"])
username, password = os.environ["HA_USERNAME"], os.environ["HA_PASSWORD"]
base = f"http://{host}:{port}"

for _ in range(30):
    try:
        flow = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base}/auth/login_flow",
                    data=json.dumps(
                        {
                            "client_id": "http://localhost/",
                            "handler": ["homeassistant", None],
                            "redirect_uri": "http://localhost/",
                        }
                    ).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                ),
                timeout=5,
            ).read()
        )
        fid = flow["flow_id"]
        step = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base}/auth/login_flow/{fid}",
                    data=json.dumps(
                        {
                            "username": username,
                            "password": password,
                            "client_id": "http://localhost/",
                        }
                    ).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                ),
                timeout=5,
            ).read()
        )
        if step.get("type") != "create_entry":
            raise RuntimeError(f"login failed: {step}")
        code = step["result"]
        token = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base}/auth/token",
                    data=(
                        f"grant_type=authorization_code&code={code}"
                        f"&client_id=http://localhost/"
                    ).encode(),
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    method="POST",
                ),
                timeout=5,
            ).read()
        )
        print(token["access_token"])
        break
    except Exception:
        time.sleep(2)
else:
    raise SystemExit("Could not obtain HA access token")
PY
)"

echo "==> HDR Tone Mapping Mode E2E (API + HA select)"
docker exec \
  -e HYPERHDR_ADMIN_PASSWORD="${HYPERHDR_ADMIN_PASSWORD}" \
  "${CONTAINER}" python3 /tmp/docker_test_hdr_mode.py \
  --ha-host 127.0.0.1 \
  --ha-access-token "${HA_TOKEN}" \
  --hyperhdr-host "${HYPERHDR_HOST}" \
  --hyperhdr-port "${HYPERHDR_PORT}" \
  --admin-password "${HYPERHDR_ADMIN_PASSWORD}"

echo "==> Done."
