#!/bin/bash
# Set up Grokbot-RedNote on this Mac: write a user LaunchAgent from the
# repo template (no manual path editing) and make sure the local service
# is running on port 18765.
set -euo pipefail

die() {
  echo "install.sh: $*" >&2
  exit 1
}

source="${BASH_SOURCE[0]}"
while [ -L "$source" ]; do
  dir="$(cd -P "$(dirname "$source")" && pwd)"
  source="$(readlink "$source")"
  case "$source" in
    /*) ;;
    *) source="$dir/$source" ;;
  esac
done
ROOT="$(cd -P "$(dirname "$source")" && pwd)"

LABEL="com.drunk.grokbotrednote"
TEMPLATE="$ROOT/launchd/${LABEL}.plist"
SERVICE_SCRIPT="$ROOT/src/grokbot_rednote.py"
DEST="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG="/tmp/grokbot-rednote-service.log"
HEALTH="http://127.0.0.1:18765/health"

[ -f "$SERVICE_SCRIPT" ] || die "cannot find $SERVICE_SCRIPT. Run this script from a complete project checkout."
[ -f "$TEMPLATE" ] || die "cannot find the launchd template at $TEMPLATE."
[ -x /usr/bin/python3 ] || die "/usr/bin/python3 is missing. Install the macOS Command Line Tools (xcode-select --install)."
/usr/bin/python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' \
  || die "/usr/bin/python3 must be Python 3.9 or newer."

command -v curl >/dev/null || die "curl is required to check the service."
command -v launchctl >/dev/null || die "launchctl is required to load the LaunchAgent."

health_ok() {
  curl -fsS --max-time 1 "$HEALTH" >/dev/null 2>&1
}

mkdir -p "$HOME/Library/LaunchAgents"

/usr/bin/python3 - "$TEMPLATE" "$DEST" "$ROOT" <<'PY'
import sys
from pathlib import Path

template, dest, root = sys.argv[1], sys.argv[2], sys.argv[3]
text = Path(template).read_text()
if "PROJECT_DIR" not in text:
    sys.exit("install.sh: launchd template is missing PROJECT_DIR placeholders")
Path(dest).write_text(text.replace("PROJECT_DIR", root))
PY

uid="$(id -u)"
service="gui/${uid}/${LABEL}"
loaded=false
if launchctl print "$service" >/dev/null 2>&1; then
  loaded=true
fi

already_up=false
if health_ok; then
  already_up=true
fi

if "$already_up" && ! "$loaded"; then
  echo "Wrote $DEST."
  echo "The service is already running on port 18765, so the LaunchAgent was not loaded now (that would start a second copy). It will be available at the next login, or after the current service stops."
else
  if "$loaded"; then
    launchctl bootout "$service" 2>/dev/null || true
  fi
  launchctl bootstrap "gui/${uid}" "$DEST" || die "failed to load LaunchAgent ${LABEL}."
fi

if ! health_ok; then
  i=0
  while [ "$i" -lt 40 ]; do
    if health_ok; then
      break
    fi
    i=$((i + 1))
    sleep 0.25
  done
fi

if ! health_ok; then
  die "the service did not respond at ${HEALTH}. Check ${LOG}."
fi

echo "Grokbot-RedNote is installed."
echo "Project directory: $ROOT"
echo "LaunchAgent: $DEST"
echo "Logs: $LOG"
echo "Service: ${HEALTH}"
