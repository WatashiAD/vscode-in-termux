#!/usr/bin/env bash
set -euo pipefail

PREFIX="${CODIUM_PREFIX:-/usr/local}"
SERVER_HOME="${CODIUM_SERVER_HOME:-/opt/openvscode-server}"
VERSION="${CODIUM_SERVER_VERSION:-1.109.5}"
SRC="$(cd "$(dirname "$0")" && pwd)"

if [ "$(id -u)" != "0" ] && [ ! -w "$(dirname "$SERVER_HOME")" ]; then
	echo "codium: run as root (or set CODIUM_SERVER_HOME to a writable path)" >&2
	exit 1
fi

case "$(uname -m)" in
aarch64 | arm64) ARCH=arm64 ;;
x86_64 | amd64) ARCH=x64 ;;
armv7l | armv8l) ARCH=armhf ;;
*)
	echo "codium: unsupported architecture: $(uname -m)" >&2
	exit 1
;;
esac

command -v python3 >/dev/null || {
	echo "codium: python3 is required" >&2
	exit 1
}

TARBALL="openvscode-server-v${VERSION}-linux-${ARCH}.tar.gz"
URL="https://github.com/gitpod-io/openvscode-server/releases/download/openvscode-server-v${VERSION}/${TARBALL}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "codium: downloading $URL"
if command -v curl >/dev/null; then
	curl -fL "$URL" -o "$TMP/$TARBALL"
elif command -v wget >/dev/null; then
	wget -qO "$TMP/$TARBALL" "$URL"
else
	echo "codium: need curl or wget to download the server" >&2
	exit 1
fi

mkdir -p "$SERVER_HOME"
tar -xzf "$TMP/$TARBALL" -C "$SERVER_HOME" --strip-components=1
cp "$SERVER_HOME/product.json" "$SERVER_HOME/product.json.orig"

python3 - "$SERVER_HOME/product.json" <<'PY'
import json
import sys

p = sys.argv[1]
with open(p, encoding="utf8") as f:
    d = json.load(f)
d["nameShort"] = "VSCodium"
d["nameLong"] = "VSCodium"
d["applicationName"] = "codium"
d["dataFolderName"] = ".codium"
d["checkForCodiumExtension"] = True
d["telemetryLevel"] = None
with open(p, "w", encoding="utf8") as f:
    f.write(json.dumps(d, indent=4))
PY

install -d "$PREFIX/bin" "$PREFIX/lib/codium"
install -m 0755 "$SRC/bin/codium" "$PREFIX/bin/codium"
install -m 0755 "$SRC/lib/picker.py" "$SRC/lib/serve" "$PREFIX/lib/codium/"

if [ "$PREFIX" != "/usr/local" ]; then
	sed -i "s|/usr/local/lib/codium|$PREFIX/lib/codium|g" "$PREFIX/bin/codium" "$PREFIX/lib/codium/serve"
	sed -i "s|/usr/local/bin/codium|$PREFIX/bin/codium|g" "$PREFIX/bin/codium"
fi

SETTINGS="$HOME/.codium/User/settings.json"
if [ ! -f "$SETTINGS" ]; then
	mkdir -p "$(dirname "$SETTINGS")"
	cp "$SRC/config/settings.json" "$SETTINGS"
fi

echo "codium: installed"
echo "  server : $SERVER_HOME (v${VERSION}, VSCodium branding applied)"
echo "  command: $PREFIX/bin/codium"
