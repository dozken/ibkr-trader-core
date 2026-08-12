#!/bin/sh
# Emit runtime config for the SPA, then hand off to nginx.
#
# The API key used to be a Vite build ARG, which compiled it into the hashed JS
# bundle — so the published ghcr image contained a live credential and rotating
# the key meant rebuilding and republishing the image. Writing it here instead
# keeps the artifact clean and makes rotation a restart.
#
# This does NOT make the key confidential: the browser still receives it, so it
# is an origin guard rather than a secret. It is only kept out of the image.
set -eu

CONFIG=/usr/share/nginx/html/config.js

# JSON-escape: backslash first, then quote; drop any newline that would break
# out of the string literal.
escaped=$(printf '%s' "${IBKR_API_KEY:-}" \
  | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' \
  | tr -d '\n\r')

printf 'window.__APP_CONFIG__ = { apiKey: "%s" };\n' "$escaped" > "$CONFIG"

if [ -z "${IBKR_API_KEY:-}" ]; then
  echo "frontend: IBKR_API_KEY is empty — privileged API calls will be rejected" >&2
else
  echo "frontend: runtime config written (${#escaped} char key)" >&2
fi

exec "$@"
