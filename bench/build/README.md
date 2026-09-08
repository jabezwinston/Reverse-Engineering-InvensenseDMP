# Prebuilt ESP32 bridge images

Built 2026-09-08 from `bench/esp32_dmp_bridge/esp32_dmp_bridge.ino` with arduino-cli,
core `esp32:esp32` 3.3.11, board `esp32:esp32:esp32` (ESP32 Dev Module, 4 MB flash, dio 80 MHz).
Rebuild with `./bench/flash_bridge.sh` (it compiles into this directory).

## Flash locally

Simplest: the merged image at offset 0 (esptool 5 spelling; esptool 4 uses `write_flash`):

```sh
esptool --chip esp32 -p /dev/ttyUSB0 -b 460800 write-flash 0x0 esp32_dmp_bridge.ino.merged.bin
```

Or the four parts (what the Arduino IDE does):

```sh
esptool --chip esp32 -p /dev/ttyUSB0 -b 460800 write-flash -z --flash-mode dio --flash-freq 80m --flash-size detect \
    0x1000  esp32_dmp_bridge.ino.bootloader.bin \
    0x8000  esp32_dmp_bridge.ino.partitions.bin \
    0xe000  boot_app0.bin \
    0x10000 esp32_dmp_bridge.ino.bin
```

If esptool cannot enter download mode on its own, hold BOOT, tap EN, release BOOT, then run it
with `--before no-reset`.

Verify afterwards (locally or through the tunnel):

```sh
python3 bench/check_link.py --port /dev/ttyUSB0
python3 bench/check_link.py --port rfc2217://localhost:5555
```

Expected: banner `# esp32_dmp_bridge ready` after reset, and `P` -> `OK 68`.

| file | md5 |
|---|---|
| esp32_dmp_bridge.ino.bin | 8eba09dd7a25aa40f2f47c853168120e |
| esp32_dmp_bridge.ino.bootloader.bin | 42863d8b59e70f04bf1f3b0d5aae512e |
| esp32_dmp_bridge.ino.partitions.bin | a039c66cd3488176037b616b7595fe72 |
| esp32_dmp_bridge.ino.merged.bin | 3067b87b483f9ec83224a005d2d96199 |
