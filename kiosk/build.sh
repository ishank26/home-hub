#!/bin/bash
# Build the Home Hub kiosk APK without the Android SDK installer.
#
# Tools: Debian packages openjdk-21-jdk-headless, aapt, zipalign, apksigner, android-framework-res,
# plus Google's open-source d8 (com.android.tools:r8 from Google Maven), pinned by SHA-256.
# Java compiles against the minimal stubs in stubs/ (never packaged); the device supplies the
# real framework. The signing key lives outside Git in ~/.config/home-hub/ and is created on
# first use.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/build"
R8_JAR="${R8_JAR:-$HOME/.local/share/home-hub/tools/r8-8.5.35.jar}"
R8_SHA256=4733945987ee0a840fafc34080b135259e01678412e07212b23f706334290294
FRAMEWORK_RES="${FRAMEWORK_RES:-/usr/share/android-framework-res/framework-res.apk}"
KEY_DIR="$HOME/.config/home-hub"
KEYSTORE="$KEY_DIR/kiosk.jks"
KEYPASS="$KEY_DIR/kiosk.jks.pass"

for tool in javac jar java keytool aapt zipalign apksigner; do
    command -v "$tool" >/dev/null || { echo "missing tool: $tool" >&2; exit 1; }
done
[ -f "$FRAMEWORK_RES" ] || { echo "missing $FRAMEWORK_RES (android-framework-res)" >&2; exit 1; }
echo "$R8_SHA256  $R8_JAR" | sha256sum -c --quiet - || { echo "d8 jar hash mismatch" >&2; exit 1; }
JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"

rm -rf "$OUT"
mkdir -p "$OUT/stubs" "$OUT/classes" "$OUT/dex"

javac -nowarn --release 8 -d "$OUT/stubs" $(find "$HERE/stubs" -name '*.java')
jar cf "$OUT/stubs.jar" -C "$OUT/stubs" .
javac --release 8 -Xlint:-options -cp "$OUT/stubs.jar" -d "$OUT/classes" $(find "$HERE/src" -name '*.java')

java -cp "$R8_JAR" com.android.tools.r8.D8 --release --min-api 23 \
    --lib "$JAVA_HOME" --classpath "$OUT/stubs.jar" --output "$OUT/dex" \
    $(find "$OUT/classes" -name '*.class')

aapt package -f -M "$HERE/AndroidManifest.xml" -I "$FRAMEWORK_RES" \
    --min-sdk-version 23 --target-sdk-version 23 -F "$OUT/unsigned.apk"
(cd "$OUT/dex" && aapt add "$OUT/unsigned.apk" classes.dex >/dev/null)
zipalign -f -p 4 "$OUT/unsigned.apk" "$OUT/aligned.apk"

if [ ! -f "$KEYSTORE" ]; then
    mkdir -p "$KEY_DIR" && chmod 700 "$KEY_DIR"
    (umask 077 && head -c 24 /dev/urandom | base64 > "$KEYPASS")
    keytool -genkeypair -keystore "$KEYSTORE" -storepass:file "$KEYPASS" -keypass:file "$KEYPASS" \
        -alias kiosk -keyalg RSA -keysize 3072 -validity 10000 -dname "CN=Home Hub kiosk" >/dev/null
    chmod 600 "$KEYSTORE"
fi
apksigner sign --ks "$KEYSTORE" --ks-pass "file:$KEYPASS" --ks-key-alias kiosk \
    --min-sdk-version 23 --out "$OUT/home-hub-kiosk.apk" "$OUT/aligned.apk"
apksigner verify --min-sdk-version 23 "$OUT/home-hub-kiosk.apk"
rm -f "$OUT/unsigned.apk" "$OUT/aligned.apk" "$OUT"/*.idsig
ls -l "$OUT/home-hub-kiosk.apk"
sha256sum "$OUT/home-hub-kiosk.apk"
