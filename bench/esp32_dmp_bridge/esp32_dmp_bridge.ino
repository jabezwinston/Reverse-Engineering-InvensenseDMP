// esp32_dmp_bridge - dumb I2C bridge to an MPU-6050 for DMP experiments.
//
// Wiring (as built):  SDA = D21, SCL = D22, MPU INT = D5
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
//   T <ms>                   single step: reset+start DMP, wait for one INT edge (or
//                            <ms> timeout), stop DMP  -> "OK <ints> <elapsed_us>"
//                            (host-side stepping over a slow link runs many samples)

#include <Wire.h>

static const uint8_t SDA_PIN = 21, SCL_PIN = 22, INT_PIN = 5;
static const uint8_t MPU = 0x68;

static const uint8_t RA_SMPLRT_DIV = 0x19, RA_USER_CTRL = 0x6A,
                     RA_PWR_MGMT_1 = 0x6B, RA_BANK_SEL = 0x6D,
                     RA_MEM_START = 0x6E, RA_MEM_R_W = 0x6F,
                     RA_FIFO_COUNTH = 0x72, RA_FIFO_R_W = 0x74,
                     RA_WHO_AM_I = 0x75;

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

// DMP memory is paged: bank select, then byte address within the 256-byte page.
static bool memSeek(uint8_t bank, uint8_t addr) {
  return wr1(RA_BANK_SEL, bank & 0x1F) && wr1(RA_MEM_START, addr);
}
static bool memRead(uint8_t bank, uint8_t addr, uint8_t *d, size_t n) {
  return memSeek(bank, addr) && rdReg(RA_MEM_R_W, d, n);
}
static bool memWrite(uint8_t bank, uint8_t addr, const uint8_t *d, size_t n) {
  return memSeek(bank, addr) && wrReg(RA_MEM_R_W, d, n);
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

  wr1(RA_PWR_MGMT_1, 0x80);              // device reset
  delay(100);
  wr1(RA_PWR_MGMT_1, 0x01);              // wake, clock = PLL/gyro-X
  delay(20);
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
      if (!rdReg(RA_WHO_AM_I, &w, 1)) { Serial.println("ERR i2c"); return; }
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
      if (!rdReg(RA_FIFO_COUNTH, fc, 2)) { Serial.println("ERR i2c"); return; }
      Serial.print("OK "); Serial.println((fc[0] << 8) | fc[1]);
      return;
    }
    case 'R':
      if (sscanf(s + 1, "%u", &a) != 1 || a > sizeof(buf)) { Serial.println("ERR arg"); return; }
      if (!rdReg(RA_FIFO_R_W, buf, a)) { Serial.println("ERR i2c"); return; }
      Serial.print("OK "); emitHex(buf, a); Serial.println();
      return;
    case 'I':
      Serial.print("OK "); Serial.print(digitalRead(INT_PIN));
      Serial.print(' '); Serial.println(intCount);
      return;
    case 'Z':
      intCount = 0; Serial.println("OK");
      return;
    case 'T': {
      unsigned ms = 600;
      sscanf(s + 1, "%u", &ms);
      if (!wr1(RA_USER_CTRL, 0x00)) { Serial.println("ERR i2c"); return; }
      intCount = 0;
      if (!wr1(RA_USER_CTRL, 0x4C) || !wr1(RA_USER_CTRL, 0xC0)) { Serial.println("ERR i2c"); return; }
      uint32_t t0 = micros();
      while (intCount == 0 && (micros() - t0) < ms * 1000UL) { }
      wr1(RA_USER_CTRL, 0x00);           // stop within microseconds of the edge
      uint32_t dt = micros() - t0;
      uint32_t n = intCount;
      Serial.print("OK "); Serial.print(n); Serial.print(' '); Serial.println(dt);
      return;
    }
  }
  Serial.println("ERR cmd");
}
