#!/bin/sh
set -eu
. "$(dirname "$0")/env.sh"
cd "$PROJECT_ROOT"
APP="ProtoMind Lab.app"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources" .cache/swift .cache/clang
export CLANG_MODULE_CACHE_PATH="$PROJECT_ROOT/.cache/clang"
export SWIFT_MODULECACHE_PATH="$PROJECT_ROOT/.cache/swift"
xcrun swiftc desktop/main.swift -o "$APP/Contents/MacOS/ProtoMindLab" -framework Cocoa -framework WebKit -module-cache-path "$SWIFT_MODULECACHE_PATH" -O
cp assets/ProtoMind.icns "$APP/Contents/Resources/ProtoMind.icns"
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd"><plist version="1.0"><dict><key>CFBundleName</key><string>ProtoMind Lab</string><key>CFBundleDisplayName</key><string>ProtoMind Lab</string><key>CFBundleIdentifier</key><string>org.protomind.lab</string><key>CFBundleVersion</key><string>2</string><key>CFBundleShortVersionString</key><string>0.2.0</string><key>CFBundleExecutable</key><string>ProtoMindLab</string><key>CFBundleIconFile</key><string>ProtoMind</string><key>CFBundlePackageType</key><string>APPL</string><key>NSHighResolutionCapable</key><true/><key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict></dict></plist>
PLIST
codesign --force --sign - "$APP"
printf '%s\n' "Built project-local $APP (ad-hoc signed, not notarized)."
