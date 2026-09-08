# Reaching the ESP32 rig from this machine

The ESP32 + MPU-6050 are plugged into **your laptop**; this box (`100.78.26.14`) has no
`/dev/ttyUSB*`. Same arrangement as `~/bk3296/doc/REMOTE_SERIAL.md`, and the same fix: share
the port with RFC2217 on the laptop and pull it here through an SSH **reverse** tunnel. Inbound
connections to the laptop do not work on this tailnet (measured 2026-09-07), and a reverse
tunnel can only be requested by the SSH client, so the two commands below are yours to run.

RFC2217 rather than a plain socket because it carries **DTR/RTS**: the bench resets the ESP32
through those lines, and `esptool` needs them to enter the bootloader for flashing.

## On your laptop (two terminals, leave both running)

```sh
pip install pyserial                                           # once
scp js@100.78.26.14:InvensenseDMP/bench/rfc2217_server.py .   # once (same file as bk3296's)
python3 rfc2217_server.py -p 5555 /dev/ttyUSB0                 # macOS: /dev/tty.usbserial-*
```

```sh
ssh -N -R 5555:localhost:5555 js@100.78.26.14
```

(Or add the forward to the session you already have: Enter, `~C`, then `-R 5555:localhost:5555`.)

## Here

```sh
python3 bench/check_link.py --port rfc2217://localhost:5555     # tunnel -> server -> banner -> WHO_AM_I
./bench/flash_bridge.sh rfc2217://localhost:5555               # only if the ESP32 is not running the bridge
python3 bench/isa_probe.py --port rfc2217://localhost:5555 store
python3 bench/isa_probe.py --port rfc2217://localhost:5555 optable
```

Every bench tool takes `--port` as a device path **or** a pyserial URL; `Bridge` opens it with
`serial_for_url`, so nothing else changes.

## Flashing over the tunnel

`flash_bridge.sh` compiles `esp32_dmp_bridge.ino` here with `arduino-cli` (core `esp32:esp32`,
board `esp32:esp32:esp32`) into a single merged image and writes it with `esptool` at the
URL. The ESP32 dev board's auto-reset circuit (DTR -> IO0, RTS -> EN) is driven through
RFC2217, so no button pressing is needed; if the server on the laptop cannot drive modem lines,
hold BOOT while the script says "Connecting...". Flash speed is limited by the tunnel; the
script uses 230400 baud by default (`BAUD=115200 ./bench/flash_bridge.sh ...` if it stalls).

## Port already in use

5555 is free here (bk3296's fake-module test server holds 5599). If you pick another port,
change it in all three places: server, tunnel, `--port`.

## Wiring reminder (as built)

SDA = D21, SCL = D22, MPU INT = D5, MPU-6050 at I2C 0x68, powered from the ESP32's 3V3.
