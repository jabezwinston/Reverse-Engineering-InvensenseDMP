#!/usr/bin/env bash
# Build esp32_dmp_bridge.ino here and flash it to the ESP32 at a local device or a pyserial
# URL (rfc2217://localhost:5555 through the reverse tunnel, see REMOTE_SERIAL.md).
#
#   ./bench/flash_bridge.sh rfc2217://localhost:5555
#   BAUD=115200 ./bench/flash_bridge.sh /dev/ttyUSB0
#
# Needs arduino-cli with the esp32:esp32 core, and esptool (uv tool install esptool).
set -euo pipefail
PORT="${1:?usage: flash_bridge.sh <port-or-url>}"
BAUD="${BAUD:-230400}"
FQBN="${FQBN:-esp32:esp32:esp32}"
HERE="$(cd "$(dirname "$0")" && pwd)"
SKETCH="$HERE/esp32_dmp_bridge"
OUT="$HERE/build"
export PATH="$HOME/.local/bin:$PATH"

command -v arduino-cli >/dev/null || { echo "arduino-cli not found (expected in ~/.local/bin)"; exit 1; }
command -v esptool >/dev/null || { echo "esptool not found: uv tool install esptool"; exit 1; }

echo "== compiling $SKETCH for $FQBN"
arduino-cli compile --fqbn "$FQBN" --output-dir "$OUT" "$SKETCH"
MERGED="$OUT/esp32_dmp_bridge.ino.merged.bin"
if [ ! -f "$MERGED" ]; then
  echo "no merged image; flashing the four parts instead"
  CORE_DIR="$(arduino-cli config get directories.data)/packages/esp32/hardware/esp32"
  BOOT_APP0="$(ls "$CORE_DIR"/*/tools/partitions/boot_app0.bin | head -1)"
  set -x
  esptool --chip esp32 --port "$PORT" --baud "$BAUD" --before default_reset --after hard_reset \
      write-flash -z --flash-mode dio --flash-freq 80m --flash-size detect \
      0x1000  "$OUT/esp32_dmp_bridge.ino.bootloader.bin" \
      0x8000  "$OUT/esp32_dmp_bridge.ino.partitions.bin" \
      0xe000  "$BOOT_APP0" \
      0x10000 "$OUT/esp32_dmp_bridge.ino.bin"
  exit
fi
echo "== flashing $MERGED to $PORT at $BAUD baud"
esptool --chip esp32 --port "$PORT" --baud "$BAUD" --before default_reset --after hard_reset \
    write-flash -z 0x0 "$MERGED"
echo "== done; verify with:  python3 $HERE/check_link.py --port $PORT"
