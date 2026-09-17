#!/usr/bin/env bash
# Report a delivery's outcome to transom from a child process the runner
# started with `completion = "child"` (see config.example.toml): the runner
# itself only reports "queued", and whatever the command launched (a Claude
# session, a long import) calls this once when it is done.
#
#   report-result.sh done   "Created Work/Meetings/2026/Q3/2026-09-09 - Standup.md and logged it"
#   report-result.sh failed "The repo had uncommitted changes I did not want to touch"
#
# Where the callback lives: either PB_RESULT_FILE (a 0600 JSON file with
# {"url": ..., "token": ...}, written by the launcher so the token never sits
# in a process environment) or PB_RESULT_URL + PB_RESULT_TOKEN in the env
# (what the runner hands the command). A 2xx or a 409 (already reported) ends
# the job's reporting and removes the file; anything else leaves it so the
# call can be repeated.
set -uo pipefail

status="${1:-}"
shift || true
summary="$*"
case "$status" in
  done|failed) ;;
  *) echo "usage: report-result.sh done|failed \"<what happened, where the result is>\"" >&2; exit 2 ;;
esac
if [ -z "${summary//[[:space:]]/}" ]; then
  echo "report-result.sh: a summary is required" >&2
  exit 2
fi

url="${PB_RESULT_URL:-}"
token="${PB_RESULT_TOKEN:-}"
file="${PB_RESULT_FILE:-}"
if [ -n "$file" ] && [ -f "$file" ]; then
  url="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("url",""))' "$file")"
  token="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("token",""))' "$file")"
fi
if [ -z "$url" ] || [ -z "$token" ]; then
  echo "report-result.sh: no result callback (PB_RESULT_FILE or PB_RESULT_URL/PB_RESULT_TOKEN)" >&2
  exit 3
fi

# Body via python so quotes and newlines in the summary are encoded correctly; the summary
# is cut to what the bridge accepts. The token goes over the wire only, never into argv.
code="$(
  PB_RR_URL="$url" PB_RR_TOKEN="$token" PB_RR_STATUS="$status" PB_RR_SUMMARY="$summary" python3 - <<'PY'
import json, os, sys, urllib.request, urllib.error
body = json.dumps({"status": os.environ["PB_RR_STATUS"], "summary": " ".join(os.environ["PB_RR_SUMMARY"].split())[:2000]}).encode()
req = urllib.request.Request(os.environ["PB_RR_URL"], data=body, method="POST",
                             headers={"Authorization": "Bearer " + os.environ["PB_RR_TOKEN"], "Content-Type": "application/json"})
class NoRedirect(urllib.request.HTTPRedirectHandler):
    # Never follow a 3xx: it would carry the delivery token to whatever host the redirect names.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None
opener = urllib.request.build_opener(NoRedirect)
try:
    with opener.open(req, timeout=15) as r:
        print(r.status)
except urllib.error.HTTPError as e:
    print(e.code)
except Exception as e:
    print("error", str(e)[:200], file=sys.stderr)
    print(0)
PY
)"
case "$code" in
  2*|409)
    [ -n "$file" ] && rm -f "$file"
    echo "Reported '$status' to transom (HTTP $code)"
    ;;
  *)
    echo "report-result.sh: transom answered HTTP $code; not reported, try again" >&2
    exit 1
    ;;
esac
