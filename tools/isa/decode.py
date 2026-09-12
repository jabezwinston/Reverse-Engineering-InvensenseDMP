#!/usr/bin/env python3
"""Annotated DMP decoder under the pointer model (2026-09-08).

    8x  P0.page = x        bx (mantis) sel=bits[3:2] -> pointer, bank=bits[1:0]
    9x  P1.page = x        cx (3050)   sel=bits[2:1] -> pointer, bank=bit0   (c0..c5)
    ax  P2.page = x
    low byte v = 0 AA BB ooo :  A-word = P0 + 4*AA, B-word = P1 + 4*BB, op = ooo
                                 (bench: emitted value = M[B-word] + M[A-word] in FIFO mode)
    f4 imm (mantis) / fc imm (3050): forward branch to site+2+imm, 7-bit displacement.
        imm>=0x80 does NOT branch and is not an operand: the byte executes  [probe27, HW]
    d1: TEST Z := (result == 0).  d8 always; d9 IF.Z; da IF.NZ; db IF.3 (true at rest):
        single-shot conditional prefixes on the NEXT instruction        [probe10/19/20, HW]
    P2 word index (2 bits, mod 4): df/fa/fb/odd-cx pre-advance 1, d0 += 2; op&4 pre-advances 1
    f8/f9: INC/DEC M[P2] by 1 LSB; fa/fb: same after advancing         [probe23, HW]
    de: M[P2] := 0 in place; df: advance the word first, then clear    [probe23/31, HW]
    c0..cf (mantis): MOV M[P0 + 4*(x>>1)] -> M[P2]; x&1 pre-advances P2;
                     x&8 = MOV16 (upper half-word, zero-extended)        [probe25, HW]
    dc/dd: result routing RAM/FIFO (sticky two-way switch; FIFO at rest)          [probe9-16, HW]
    f5: prefix -- the next ALU op with op field 0 computes signed MIN(A,B)  [probe29, HW]
    f0..f3 (mantis) / f8..fb (3050): FIFO width/mode        [bench]

Usage: decode.py <image.bin> [--start N] [--end N] [--symbols dmpmap|emd|hammerhead|none]
"""
import argparse, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from symbols import symbols, dmpmap, dmp3map, data_labels

def lineage_of(img, start):
    if len(img) > 14000:
        return "icm"                       # DMP3: the 14301 B ICM-20948 image (Finding 24)
    code = img[start:]
    old = sum(code.count(b) for b in range(0xC0, 0xC6)) + sum(code.count(b) for b in range(0xF8, 0xFC))
    new = sum(code.count(b) for b in range(0xB0, 0xBC)) + sum(code.count(b) for b in range(0xF0, 0xF4))
    return "3050" if old > new else "mantis"

# Bytes with no hardware-confirmed meaning.  These are rendered with a leading "?" so a
# listing can never pass a guess off as a decode; the evidence and the experiment that would
# settle each are in UNKNOWNS.md.
CONJECTURE = {}     # nothing in the mantis lineage is conjectural any more (Findings 19-21)


class Namer:
    def __init__(self, table):
        # table: name -> address. Build address -> best name (prefer 32-bit H names).
        self.by_addr = {}
        for n, a in sorted(table.items(), key=lambda kv: (kv[1], len(kv[0]))):
            self.by_addr.setdefault(a, n)
    def name(self, a):
        for k in (a, a - 1, a - 2, a - 3):
            n = self.by_addr.get(k)
            if n is not None:
                n = n.replace("DMP_", "")
                if n.endswith("H") and k == a: n = n[:-1]
                return n if k == a else f"{n}+{a-k}"
        return f"@{a}"

class Decoder:
    def __init__(self, img, lineage, namer):
        self.img, self.L, self.N = img, lineage, namer
        self.page = [0, 0, 0]; self.bank = [0, 0, 0]; self.blk = [0, 0, 0]
        self.cond = "d8"; self.width = None; self.ram = False   # dc/dd routing, off at start
        self.mode4 = False                                       # icm: after f4, until f0-f7
        self.base = 0x90 if lineage == "icm" else 0              # image offset -> DMP address
        if lineage in ("mantis", "icm"):
            self.br = 0xF4; self.bankfam = 0xB; self.fmode = range(0xF0, 0xF4)
        else:
            self.br = 0xFC; self.bankfam = None; self.fmode = range(0xF8, 0xFC)
    def ptr(self, p):
        # icm: bc/bd/be add a 1 KB block (mod 4) above bank/page -- a 12-bit pointer (probe47)
        return self.blk[p] * 1024 + self.bank[p] * 256 + self.page[p] * 16 + (getattr(self, "p2off", 0) if p == 2 else 0)
    def io(self):
        return "  ; I/O space: pointer loaded under mode 4 (probe47/48)" if self.mode4 else ""
    def step(self, i):
        b = self.img[i]; L = self.L
        if L == "icm" and b == 0xF4 and i + 2 < len(self.img):
            # DMP3: f4 hi lo is a 16-bit absolute jump when hi < 0x80; bit 14 makes it a
            # call (e0 returns).  Every f4 also enters mode 4, which the vendor leaves with
            # f1/f3 at every target and after every call (probe45/46; Finding 24).
            self.mode4 = True
            hi, lo = self.img[i + 1], self.img[i + 2]
            if hi < 0x80:
                t = (hi << 8) | lo
                verb = "CALL" if t & 0x4000 else "JUMP"
                if self.cond != "d8": verb += "." + self.cond
                return 3, f"{verb} -> {t & 0x3FFF:#06x}"
            return 1, "MODE4   (f4 alone: pointer loads now address the I/O space; f0-f7 ends it)  [probe47]"
        if b == self.br and i + 1 < len(self.img):
            imm = self.img[i + 1]
            if imm < 0x80:
                return 2, f"{'B' if self.cond=='d8' else 'B.'+self.cond} -> {i+2+imm}"
            # bit 7 set: no branch is taken and the next byte executes normally, so f4
            # consumes only itself here (probe26/27).
            return 1, "NOBR   (f4 with bit7 set in the displacement: no jump)  [probe27]"
        if L == "icm" and b == 0xE0:
            return 1, "RET   (e0; ends every called routine and the image)  [probe46]"
        fam = b >> 4
        if fam == 8: self.page[0] = b & 0xf; return 1, f"P0.page={b&0xf:x}   -> A@{self.ptr(0)} {self.N.name(self.ptr(0))}" + self.io()
        if fam == 9: self.page[1] = b & 0xf; return 1, f"P1.page={b&0xf:x}   -> B@{self.ptr(1)} {self.N.name(self.ptr(1))}" + self.io()
        if fam == 0xA: self.page[2] = b & 0xf; self.p2off = 0; return 1, f"P2.page={b&0xf:x}   -> D@{self.ptr(2)} {self.N.name(self.ptr(2))}" + self.io()
        if L in ("mantis", "icm") and fam == 0xB:
            sel, bank = (b >> 2) & 3, b & 3
            if sel < 3: self.bank[sel] = bank; return 1, f"P{sel}.bank={bank}"
            if L == "icm" and bank < 3:
                self.blk[bank] = (self.blk[bank] + 1) & 3
                return 1, f"P{bank}.blk++ -> {self.blk[bank]}   (+1 KB, mod 4; probe47)"
            return 1, f"bank-sel3 {bank}   ; unknown"
        if L == "3050" and 0xC0 <= b <= 0xC5:
            sel, bank = (b >> 1) & 3, b & 1
            self.bank[sel] = bank; return 1, f"P{sel}.bank={bank}"
        if 0xD8 <= b <= 0xDB:
            self.cond = f"{b:02x}"; return 1, {0xD8: "ALWAYS", 0xD9: "IF.Z", 0xDA: "IF.NZ", 0xDB: "IF.3"}[b]
        if L == "icm" and 0xF0 <= b <= 0xF7 and b != 0xF4:
            self.mode4 = False
        if b in self.fmode:
            self.width = b & 3
            # probe37, 3 repeats per cell, raw hex.  These are not FIFO-only: they change what a
            # RAM store writes.  With P2 holding 0x7E7E7E7E and the op computing 1.5:
            #   f1 -> 0x60000000 (32-bit, same as the default)   f2 -> 0x60007E7E (upper half)
            #   f3 -> 0x7E7E0000 (lower half)                    f0 -> the A operand contributes 0
            note = {0: "A operand contributes 0 (single-shot)", 1: "32-bit store",
                    2: "16-bit store, upper half-word", 3: "16-bit store, lower half-word"}[b & 3]
            return 1, f"WIDTH.{b&3}   ; {note}  [probe37]"
        if self.L in ("mantis", "icm") and 0xF8 <= b <= 0xFB:
            if b & 2: self.p2off = (getattr(self, "p2off", 0) + 4) % 16
            verb = "DEC" if b & 1 else "INC"
            return 1, f"{verb}  {self.N.name(self.ptr(2))} by 1{'  (P2 word++ first)' if b & 2 else ''}  ({b:02x}; probe23)"
        if b == 0xF5 and self.L in ("mantis", "icm"):
            self.minpfx = True
            return 1, "MIN prefix  next ALU op computes signed min(A,B)  [probe29, 16/16]"
        if b == 0xF6 and self.L in ("mantis", "icm"):
            # Same MIN as f5, but the store is 16-bit: only the upper half-word is written and
            # the destination's low half survives.  probe36, raw hex:
            #   f5 00 -> 0x20000000     f6 00 -> 0x20007E7E  (7E7E = the seed's low half)
            self.minpfx = True; self.half = True
            return 1, "MIN16 prefix  signed min(A,B), 16-bit store (upper half-word)  [probe31/36]"
        if b == 0xF7 and self.L in ("mantis", "icm"):
            # probe36 seeded known destinations: 0x12345678 -> 0x12340000, 0x0000FFFF -> 0.
            # The following ALU op does not store (16/16 sweep cells + 4 seeded cells).
            self.nostore = True
            return 1, (f"TRUNC {self.N.name(self.ptr(2))} &= 0xFFFF0000   clear the low half-word"
                       f"  (the next ALU op does not store)  [probe36]")
        if b == 0xFC and self.L in ("mantis", "icm"):
            # probe35: the A field indexes P1 and the B field indexes P0.  32/32 cells over two
            # independent operand vectors.  Paired with RSUB (B-A) this gets the opposite
            # subtraction order without reloading a pointer -- 11/19 sites are followed by RSUB.
            self.swap = True
            return 1, "SWAP prefix  next ALU op reads A through P1 and B through P0  [probe35, 32/32]"
        if b == 0xFD and self.L in ("mantis", "icm"):
            # probe31: 16/16 no-store across the operand grid, and `fd 20 09 71 58`
            # suppressed all four ops -- so it is not single-shot on the bench.  It is
            # rendered as single-shot anyway because all three corpus sites head a live
            # biquad run that would otherwise be entirely dead code.  Scope: open.
            self.nostore = True
            return 1, "NOSTORE  the following ALU result is not written  [probe31; scope open, see UNKNOWNS.md]"
        if self.L == "3050" and 0xFD <= b <= 0xFF:
            # dmpKey.h puts the DINAF8 family at 0xf8 in the 3050 lineage and at 0xf0 in
            # mantis, so 3050 fc..ff are mantis f4..f7 -- fc is already decoded as the branch
            # on exactly that basis.  There is no MPU-3050 here, so these stay conjecture.
            # But 0xff is certainly NOT halt in this lineage: image 1024 carries one at 825,
            # unconditional (`d8 d8 ff` = CFG_6), and FCFG_1/2/7/3 at 868..936 still have to
            # run -- the vendor's drivers patch them at runtime.
            if b == 0xFF:
                self.nostore = True
                return 1, (f"?TRUNC {self.N.name(self.ptr(2))} &= 0xFFFF0000   (the next ALU op does not store)"
                           f"   ; CONJECTURE: 3050 ff = mantis f7, no MPU-3050 to test")
            self.minpfx = True
            if b == 0xFE:
                self.half = True
                return 1, ("?MIN16 prefix  signed min(A,B), 16-bit store"
                           "   ; CONJECTURE: 3050 fe = mantis f6 (the vendor also defines DINAFE = 0xfe here)")
            return 1, "?MIN prefix  next ALU op computes signed min(A,B)   ; CONJECTURE: 3050 fd = mantis f5"
        if b == 0xFF:
            return 1, "HALT   disable/terminate (vendor: ends every image; probe26)"
        if b == 0xFE:
            return 1, "SKIP   (vendor: DINAFE; never probed -- label only)"
        if b == 0xD1:
            return 1, "TEST  Z := (last ALU result == 0); d9 = IF.Z, da = IF.NZ  [probe19/20]"
        if b == 0xD0:
            self.p2off = (getattr(self, "p2off", 0) + 8) % 16
            return 1, f"P2 word += 2 -> D@{self.ptr(2)} {self.N.name(self.ptr(2))}  (d0, mod 4; probe20)"
        if self.L in ("mantis", "icm") and 0xC0 <= b <= 0xCF:
            k = (b >> 1) & 3                       # source word of the P0 page; bit0 pre-advances P2
            if b & 1: self.p2off = (getattr(self, "p2off", 0) + 4) % 16
            src = self.ptr(0) + 4 * k
            op = "MOV16" if b & 8 else "MOV  "     # c8..cf: upper half-word, zero-extended
            note = ""
            if b & 8 and L == "icm":
                # probe44: `cc` under f1 emitted the whole 32-bit word on the ICM; the MPU
                # reading is from vendor names only, so this is an open difference.
                op = "MOV? "; note = "  ; c8-cf: full word on DMP3 under f1 (probe44), MOV16 is the MPU label"
            return 1, (f"{op} {self.N.name(src):<12} -> {self.N.name(self.ptr(2))}"
                       f"{'  (P2 word++ first)' if b & 1 else ''}  ({b:02x}; probe25){note}")
        if b == 0xDE:
            # Writes a zero through the current result route: with dc (RAM) it clears the
            # P2 word in place, without advancing.  Earlier rounds called it inert because
            # they ran it BEFORE a store, which then overwrote the zero.  probe31 B:
            #   ba a4 dc 40 de -> 0x240 = +0.00   (the store had put +1.00 there)
            #   ba a4 dc de 40 -> 0x240 = +1.00   (so it does not move the destination)
            return 1, f"CLR  {self.N.name(self.ptr(2))} := 0  (in place, no advance)  (de; probe31)"
        if b == 0xDF:
            self.p2off = (getattr(self, "p2off", 0) + 4) % 16   # 2-bit word index
            return 1, f"CLR  {self.N.name(self.ptr(2))} := 0  (P2 word++ first)  (df; probe23)"
        if b == 0xDD:
            self.ram = False; return 1, "ROUTE -> FIFO  (dd; sticky until dc)  [probe16]"
        if b == 0xDC:
            self.ram = True; return 1, f"ROUTE -> RAM   M[P2..] {self.N.name(self.ptr(2))}  (dc; sticky until dd)"
        if self.L == "3050" and 0xC8 <= b <= 0xCF:
            # DINAC8..DINACF are 0xc8..0xcf in BOTH lineages' headers, and in mantis this half
            # is MOV16.  Untestable here (the rig is an MPU-6050), so it stays a conjecture.
            k = (b >> 1) & 3
            return 1, (f"?MOV16 {self.N.name(self.ptr(0) + 4 * k)} -> {self.N.name(self.ptr(2))}"
                       f"   ; CONJECTURE: assumed same as mantis c8-cf, no MPU-3050 to test")
        if b in CONJECTURE and self.L == "mantis":
            return 1, CONJECTURE[b] + "  [UNKNOWNS.md]"
        if b < 0x80:
            A, B, op = (b >> 5) & 3, (b >> 3) & 3, b & 7
            if getattr(self, "swap", False):          # fc: operand pointers exchanged
                self.swap = False
                a, bb = self.ptr(1) + 4 * A, self.ptr(0) + 4 * B
            else:
                a, bb = self.ptr(0) + 4 * A, self.ptr(1) + 4 * B
            ALU = {0: "ADD", 1: "RSUB", 2: "MUL", 3: "NMUL"}[op & 3]
            if getattr(self, "minpfx", False):
                self.minpfx = False
                if op & 3 == 0: ALU = "MIN "        # only op0 is confirmed under f5
                else: ALU = f"F5.{op & 3}"
            # op&4 PRE-ADVANCES the P2 word (mod 4); it is not a fixed +4 offset.
            # probe32: `44 44 44` writes 0x244/0x248/0x24c, and `00 2c 54 7c`
            # writes four consecutive words -- that is how QT1..QT4 get updated.
            if op & 4: self.p2off = (getattr(self, 'p2off', 0) + 4) % 16
            d = self.ptr(2)
            if getattr(self, "nostore", False):
                self.nostore = False
                dest = "(discarded)"
            elif self.ram:
                dest = self.N.name(d)
                if getattr(self, "half", False) or self.width in (2, 3):
                    dest += ".hi" if (getattr(self, "half", False) or self.width == 2) else ".lo"
            else:
                dest = f"FIFO{ {1: 32, 2: 16, 3: 16}.get(self.width, '') }"
            self.half = False
            return 1, f"{ALU} A={self.N.name(a):<12} B={self.N.name(bb):<12} -> {dest}"
        return 1, f"{b:02x}"

def run(img, start, end, table):
    L = lineage_of(img, start)
    d = Decoder(img, L, Namer(table))
    print(f"; lineage={L} start={start}" + (f"  (DMP address = image offset + {d.base:#x})" if d.base else ""))
    i = start
    while i < end:
        n, txt = d.step(i)
        if not (0xD8 <= img[i] <= 0xDB):
            if d.cond != "d8": txt = f"[{d.cond}] " + txt
            d.cond = "d8"                              # single-shot: governs one instruction (probe10)
        if d.base: print(f"{i + d.base:#06x}  {img[i:i+n].hex(' '):8}  {txt}")
        else:      print(f"{i:5}  {img[i:i+n].hex(' '):6}  {txt}")
        i += n

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("image"); ap.add_argument("--start", type=int); ap.add_argument("--end", type=int)
    ap.add_argument("--symbols", default="auto")
    a = ap.parse_args()
    img = pathlib.Path(a.image).read_bytes(); size = len(img)
    # ICM: the image loads at 0x90 and starts at 0x1000, so code begins at offset 0xf70 (Finding 24)
    start = a.start if a.start is not None else (0x1000 - 0x90 if size > 14000 else 1024 if size > 2000 else 512 if size == 1024 else 768)
    end = a.end or size
    syms = symbols()
    if a.symbols == "auto":
        table = dmp3map() if size > 14000 else data_labels(syms[3062]) if size == 3062 else data_labels(syms[2639]) if size == 2639 else dmpmap()
    elif a.symbols == "dmpmap": table = dmpmap()
    elif a.symbols == "emd": table = data_labels(syms[3062])
    elif a.symbols == "hammerhead": table = data_labels(syms[2639])
    else: table = {}
    run(img, start, end, table)
