// esp32_dmp_bridge - dumb I2C bridge to an MPU-6050 or ICM-20948 for DMP experiments.
//
// Wiring (as built):  SDA = D21, SCL = D22, INT (MPU INT / ICM INT1) = D5, FSYNC = D4 (driven)
//
// The part is auto-detected at boot (0x68 then 0x69; WHO_AM_I 0xEA at reg 0 = ICM-20948,
// 0x68/0x70/0x71/0x73 at reg 0x75 = MPU). The banner reports "# part <mpu|icm> addr <hex>".
// The two parts differ only in register addresses and the DMP-memory burst limit, which
// the profile table below hides from the host; the command set is the same.
//
// The ESP32 does no experiment logic; it only exposes register and DMP-memory
// access over serial so the host can iterate without reflashing.
//
// Line protocol, ASCII, one command per line, reply prefixed OK/ERR:
//   P                        ping        -> "OK <WHO_AM_I>"
//   G <reg> <len>            read regs   -> "OK <hex>"
//   S <reg> <hex>            write regs  -> "OK"
//   M <bank> <addr> <len>    read DMP    -> "OK <hex>"       (len <= 128)
//   N <bank> <addr> <hex>    write DMP   -> "OK"
//   F                        FIFO count  -> "OK <count>"
//   R <len>                  read FIFO   -> "OK <hex>"
//   I                        INT state   -> "OK <level> <count>"
//   Z                        clear INT counter -> "OK"
//   A <addr>                 set I2C address (hex)  -> "OK"
//   X                        scan the bus -> "OK <addr>..."  (7-bit addresses, hex)
//   K [mpu|icm]              select/report part profile -> "OK <part> <addr>"
//   Y <0|1>                  drive the FSYNC pin (D4) low/high -> "OK <level>"; Y alone reads it
//   T <ms>                   single step: reset+start DMP, wait for one INT edge (or
//                            <ms> timeout), stop DMP  -> "OK <ints> <elapsed_us>"
//                            (host-side stepping over a slow link runs many samples)
//
// ICM-20948 notes: M/N/T/F/R/P assume register bank 0 and re-select it themselves
// (REG_BANK_SEL 0x7f); a host that used G/S in another bank need not restore it. DMP
// memory is accessed through MEM_BANK_SEL/MEM_START_ADDR/MEM_R_W (0x7e/0x7c/0x7d) in
// bursts of at most 16 bytes that never cross a 256-byte page, exactly as the vendor
// driver does; M/N split longer requests. The T command starts the DMP with
// USER_CTRL = FIFO_EN|DMP_RST (0x48) rather than the MPU's 0x4c, because bit 2 is
// SRAM_RST on the ICM, not FIFO_RESET.

#include <Wire.h>

static const uint8_t SDA_PIN = 21, SCL_PIN = 22, INT_PIN = 5, FSYNC_PIN = 4;
static uint8_t MPU = 0x68;               // current I2C address (A command / autodetect)

// Everything that differs between the two parts.
struct Part {
  const char *name;
  uint8_t who_reg, pwr1, user_ctrl, bank_sel, mem_start, mem_rw, fifo_cnt, fifo_rw;
  uint8_t chunk;        // largest DMP-memory burst
  bool    regbank;      // has REG_BANK_SEL at 0x7f (ICM)
  uint8_t t_reset;      // USER_CTRL value that resets the DMP+FIFO in the T command
};
static const Part PART_MPU = { "mpu", 0x75, 0x6B, 0x6A, 0x6D, 0x6E, 0x6F, 0x72, 0x74, 128, false, 0x4C };
static const Part PART_ICM = { "icm", 0x00, 0x06, 0x03, 0x7E, 0x7C, 0x7D, 0x70, 0x72,  16, true,  0x48 };
static const Part *part = &PART_MPU;
static const uint8_t RA_REG_BANK_SEL = 0x7F;   // ICM only

volatile uint32_t intCount = 0;
void IRAM_ATTR onInt() { intCount++; }

static bool wrReg(uint8_t reg, const uint8_t *d, size_t n) {
  Wire.beginTransmission(MPU);
  Wire.write(reg);
  for (size_t i = 0; i < n; i++) Wire.write(d[i]);
  return Wire.endTransmission() == 0;
}
static bool wr1(uint8_t reg, uint8_t v) { return wrReg(reg, &v, 1); }

static bool rdReg(uint8_t reg, uint8_t *d, size_t n) {
  Wire.beginTransmission(MPU);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  size_t got = Wire.requestFrom((int)MPU, (int)n, (int)true);
  if (got != n) return false;
  for (size_t i = 0; i < n; i++) d[i] = Wire.read();
  return true;
}

// ICM: user registers live in four banks selected by REG_BANK_SEL; everything the
// bridge touches itself is in bank 0.
static bool bank0() { return !part->regbank || wr1(RA_REG_BANK_SEL, 0x00); }

// DMP memory is paged: bank select, then byte address within the 256-byte page.
// Each burst is at most part->chunk bytes and never crosses a page (the ICM requires
// both; the MPU tolerates 128-byte bursts within a page).
static bool memSeek(uint8_t bank, uint8_t addr) {
  return bank0() && wr1(part->bank_sel, part->regbank ? bank : (bank & 0x1F)) && wr1(part->mem_start, addr);
}
static bool memXfer(uint8_t bank, uint8_t addr, uint8_t *d, size_t n, bool write) {
  unsigned a = bank * 256u + addr;
  while (n) {
    size_t k = n < part->chunk ? n : part->chunk;
    if ((a & 0xFF) + k > 0x100) k = 0x100 - (a & 0xFF);
    if (!memSeek(a >> 8, a & 0xFF)) return false;
    if (write ? !wrReg(part->mem_rw, d, k) : !rdReg(part->mem_rw, d, k)) return false;
    a += k; d += k; n -= k;
  }
  return true;
}
static bool memRead(uint8_t bank, uint8_t addr, uint8_t *d, size_t n)        { return memXfer(bank, addr, d, n, false); }
static bool memWrite(uint8_t bank, uint8_t addr, const uint8_t *d, size_t n) { return memXfer(bank, addr, (uint8_t *)d, n, true); }

// Probe one address for either part. Returns the profile or NULL. The MPU test comes
// first because the ICM test has to write REG_BANK_SEL (0x7f): the ICM's register bank
// survives an ESP32 reset, and WHO_AM_I is only at reg 0 in bank 0.
static const Part *identify(uint8_t addr) {
  uint8_t w = 0, saved = MPU;
  MPU = addr;
  const Part *found = NULL;
  if (rdReg(0x75, &w, 1) && (w == 0x68 || w == 0x70 || w == 0x71 || w == 0x73)) found = &PART_MPU;
  else if (wr1(RA_REG_BANK_SEL, 0x00) && rdReg(0x00, &w, 1) && w == 0xEA) found = &PART_ICM;
  MPU = saved;
  return found;
}

static int hexNib(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}
static size_t parseHex(const char *s, uint8_t *out, size_t cap) {
  size_t n = 0;
  while (*s && n < cap) {
    while (*s == ' ') s++;
    int hi = hexNib(*s), lo = hexNib(*(s + 1));
    if (hi < 0 || lo < 0) break;
    out[n++] = (hi << 4) | lo;
    s += 2;
  }
  return n;
}
static void emitHex(const uint8_t *d, size_t n) {
  for (size_t i = 0; i < n; i++) {
    if (d[i] < 16) Serial.print('0');
    Serial.print(d[i], HEX);
  }
}

// An aborted I2C transaction can leave the slave holding SDA low, which wedges
// the bus and blocks Wire.begin()/endTransmission(). Clock SCL until the slave
// releases SDA, then issue a STOP.
static void i2cRecover() {
  pinMode(SDA_PIN, INPUT_PULLUP);
  pinMode(SCL_PIN, OUTPUT);
  for (int i = 0; i < 9 && digitalRead(SDA_PIN) == LOW; i++) {
    digitalWrite(SCL_PIN, LOW);  delayMicroseconds(5);
    digitalWrite(SCL_PIN, HIGH); delayMicroseconds(5);
  }
  // manual STOP: SDA low->high while SCL high
  pinMode(SDA_PIN, OUTPUT);
  digitalWrite(SDA_PIN, LOW);  delayMicroseconds(5);
  digitalWrite(SCL_PIN, HIGH); delayMicroseconds(5);
  digitalWrite(SDA_PIN, HIGH); delayMicroseconds(5);
  pinMode(SDA_PIN, INPUT_PULLUP);
  pinMode(SCL_PIN, INPUT_PULLUP);
}

void setup() {
  Serial.begin(115200);
  delay(50);
  // Banner first: the host must be able to sync even if the bus is wedged.
  Serial.println("# esp32_dmp_bridge ready");

  i2cRecover();
  Wire.begin(SDA_PIN, SCL_PIN, 400000);
  Wire.setTimeOut(50);                   // never block the command loop
  pinMode(INT_PIN, INPUT);
  attachInterrupt(digitalPinToInterrupt(INT_PIN), onInt, RISING);
  pinMode(FSYNC_PIN, OUTPUT); digitalWrite(FSYNC_PIN, LOW);

  for (uint8_t a : {0x68, 0x69}) {
    const Part *p = identify(a);
    if (p) { part = p; MPU = a; break; }
  }
  bank0();
  wr1(part->pwr1, 0x80);                 // device reset
  delay(100);
  bank0();
  wr1(part->pwr1, 0x01);                 // wake, clock = PLL/gyro-X (MPU) / auto (ICM)
  delay(20);
  Serial.print("# part "); Serial.print(part->name);
  Serial.print(" addr "); Serial.println(MPU, HEX);
  Serial.println("# i2c init done");
}

void loop() {
  static char line[600];
  static size_t len = 0;
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (!len) continue;
      line[len] = 0;
      handle(line);
      len = 0;
    } else if (len < sizeof(line) - 1) {
      line[len++] = c;
    }
  }
}

void handle(char *s) {
  uint8_t buf[256];
  unsigned a = 0, b = 0, c = 0;
  switch (s[0]) {
    case 'P': {
      uint8_t w = 0;
      if (!bank0() || !rdReg(part->who_reg, &w, 1)) { Serial.println("ERR i2c"); return; }
      Serial.print("OK "); Serial.println(w, HEX);
      return;
    }
    case 'G':
      if (sscanf(s + 1, "%x %u", &a, &b) != 2 || b > sizeof(buf)) { Serial.println("ERR arg"); return; }
      if (!rdReg(a, buf, b)) { Serial.println("ERR i2c"); return; }
      Serial.print("OK "); emitHex(buf, b); Serial.println();
      return;
    case 'S': {
      char *sp = strchr(s + 2, ' ');
      if (!sp || sscanf(s + 1, "%x", &a) != 1) { Serial.println("ERR arg"); return; }
      size_t n = parseHex(sp + 1, buf, sizeof(buf));
      Serial.println(n && wrReg(a, buf, n) ? "OK" : "ERR i2c");
      return;
    }
    case 'M':
      if (sscanf(s + 1, "%u %x %u", &a, &b, &c) != 3 || c > 128) { Serial.println("ERR arg"); return; }
      if (!memRead(a, b, buf, c)) { Serial.println("ERR i2c"); return; }
      Serial.print("OK "); emitHex(buf, c); Serial.println();
      return;
    case 'N': {
      char *p1 = strchr(s + 2, ' ');
      char *p2 = p1 ? strchr(p1 + 1, ' ') : NULL;
      if (!p2 || sscanf(s + 1, "%u %x", &a, &b) != 2) { Serial.println("ERR arg"); return; }
      size_t n = parseHex(p2 + 1, buf, sizeof(buf));
      Serial.println(n && memWrite(a, b, buf, n) ? "OK" : "ERR i2c");
      return;
    }
    case 'F': {
      uint8_t fc[2];
      if (!bank0() || !rdReg(part->fifo_cnt, fc, 2)) { Serial.println("ERR i2c"); return; }
      Serial.print("OK "); Serial.println((fc[0] << 8) | fc[1]);
      return;
    }
    case 'R':
      if (sscanf(s + 1, "%u", &a) != 1 || a > sizeof(buf)) { Serial.println("ERR arg"); return; }
      if (!bank0() || !rdReg(part->fifo_rw, buf, a)) { Serial.println("ERR i2c"); return; }
      Serial.print("OK "); emitHex(buf, a); Serial.println();
      return;
    case 'I':
      Serial.print("OK "); Serial.print(digitalRead(INT_PIN));
      Serial.print(' '); Serial.println(intCount);
      return;
    case 'Z':
      intCount = 0; Serial.println("OK");
      return;
    case 'A':
      if (sscanf(s + 1, "%x", &a) != 1 || a > 0x7F) { Serial.println("ERR arg"); return; }
      MPU = a; Serial.println("OK");
      return;
    case 'X': {
      Serial.print("OK");
      for (uint8_t addr = 0x08; addr < 0x78; addr++) {
        Wire.beginTransmission(addr);
        if (Wire.endTransmission() == 0) { Serial.print(' '); Serial.print(addr, HEX); }
      }
      Serial.println();
      return;
    }
    case 'Y': {
      if (sscanf(s + 1, "%u", &a) == 1) digitalWrite(FSYNC_PIN, a ? HIGH : LOW);
      Serial.print("OK "); Serial.println(digitalRead(FSYNC_PIN));
      return;
    }
    case 'K': {
      if (strstr(s + 1, "mpu")) part = &PART_MPU;
      else if (strstr(s + 1, "icm")) part = &PART_ICM;
      else if (s[1] && s[1] != ' ') { Serial.println("ERR arg"); return; }
      Serial.print("OK "); Serial.print(part->name); Serial.print(' '); Serial.println(MPU, HEX);
      return;
    }
    case 'T': {
      unsigned ms = 600;
      sscanf(s + 1, "%u", &ms);
      if (!bank0() || !wr1(part->user_ctrl, 0x00)) { Serial.println("ERR i2c"); return; }
      intCount = 0;
      if (!wr1(part->user_ctrl, part->t_reset) || !wr1(part->user_ctrl, 0xC0)) { Serial.println("ERR i2c"); return; }
      uint32_t t0 = micros();
      while (intCount == 0 && (micros() - t0) < ms * 1000UL) { }
      wr1(part->user_ctrl, 0x00);        // stop within microseconds of the edge
      uint32_t dt = micros() - t0;
      uint32_t n = intCount;
      Serial.print("OK "); Serial.print(n); Serial.print(' '); Serial.println(dt);
      return;
    }
  }
  Serial.println("ERR cmd");
}
