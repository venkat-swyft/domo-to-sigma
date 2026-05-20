#!/usr/bin/env bash
# Exchange SIGMA_CLIENT_ID + SIGMA_CLIENT_SECRET for a short-lived SIGMA_API_TOKEN.
#
# Usage:
#   eval "$(scripts/get-token.sh)"
#
# After eval, $SIGMA_API_TOKEN is set in the current shell (~1h TTL). If you
# capture the output into a variable in a subshell, the export dies with the
# subshell — always use `eval "$(...)"` directly.
#
# Borrowed from twells89/sigma-skills patterns.

set -euo pipefail

: "${SIGMA_BASE_URL:?SIGMA_BASE_URL not set — run setup.py and source ~/.sigma-env}"
: "${SIGMA_CLIENT_ID:?SIGMA_CLIENT_ID not set}"
: "${SIGMA_CLIENT_SECRET:?SIGMA_CLIENT_SECRET not set}"

response=$(curl -sf -X POST \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=${SIGMA_CLIENT_ID}" \
  -d "client_secret=${SIGMA_CLIENT_SECRET}" \
  "${SIGMA_BASE_URL}/v2/auth/token")

token=$(echo "$response" | python -c "import json,sys;print(json.load(sys.stdin)['access_token'])")

if [ -z "$token" ]; then
  echo "echo 'Failed to obtain token. Response: $response' >&2" >&2
  exit 1
fi

echo "export SIGMA_API_TOKEN='${token}'"
