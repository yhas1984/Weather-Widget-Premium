#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-6.0.1}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD="${ROOT}/.package-build"
DIST="${ROOT}/dist"
PKG="${BUILD}/weather-widget-premium_${VERSION}_amd64"

rm -rf "${BUILD}"
install -d -m 0755 \
    "${PKG}/DEBIAN" \
    "${PKG}/opt/weather-widget-premium" \
    "${PKG}/usr/bin" \
    "${PKG}/usr/share/applications" \
    "${PKG}/usr/share/doc/weather-widget-premium" \
    "${PKG}/usr/share/icons/hicolor/512x512/apps"

python3 -m PyInstaller --clean --noconfirm --distpath "${DIST}" --workpath "${BUILD}/pyinstaller" "${ROOT}/WeatherWidgetPremium.spec"
install -m 0755 "${DIST}/WeatherWidgetPremium" "${PKG}/opt/weather-widget-premium/WeatherWidgetPremium"
install -m 0644 "${ROOT}/icon-minimal.png" "${PKG}/usr/share/icons/hicolor/512x512/apps/weather-widget-premium.png"

cat > "${PKG}/usr/bin/weather-widget-premium" <<'EOF'
#!/bin/sh
exec /opt/weather-widget-premium/WeatherWidgetPremium "$@"
EOF
chmod 0755 "${PKG}/usr/bin/weather-widget-premium"

cat > "${PKG}/usr/share/applications/weather-widget-premium.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Weather Widget Premium
Comment=Widget meteorológico premium para Linux
Exec=/usr/bin/weather-widget-premium
Icon=weather-widget-premium
Terminal=false
Categories=Utility;
StartupWMClass=WeatherWidgetPremium
EOF
chmod 0644 "${PKG}/usr/share/applications/weather-widget-premium.desktop"

cat > "${PKG}/usr/share/doc/weather-widget-premium/SOURCE.txt" <<EOF
Source repository: https://github.com/yhas1984/Weather-Widget-Premium
Source commit: $(git -C "${ROOT}" rev-parse HEAD)
Package: weather-widget-premium
Version: ${VERSION}
Architecture: amd64
EOF
chmod 0644 "${PKG}/usr/share/doc/weather-widget-premium/SOURCE.txt"

cat > "${PKG}/DEBIAN/control" <<EOF
Package: weather-widget-premium
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: amd64
Maintainer: yhas1984
Homepage: https://github.com/yhas1984/Weather-Widget-Premium
Depends: libxcb-xinerama0, libxcb-cursor0, libegl1, libgl1
Description: Weather Widget Premium
 Desktop weather widget with native X11 and Wayland support using Open-Meteo.
EOF
chmod 0644 "${PKG}/DEBIAN/control"

OUT="${ROOT}/weather-widget-premium_${VERSION}_amd64.deb"
dpkg-deb --build --root-owner-group "${PKG}" "${OUT}"
(cd "${ROOT}" && sha256sum "$(basename "${OUT}")") > "${OUT}.sha256"
dpkg-deb --info "${OUT}"
dpkg-deb --contents "${OUT}" | grep -E 'opt/weather-widget-premium/WeatherWidgetPremium|usr/bin/weather-widget-premium|usr/share/applications|usr/share/icons|SOURCE.txt'
file "${DIST}/WeatherWidgetPremium"
echo "created ${OUT}"
echo "created ${OUT}.sha256"
