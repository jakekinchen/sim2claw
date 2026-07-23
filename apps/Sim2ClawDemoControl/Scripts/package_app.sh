#!/usr/bin/env bash
set -euo pipefail

CONF=${1:-release}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

APP_NAME=Sim2ClawDemoControl
BUNDLE_ID=com.sim2claw.demo-control
MACOS_MIN_VERSION=14.0
source "$ROOT/version.env"

swift build -c "$CONF"
BIN_DIR=$(swift build -c "$CONF" --show-bin-path)
APP="$ROOT/${APP_NAME}.app"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN_DIR/$APP_NAME" "$APP/Contents/MacOS/$APP_NAME"
chmod +x "$APP/Contents/MacOS/$APP_NAME"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>sim2claw Demo Control</string>
  <key>CFBundleDisplayName</key><string>sim2claw Demo Control</string>
  <key>CFBundleIdentifier</key><string>${BUNDLE_ID}</string>
  <key>CFBundleExecutable</key><string>${APP_NAME}</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>${MARKETING_VERSION}</string>
  <key>CFBundleVersion</key><string>${BUILD_NUMBER}</string>
  <key>LSMinimumSystemVersion</key><string>${MACOS_MIN_VERSION}</string>
  <key>NSCameraUsageDescription</key>
  <string>sim2claw records the C922 overhead camera as diagnostic evidence for operator-started robot demonstrations.</string>
  <key>NSAppTransportSecurity</key>
  <dict><key>NSAllowsLocalNetworking</key><true/></dict>
</dict>
</plist>
PLIST

xattr -cr "$APP"
codesign --force --sign - "$APP"
echo "Created $APP"
