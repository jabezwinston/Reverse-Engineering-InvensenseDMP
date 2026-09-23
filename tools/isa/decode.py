#!/usr/bin/env python3
"""Annotated DMP decoder under the pointer model (2026-09-08).

    8x  P0.page = x        bx (mantis) sel=bits[3:2] -> pointer, bank=bits[1:0]
    9x  P1.page = x        cx (3050)   sel=bits[2:1] -> pointer, bank=bit0   (c0..c5)
    ax  P2.page = x
    low byte v = 0 AA BB ooo :  A-word = P0 + 4*AA, B-word = P1 + 4*BB, op = ooo
                                 (bench: emitted value = M[B-word] + M[A-word] in FIFO mode)
    f4 d (mantis) / fc d (3050): branch to site+2+d, d a SIGNED 6-bit field (-32..+31)
        [probe101, HW; 3050 by analogy]; f4 41-7f raise DMP_INT; imm>=0x80 does NOT branch and
        is not an operand: the byte executes  [probe27, HW].  Every f4 leaves mode 4 [probe95-97]
    F: the sign of the exact last result; d1 TEST makes it result == 0.  d8 always; d9/db IF F;
        da IF not F; sticky until the next d8-db; F frozen while armed   [Findings 27, 37]
    P2 word index (2 bits, mod 4): df/fa/fb/odd-cx pre-advance 1, d0 += 2; op&4 pre-advances 1
    f8/f9: INC/DEC M[P2] by 1 LSB; fa/fb: same after advancing         [probe23, HW]
    de: M[P2] := 0 in place; df: advance the word first, then clear    [probe23/31, HW]
    c0..cf (mantis): MOV M[P0 + 4*(x>>1)] -> M[P2]; x&1 pre-advances P2;
                     x&8 = MOVX (the half-words exchanged)               [probe25/54/67, HW]
    dc/dd: result routing RAM/FIFO (sticky two-way switch; FIFO at rest)          [probe9-16, HW]
    f5/f6/f7: modes: op field 0 CLAMP A to +-B, 1 sign test (F := A<0<=B), 2 AND, 3 XOR  [probe70/98/103]
    f0..f3 (mantis) / f8..fb (3050): MAC, 32-bit, high 16-bit lane, low 16-bit lane  [Finding 37]

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
        self.logic = None                                        # f5/f6/f7: CLAMP/CMP/AND/XOR mode (probe70/103)
        self.mac = False                                         # f0: multiply-accumulate mode (probe74)
        self.mode4 = False                                       # after any f4, until f0-f3/f5-f7 (both cores)
        self.base = 0x90 if lineage == "icm" else 0              # image offset -> DMP address
        if lineage in ("mantis", "icm"):
            self.br = 0xF4; self.bankfam = 0xB; self.fmode = range(0xF0, 0xF4)
        else:
            self.br = 0xFC; self.bankfam = None; self.fmode = range(0xF8, 0xFC)
    def ptr(self, p):
        # icm: bc/bd/be add a 1 KB block (mod 4) above bank/page -- a 12-bit pointer (probe47)
        return self.blk[p] * 1024 + self.bank[p] * 256 + self.page[p] * 16 + (getattr(self, "p2off", 0) if p == 2 else 0)
    def io(self):
        return "  ; I/O space: pointer loaded under mode 4 (probe47/48)" if self.mode4 and self.L == "icm" else ""
    def step(self, i):
        b = self.img[i]; L = self.L
        if L == "icm" and self.mode4 and b < 0x80 and i + 1 < len(self.img):
            # Mode 4 is branch-target mode: while it is set, every byte below 0x80 begins a
            # 16-bit big-endian target, whether or not an f4 immediately precedes it.  The
            # 14290/14301 image pair proves it statically -- nine targets sit after d8/da/bc
            # rather than f4 (`f4 16 14 d8 17 74`: if-jump, else-jump) and their low bytes
            # move with the code like every other target's (Finding 26).
            t = (b << 8) | self.img[i + 1]
            verb = "CALL" if t & 0x4000 else "JUMP"
            if self.cond != "d8": verb += "." + self.cond
            return 2, f"{verb} -> {t & 0x3FFF:#06x}   (target under mode 4, no f4 of its own)"
        if L == "mantis" and self.mode4 and b < 0x80:
            # Finding 42 (probe104): in mode 4 the MPU reads a byte below 0x40 as a ONE-byte
            # branch, the f4's displacement without the f4: to i + 1 + sext6(b).  0x40-0x7f do
            # not branch or interrupt; what else they do is unmeasured.  (A linear decode assumes
            # the fall-through's mode; a branch target can be reached in another.)
            if b < 0x40:
                t = i + 1 + (b if b < 0x20 else b - 64)
                return 1, f"{'B1' if self.cond == 'd8' else 'B1.' + self.cond} -> {t}   (one-byte branch under mode 4)"
            return 1, f"?M4 {b:02x}   (under mode 4: no branch, no interrupt; the rest unmeasured, probe104)"
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
            if L == "mantis":
                self.mode4 = True                  # every f4 [Finding 40, probe95-97]
            if 0x40 <= imm < 0x80:
                # probe69/70: bit 6 with a nonzero low field raises DMP_INT and does not branch
                # (f4 44, f4 41, f4 42, f4 48); f4 40 alone does nothing; f4 60 emitted a zero word.
                return 2, (f"INT   raise DMP_INT, no branch  (f4 {imm:02x}; probe69/70)" if imm & 0x1F else
                           f"f4 {imm:02x}: no branch, no interrupt measured (probe70)")
            if imm < 0x80:                     # signed 6 bits [probe101, Finding 40]
                t = i + 2 + (imm if imm < 0x20 else imm - 64)
                return 2, f"{'B' if self.cond=='d8' else 'B.'+self.cond} -> {t}{'  (back)' if imm >= 0x20 else ''}"
            # bit 7 set: no branch is taken and the next byte executes normally, so f4
            # consumes only itself here (probe26/27).
            return 1, "NOBR   (f4 with bit7 set in the displacement: no jump)  [probe27]"
        if L == "icm" and b == 0xE0:
            return 1, "RET   (e0; ends every called routine and the image)  [probe46]"
        if L == "icm" and b == 0xE2:
            return 1, "INT   raise DMP_INT1  (e2; vendor: da f0 e2 f1)  [probe53]"
        if L == "icm" and b == 0xE7:
            return 1, f"CLR  {self.N.name(self.ptr(2))} := 0  (e7; same as de in every cell)  [probe53]"
        if L == "icm" and b in (0xD2, 0xD3):
            # probe51 D: the low 30 bits of the last 64-bit product, sign-extended from bit 29
            if b == 0xD3: self.p2off = (getattr(self, "p2off", 0) + 4) % 16
            return 1, (f"STORE.LO  {self.N.name(self.ptr(2))} := low word of the last product"
                       f"{'  (P2 word++ first)' if b == 0xD3 else ''}  ({b:02x}; probe51)")
        if L == "icm" and 0xD4 <= b <= 0xD7:
            self.shw = b - 0xD4
            return 1, f"SHIFTER.LOAD  4 words from {self.N.name(self.ptr(0))}, select word {b - 0xD4}  ({b:02x}; probe51)"
        if L == "icm" and b == 0xFD and i + 1 < len(self.img):
            # probe51: fd n is a two-byte SHIFT of the 4-word register, not NOSTORE.
            # probe64: the register is also loaded by every ALU op -- the last loader wins -- so
            # `20 fd 3f` halves a sum and `0a fd 0f` rescales a product (the register holds the
            # 64-bit product: MUL, then left by 15, stores product >> 15).  Shifts compound.
            n = self.img[i + 1]; sh = n & 0x1F
            if n & 0x40: self.p2off = (getattr(self, "p2off", 0) + 4) % 16
            k = getattr(self, "shw", None)
            what = (f"word {k} of the d4-d7 load" if isinstance(k, int) else "the last ALU result" if k == "alu"
                    else "the 64-bit product" if k == "mul" else "? (nothing loaded in this run: stores 0)")
            how = f"arithmetic right by {32 - sh}" if n & 0x20 else f"left by {sh} (pulls the next word's fraction in)"
            dest = self.N.name(self.ptr(2)) if self.ram else "FIFO"
            self.shw = "shifted"
            return 2, (f"SHIFT  {how}; store {what} -> {dest}{'  (P2 word++ first)' if n & 0x40 else ''}  (fd {n:02x}; probe51/64)")
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
            self.cond = f"{b:02x}"
            if L == "icm":
                # probe52: one flag F. Every ALU op / INC / DEC sets F := result < 0; d1 sets
                # F := result == 0. d9 = IF.F, da = IF.not F, db = IF.F in every cell. Sticky:
                # a not-taken predicate skips everything up to the next d8..db.
                # probe60: while d9/da/db is armed, ALU ops, INC and DEC do NOT update F (d1 and
                # fc still do) -- so a predicated block cannot disturb its own condition, and a
                # loop's DEC must run under d8 (Finding 27).
                return 1, {0xD8: "ALWAYS  (re-arms: ends a sticky predicate; ALU/INC/DEC update F only under d8)", 0xD9: "IF.F   (F = result<0, or ==0 right after d1; sticky until d8; F frozen while armed)",
                           0xDA: "IF.NOT-F   (sticky until d8; F frozen while armed)", 0xDB: "IF.F   (db; identical to d9 in every DMP3 cell, probe52/54)"}[b]
            # Finding 37 (probe86, MPU-6050): one flag F, as on DMP3 -- the sign of the exact
            # result, or result == 0 after d1; d9 = db = IF F, da = IF not F.  Sticky until the
            # next d8..db, and F is frozen while a predicate is armed.  (Finding 28's N/Z reading
            # was a zero result's own FIFO emit read as the marker.)
            return 1, {0xD8: "ALWAYS  (ends a sticky predicate)", 0xD9: "IF.F   (F = exact result < 0, or == 0 right after d1; sticky until d8)",
                       0xDA: "IF.NOT-F   (sticky until d8)", 0xDB: "IF.F   (db; same as d9 in every cell)"}[b]
        if L in ("icm", "mantis") and 0xF0 <= b <= 0xF7 and b != 0xF4:
            self.mode4 = False
        if b in self.fmode:
            self.width = b & 3
            self.logic = None
            # probe74: f0 is the MULTIPLY-ACCUMULATE mode, not a store width and not "A = 0".
            # Under it every ALU op computes acc +=/-= A*B (sign = op&1) and stores/emits the
            # running accumulator, which is reset at the start of each pass.  `f0 00 08 10 18`
            # over A=0.5, B=[1,.5,.25,.125] emits 0.5 0.75 0.875 0.9375 -- a dot product.  It is
            # sticky (any other fX ends it) and survives d8, MOV, a store and f1's mid-run reset
            # of the value.  DMP3 (icm) exposes the same multiplier through the shifter (d4-d7,
            # fd) instead; f0 there is unmeasured and left as a width.
            if b == 0xF0 and L != "icm":
                self.mac = True
                return 1, "MAC   ; multiply-accumulate: acc +=/-= A*B (op&1), store/emit acc; reset per pass  [probe74]"
            self.mac = False
            note = {0: "32-bit store (icm; f0 on the MPU is MAC)", 1: "32-bit store",
                    2: "high 16-bit lane: the ALU computes on the upper half-words",
                    3: "low 16-bit lane: the ALU computes on the sign-extended lower half-words"}[b & 3]
            return 1, f"WIDTH.{b&3}   ; {note}  [probe37]"
        if self.L in ("mantis", "icm") and 0xF8 <= b <= 0xFB:
            if b & 2: self.p2off = (getattr(self, "p2off", 0) + 4) % 16
            verb = "DEC" if b & 1 else "INC"
            # probe52/54/55, probe86: INC and DEC set F := result < 0 like the ALU on both
            # cores, so `f9 da f4 <back>` runs a body n + 1 times for a count of n.
            flag = "  F := result < 0"
            return 1, f"{verb}  {self.N.name(self.ptr(2))} by 1{'  (P2 word++ first)' if b & 2 else ''}{flag}  ({b:02x}; probe23)"
        if 0xF5 <= b <= 0xF7 and self.L in ("mantis", "icm"):
            # probe69/70 (MPU): f5, f6, f7 are modes 5..7 of the same sticky register as f1..f3.
            # Under them the ALU byte's op field selects CLAMP (0, long read as MIN), a no-store test that sets
            # the flags (1), AND (2) or XOR (3) -- 4 operand pairs each -- and the store width is
            # 32-bit (f5), the upper half-word (f6) or the lower half-word (f7).  f7 was read as
            # TRUNC + no-store from a cell where min(0.5, 0.5)'s low half happened to be 0000.
            # f1 (or any f0..f3) ends the mode; d8, pointer loads and MOVs do not.
            self.logic = b & 7; self.width = {5: 1, 6: 2, 7: 3}[b & 7]; self.mac = False
            return 1, {5: "LOGIC   ; ALU op field: 0 CLAMP A to +-B, 1 sign test (F := A<0<=B, no store), 2 AND, 3 XOR; sticky  [probe29/70/98/103]",
                       6: "LOGIC.HI   ; CLAMP / sign test / AND / XOR on the high 16-bit lane, sticky  [probe36/70/103]",
                       7: "LOGIC.LO   ; CLAMP / sign test / AND / XOR on the low 16-bit lane, sticky  [probe69/70/103]"}[b & 7]
        if b == 0xFC and L == "icm" and i + 2 < len(self.img):
            # Finding 27 (probe57/59/61/63): on DMP3 fc is a THREE-byte instruction, `fc X Y`,
            # that stores nothing and leaves no ALU result (d1 after it always reads zero).
            # With X = c0 it is a zero test of a P1 word:  F := (M[P1 + 4*B] == 0), inverted
            # when Y's op bit 0 is set; Y's A field and P0 are ignored (24 operand pairs).  The
            # vendor writes X = c0..c3 and Y in {00 04 08 0c 01 09 03 07}; the odd X forms and
            # X = c2 test something else in a few cells (open).  Both operand bytes are consumed
            # under mode 4 too, so `d8 fc c0 08 d9 f4` is "if word 1 is zero, jump".
            # probe65 (one zero moved through 24 words): X's low two bits select the P1 WORD
            # (c0 -> word 0 .. c3 -> word 3); Y's B field does not select a word -- with B != 0
            # no single zero fires the test at all (probe66 looks for a two-word form).
            # Finding 31 (probe76/77): fc cX Y is a BIT TEST of P1 word (X&3).  Y = 0x04/08/10/
            # 20/40/80 tests word bit 0/1/2/3/4/5 (fires when set); Y = 0 tests the low 6 bits all
            # clear, Y = 1 the complement; Y's op-field low bits modify the test and arbitrary Y
            # (e.g. the vendor's 0x0c) combines selector and op bits in a way only partly mapped.
            # So the feature gates are RAM bit tests, not an external condition.
            # Finding 35 (probe83b, 2048/2048 cells): it is an IMMEDIATE COMPARE, not a bit test:
            # F := (P1 word (X&3) & 0x3f) <cond> (Y >> 2), cond = Y & 3: 0 EQ, 1 GT, 2 LT, 3 NE.
            # The "bit tests" were equalities with one-hot values (Y = 04 is field == 1).  X below
            # 0xc0 is still three bytes and sets F, but its condition is only partly mapped.
            x, y = self.img[i + 1], self.img[i + 2]
            w = self.N.name(self.ptr(1) + 4 * (x & 3))
            if x >= 0xC0:
                c = ["==", ">", "<", "!="][y & 3]
                return 3, f"CMP   F := ({w} & 0x3f) {c} {y >> 2}   (fc {x:02x} {y:02x}; immediate compare, no store; probe83b)"
            return 3, f"CMP?  {w}   (fc {x:02x} {y:02x}; X < 0xc0: three bytes, sets F, condition partly mapped; probe83d/e)"
        if b == 0xFC and self.L in ("mantis", "icm"):
            # probe35: the A field indexes P1 and the B field indexes P0.  32/32 cells over two
            # independent operand vectors.  Paired with RSUB (B-A) this gets the opposite
            # subtraction order without reloading a pointer -- 11/19 sites are followed by RSUB.
            # probe68: it is a sticky TOGGLE, not a one-shot prefix -- MOVs read through P1 too,
            # d8/f1/dc do not end it, a second fc does.  The store still goes to P2.
            self.swap = not getattr(self, "swap", False)
            return 1, ("XCHG01  A and MOV sources through P1, B through P0, until the next fc  [probe35, probe68]"
                       if self.swap else "XCHG01  back to normal (second fc)  [probe68]")
        if b == 0xFD and self.L in ("mantis", "icm"):
            # probe67/68 (MPU): fd exchanges the roles of P0 and P2 -- the A operand and MOV
            # sources are read through P2 and the store lands in P0's page -- sticky until a
            # second fd.  probe31 watched M[P2] and saw nothing, hence "NOSTORE".
            self.xchg02 = not getattr(self, "xchg02", False)
            return 1, ("XCHG02  A and MOV sources through P2, stores into P0's page, until the next fd  [probe67/68]"
                       if self.xchg02 else "XCHG02  back to normal (second fd)  [probe68]")
        if self.L == "3050" and 0xFD <= b <= 0xFF:
            # dmpKey.h puts the DINAF8 family at 0xf8 in the 3050 lineage and at 0xf0 in
            # mantis, so 3050 fc..ff are mantis f4..f7 -- fc is already decoded as the branch
            # on exactly that basis.  There is no MPU-3050 here, so these stay conjecture.
            # But 0xff is certainly NOT halt in this lineage: image 1024 carries one at 825,
            # unconditional (`d8 d8 ff` = CFG_6), and FCFG_1/2/7/3 at 868..936 still have to
            # run -- the vendor's drivers patch them at runtime.
            if b == 0xFF:
                self.logic = 7; self.width = 3
                return 1, "?LOGIC.LO  (CLAMP/CMP/AND/XOR, lower half-word store)   ; CONJECTURE: 3050 ff = mantis f7, no MPU-3050 to test"
            self.logic = 5
            if b == 0xFE:
                self.logic = 6; self.width = 2
                return 1, "?LOGIC.HI  (CLAMP/CMP/AND/XOR, upper half-word store)   ; CONJECTURE: 3050 fe = mantis f6 (the vendor also defines DINAFE = 0xfe here)"
            return 1, "?LOGIC  (CLAMP/CMP/AND/XOR, 32-bit store)   ; CONJECTURE: 3050 fd = mantis f5"
        if b == 0xFF:
            return 1, "HALT   disable/terminate (vendor: ends every image; probe26)"
        if b == 0xFE:
            # probe69/70 (MPU): fe raises DMP_INT and the pass continues; it honours a predicate.
            # The vendor's DINAFE "disable" patches are therefore interrupts, not skips.
            return 1, "INT   raise DMP_INT and continue  (fe; conditional under a predicate; probe69/70)"
        if b == 0xD1:
            if L == "icm":
                return 1, "TEST  F := (last ALU result == 0)  (without d1, F is the result's sign)  [probe52]"
            return 1, "TEST  F := (last ALU result == 0)  (without d1, F is the exact result's sign)  [Finding 37]"
        if b == 0xD0:
            self.p2off = (getattr(self, "p2off", 0) + 8) % 16
            return 1, f"P2 word += 2 -> D@{self.ptr(2)} {self.N.name(self.ptr(2))}  (d0, mod 4; probe20)"
        if self.L in ("mantis", "icm") and 0xC0 <= b <= 0xCF:
            k = (b >> 1) & 3                       # source word of the P0 page; bit0 pre-advances P2
            if b & 1: self.p2off = (getattr(self, "p2off", 0) + 4) % 16
            src = self.ptr(0) + 4 * k
            op = "MOVX " if b & 8 else "MOV  "     # c8..cf: the half-words exchanged (probe54 C, probe67 D)
            note = "  ; c8-cf: half-words swapped, on both parts (probe54/67)" if b & 8 else ""
            if b & 8 and L == "icm":
                # probe54 C: on DMP3 c8..cf copy the word with its half-words exchanged
                # (01234567 -> 45670123); under f2/f3 that puts the source's LOW half into the
                # destination's upper half (4567ee00) or its HIGH half into the lower (c0ff0123).
                # The MPU label MOV16 is from vendor names only.
                op = "MOVX "; note = "  ; c8-cf on DMP3: half-words swapped (probe54 C)"
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
        if L == "mantis" and (b in (0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7) or 0xE0 <= b <= 0xEF):
            # probe67/68: on the MPU these clear M[P2] in place like de (d2..d5 measured, e7 too);
            # e0 / e2 emit a zero word under FIFO routing.  DMP3 gives them other meanings.
            return 1, f"CLR  {self.N.name(self.ptr(2))} := 0  (in place; {b:02x} = de on the MPU, probe68/69)"
        if b in CONJECTURE and self.L == "mantis":
            return 1, CONJECTURE[b] + "  [UNKNOWNS.md]"
        if b < 0x80:
            A, B, op = (b >> 5) & 3, (b >> 3) & 3, b & 7
            if getattr(self, "swap", False):          # fc: operand pointers exchanged (sticky on both parts)
                if L == "icm": self.swap = False
                a, bb = self.ptr(1) + 4 * A, self.ptr(0) + 4 * B
            elif getattr(self, "xchg02", False):      # fd on the MPU: A through P2
                a, bb = self.ptr(2) + 4 * A, self.ptr(1) + 4 * B
            else:
                a, bb = self.ptr(0) + 4 * A, self.ptr(1) + 4 * B
            ALU = {0: "ADD", 1: "RSUB", 2: "MUL", 3: "NMUL"}[op & 3]
            logic = getattr(self, "logic", None)
            mac = getattr(self, "mac", False)
            if logic:
                # probe70/98/103: op 0 clamps A to [-B, B] (F := clamped; long read as MIN,
                # Finding 41), op 1 only tests signs (F := A < 0 <= B, Finding 40)
                ALU = {0: "CLAMP", 1: "SGN ", 2: "AND ", 3: "XOR "}[op & 3]
            elif mac:
                ALU = "MAC-" if op & 1 else "MAC+"                            # probe74: acc +/- A*B
            # op&4 PRE-ADVANCES the P2 word (mod 4); it is not a fixed +4 offset.
            # probe32: `44 44 44` writes 0x244/0x248/0x24c, and `00 2c 54 7c`
            # writes four consecutive words -- that is how QT1..QT4 get updated.
            if op & 4: self.p2off = (getattr(self, 'p2off', 0) + 4) % 16
            d = self.ptr(0) if getattr(self, "xchg02", False) else self.ptr(2)
            if getattr(self, "nostore", False) or (logic and op & 3 == 1):
                self.nostore = False
                dest = "(no store; flags only)" if logic else "(discarded)"
            elif self.ram:
                dest = self.N.name(d)
                if self.width in (2, 3):
                    dest += ".hi" if self.width == 2 else ".lo"
            else:
                dest = f"FIFO{ {1: 32, 2: 16, 3: 16}.get(self.width, '') }"
            if L == "icm": self.shw = "mul" if op & 2 else "alu"      # the shifter's register follows every ALU op (probe64)
            if mac:
                return 1, f"{ALU} acc {'-=' if op & 1 else '+='} {self.N.name(a)} * {self.N.name(bb)} -> {dest}  (probe74)"
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
            pass                                        # sticky on both parts: governs everything up to the next d8..db (probe52, probe67)
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
