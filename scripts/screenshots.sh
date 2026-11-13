#!/bin/bash
# Regenerate the README screenshots (docs/images/*.png) from demo data.
#
# The demo data is computed by the real backend (scripts/demo_data.py) and the
# app's windows are rendered by a test (WeightLogTests/ScreenshotTests.swift)
# in Japanese. Real records are never used.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEMO="$ROOT/app/build/demo"
OUT="$ROOT/docs/images"

uv run --project "$ROOT" python "$ROOT/scripts/demo_data.py" "$DEMO"
cd "$ROOT/app"
xcodegen generate --quiet
TEST_RUNNER_SCREENSHOT_FIXTURES="$DEMO" TEST_RUNNER_SCREENSHOT_OUT="$OUT" \
  xcodebuild -project WeightLog.xcodeproj -scheme WeightLog -derivedDataPath build \
  -testLanguage ja -testRegion JP \
  test -only-testing:WeightLogTests/ScreenshotTests -quiet
ls -1 "$OUT"/*.png
