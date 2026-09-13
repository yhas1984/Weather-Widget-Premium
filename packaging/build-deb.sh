#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-6.0.0}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD="${ROOT}/.package-build"
DIST="${ROOT}/dist"
PKG="${BUILD}/weather-widget_${VERSION}_amd64"

rm -rf "${BUILD}"
mkdir -p "${PKG}/DEBIAN" "${PKG}/opt/weather-widget" "${PKG}/usr/bin" "${PKG}/usr/share/applications" "${PKG}/usr/share/doc/weather-widget"

python3 -m PyInstaller --clean --noconfirm --distpath "${DIST}" --workpath "${BUILD}/pyinstaller" "${ROOT}/WeatherWidget.spec"
install -m 0755 "${DIST}/WeatherWidget" "${PKG}/opt/weather-widget/WeatherWidget"

cat > "${PKG}/usr/bin/weather-widget" <<'EOF'
#!/bin/sh
exec /opt/weather-widget/WeatherWidget "$@"
EOF
chmod 0755 "${PKG}/usr/bin/weather-widget"

cat > "${PKG}/usr/share/applications/weather-widget.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Weather Widget
Comment=Weather Widget V6 premium para Linux
Exec=/usr/bin/weather-widget
Terminal=false
Categories=Utility;
EOF

cat > "${PKG}/usr/share/doc/weather-widget/SOURCE.txt" <<EOF
Source repository: https://github.com/yhas1984/Weather-Widget
Source commit: $(git -C "${ROOT}" rev-parse HEAD)
Package: weather-widget
Version: ${VERSION}
Architecture: amd64
EOF

cat > "${PKG}/DEBIAN/control" <<EOF
Package: weather-widget
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: amd64
Maintainer: yhas1984
Depends: libxcb-xinerama0
Description: Weather Widget V6 premium
 Desktop weather widget with native X11 and Wayland support using Open-Meteo.
EOF

OUT="${ROOT}/weather-widget_${VERSION}_amd64.deb"
dpkg-deb --build --root-owner-group "${PKG}" "${OUT}"
dpkg-deb --info "${OUT}"
dpkg-deb --contents "${OUT}" | grep -E 'opt/weather-widget/WeatherWidget|usr/bin/weather-widget|usr/share/applications|SOURCE.txt'
file "${DIST}/WeatherWidget"
echo "created ${OUT}"
