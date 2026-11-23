#!/usr/bin/env bash
set -euo pipefail

case "${1:-}" in
    0|1) state="$1" ;;
    *) printf 'Usage: bash %s 0|1\n' "$0" >&2; exit 2 ;;
esac

env_file="$(dirname -- "${BASH_SOURCE[0]}")/../.env"
if [[ -z "${THINGSBOARD_API_KEY:-}" && -r "$env_file" ]]; then
    THINGSBOARD_API_KEY="$(sed -nE "s/^[[:blank:]]*(export[[:blank:]]+)?THINGSBOARD_API_KEY[[:blank:]]*=[[:blank:]]*(['\"]?)([A-Za-z0-9_-]*)\\2([[:blank:]]+#.*)?[[:space:]]*$/\\3/p" "$env_file" | tail -n 1)"
fi
: "${THINGSBOARD_API_KEY:?Set THINGSBOARD_API_KEY in the environment or the repository .env}"

while read -r device_id command appliance; do
    printf 'X-Authorization: ApiKey %s\n' "$THINGSBOARD_API_KEY" |
        curl --silent --show-error --fail --max-time 15 \
            --header @- --header 'Content-Type: application/json' \
            --data "{\"method\":\"$command\",\"params\":$state}" \
            --output /dev/null "https://codehelpers.tech/api/rpc/oneway/$device_id"
    printf 'Submitted %s %s for %s\n' "$command" "$state" "$appliance"
done <<'DEVICES'
f45b5270-e64a-11f1-8712-afcc819282f5 POWER1 living room lamp
f45b5270-e64a-11f1-8712-afcc819282f5 POWER2 kitchen light
f2eb95d0-e64a-11f1-8712-afcc819282f5 POWER1 bathroom fan
f49d3d70-e64a-11f1-8712-afcc819282f5 POWER1 bedroom 1 fan
25816d40-e64f-11f1-8712-afcc819282f5 POWER1 bedroom 2 light
DEVICES
