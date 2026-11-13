#!/bin/bash
# Manage the s200 LaunchAgent (records weigh-ins in the background, starts at login).
#
#   scripts/launchd.sh install     render the plist for this checkout and start it
#   scripts/launchd.sh restart     restart after code or config changes
#   scripts/launchd.sh uninstall   stop it and remove the plist
#   scripts/launchd.sh status      show whether it is running
#   scripts/launchd.sh render      print the rendered plist (no changes)
set -euo pipefail

LABEL=com.user.s200
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TEMPLATE="$PROJECT_DIR/launchd/$LABEL.plist.template"
TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

render() {
  sed "s|__PROJECT_DIR__|$PROJECT_DIR|g" "$TEMPLATE"
}

case "${1:-}" in
  render)
    render
    ;;
  install)
    [[ -x "$PROJECT_DIR/.venv/bin/s200" ]] || { echo "先に uv sync を実行してください" >&2; exit 1; }
    [[ -f "$PROJECT_DIR/config.toml" ]] || { echo "config.toml がありません（config.example.toml をコピー）" >&2; exit 1; }
    mkdir -p "$PROJECT_DIR/logs" "$(dirname "$TARGET")"
    render > "$TARGET"
    plutil -lint -s "$TARGET"
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    launchctl bootstrap "$DOMAIN" "$TARGET"
    echo "installed: $TARGET"
    echo "log: tail -f $PROJECT_DIR/logs/s200.log"
    ;;
  restart)
    launchctl kickstart -k "$DOMAIN/$LABEL"
    ;;
  uninstall)
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    rm -f "$TARGET"
    echo "removed: $TARGET"
    ;;
  status)
    launchctl print "$DOMAIN/$LABEL" 2>/dev/null | grep -E "^\s+(state|pid|last exit code) =" || echo "not installed"
    ;;
  *)
    sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac
