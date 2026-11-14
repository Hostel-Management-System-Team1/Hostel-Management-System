#!/usr/bin/env bash
# Post-deployment smoke test: is the application up and serving what it should?
#
#   .github/scripts/smoke_test.sh http://127.0.0.1:8000
#
# Writes a Markdown table to $GITHUB_STEP_SUMMARY (or the console) and exits 1 if any check fails.
set -u
BASE="${1:?usage: smoke_test.sh BASE_URL}"
FAILED=0
ROWS=""

check() { # name, expected, actual
  local ok="✅"
  if [ "$2" != "$3" ]; then ok="❌"; FAILED=1; fi
  ROWS+="| $1 | $2 | $3 | $ok |"$'\n'
}

status() { curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE$1"; }
header() { curl -sI --max-time 10 "$BASE$1" | tr -d '\r' | grep -i "^$2:" | head -1 | cut -d: -f1 | tr 'A-Z' 'a-z'; }

check "Sign-in page loads (GET /accounts/login/)" 200 "$(status /accounts/login/)"
check "Anonymous API call is refused (GET /api/v1/applications)" 403 "$(status /api/v1/applications)"
check "Admin site redirects an anonymous visitor (GET /admin/)" 302 "$(status /admin/)"
check "Content-Security-Policy header is sent" content-security-policy "$(header /accounts/login/ content-security-policy)"
check "X-Frame-Options header is sent" x-frame-options "$(header /accounts/login/ x-frame-options)"

REPORT="### Smoke test of $BASE"$'\n\n'"| Check | Expected | Got | |"$'\n'"|---|---|---|---|"$'\n'"$ROWS"
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then printf '%s\n' "$REPORT" >> "$GITHUB_STEP_SUMMARY"; else printf '%s\n' "$REPORT"; fi
[ "$FAILED" -eq 0 ] || { echo "::error::Smoke test failed"; exit 1; }
