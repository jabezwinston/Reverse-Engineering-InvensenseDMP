#!/usr/bin/env python3
"""Annotated DMP decoder under the pointer model (2026-09-08).

    8x  P0.page = x        bx (mantis) sel=bits[3:2] -> pointer, bank=bits[1:0]
    9x  P1.page = x        cx (3050)   sel=bits[2:1] -> pointer, bank=bit0   (c0..c5)
    ax  P2.page = x
    low byte v = 0 AA BB ooo :  A-word = P0 + 4*AA, B-word = P1 + 4*BB, op = ooo
                                 (bench: emitted value = M[B-word] + M[A-word] in FIFO mode)
    f4 imm (mantis) / fc imm (3050): branch to site+2+imm   [proven vs eMD labels]
    d1: TEST Z := (result == 0).  d8 always; d9 IF.Z; da IF.NZ; db IF.3 (true at rest):
        single-shot conditional prefixes on the NEXT instruction        [probe10/19/20, HW]
    P2 word index (2 bits, mod 4): df/fa/fb/odd-cx pre-advance 1, d0 += 2; op&4 adds 1 for that op
    f8/f9: INC/DEC M[P2] by 1 LSB; fa/fb: same after advancing; df: advance then CLR  [probe23, HW]
    c0..cf (mantis): MOV M[P0 + 4*(x>>1)] -> M[P2]; x&1 pre-advances P2;
                     x&8 = MOV16 (upper half-word, zero-extended)        [probe25, HW]
    dc/dd: result routing RAM/FIFO (sticky two-way switch; FIFO at rest)   df: P2 += 4   [probe9-16, HW]
    f0..f3 (mantis) / f8..fb (3050): FIFO width/mode        [bench]

Usage: decode.py <image.bin> [--start N] [--end N] [--symbols dmpmap|emd|hammerhead|none]
"""
import argparse, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from symbols import symbols, dmpmap, data_labels

def lineage_of(img, start):
    code = img[start:]
    old = sum(code.count(b) for b in range(0xC0, 0xC6)) + sum(code.count(b) for b in range(0xF8, 0xFC))
    new = sum(code.count(b) for b in range(0xB0, 0xBC)) + sum(code.count(b) for b in range(0xF0, 0xF4))
    return "3050" if old > new else "mantis"

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
        self.page = [0, 0, 0]; self.bank = [0, 0, 0]
        self.cond = "d8"; self.width = None; self.ram = False   # dc/dd routing, off at start
        if lineage == "mantis":
            self.br = 0xF4; self.bankfam = 0xB; self.fmode = range(0xF0, 0xF4)
        else:
            self.br = 0xFC; self.bankfam = None; self.fmode = range(0xF8, 0xFC)
    def ptr(self, p): return self.bank[p] * 256 + self.page[p] * 16 + (getattr(self, "p2off", 0) if p == 2 else 0)
    def step(self, i):
        b = self.img[i]; L = self.L
        if b == self.br and i + 1 < len(self.img):
            imm = self.img[i + 1]
            if imm < 0x80:
                return 2, f"{'B' if self.cond=='d8' else 'B.'+self.cond} -> {i+2+imm}"
            return 2, f"{self.br:02x} {imm:02x}   ; imm>=0x80 (unknown form)"
        fam = b >> 4
        if fam == 8: self.page[0] = b & 0xf; return 1, f"P0.page={b&0xf:x}   -> A@{self.ptr(0)} {self.N.name(self.ptr(0))}"
        if fam == 9: self.page[1] = b & 0xf; return 1, f"P1.page={b&0xf:x}   -> B@{self.ptr(1)} {self.N.name(self.ptr(1))}"
        if fam == 0xA: self.page[2] = b & 0xf; self.p2off = 0; return 1, f"P2.page={b&0xf:x}   -> D@{self.ptr(2)} {self.N.name(self.ptr(2))}"
        if L == "mantis" and fam == 0xB:
            sel, bank = (b >> 2) & 3, b & 3
            if sel < 3: self.bank[sel] = bank; return 1, f"P{sel}.bank={bank}"
            return 1, f"bank-sel3 {bank}   ; unknown"
        if L == "3050" and 0xC0 <= b <= 0xC5:
            sel, bank = (b >> 1) & 3, b & 1
            self.bank[sel] = bank; return 1, f"P{sel}.bank={bank}"
        if 0xD8 <= b <= 0xDB:
            self.cond = f"{b:02x}"; return 1, {0xD8: "ALWAYS", 0xD9: "IF.Z", 0xDA: "IF.NZ", 0xDB: "IF.3"}[b]
        if b in self.fmode:
            self.width = b & 3; return 1, f"FMODE.{b&3}   ; 1=32-bit fifo, 2/3=16-bit"
        if self.L == "mantis" and 0xF8 <= b <= 0xFB:
            if b & 2: self.p2off = (getattr(self, "p2off", 0) + 4) % 16
            verb = "DEC" if b & 1 else "INC"
            return 1, f"{verb}  {self.N.name(self.ptr(2))} by 1{'  (P2 word++ first)' if b & 2 else ''}  ({b:02x}; probe23)"
        if b == 0xFA and self.L == "mantis":
            self.p2off = getattr(self, "p2off", 0) + 4
            return 1, f"P2 += 4      -> D@{self.ptr(2)} {self.N.name(self.ptr(2))}  (fa, probe18; same effect as df)"
        if b == 0xFF:
            return 1, "HALT   disable/terminate (vendor: ends every image)"
        if b == 0xFE:
            return 1, "SKIP   (vendor: DINAFE)"
        if b == 0xD1:
            return 1, "TEST  Z := (last ALU result == 0); d9 = IF.Z, da = IF.NZ  [probe19/20]"
        if b == 0xD0:
            self.p2off = (getattr(self, "p2off", 0) + 8) % 16
            return 1, f"P2 word += 2 -> D@{self.ptr(2)} {self.N.name(self.ptr(2))}  (d0, mod 4; probe20)"
        if self.L == "mantis" and 0xC0 <= b <= 0xCF:
            k = (b >> 1) & 3                       # source word of the P0 page; bit0 pre-advances P2
            if b & 1: self.p2off = (getattr(self, "p2off", 0) + 4) % 16
            src = self.ptr(0) + 4 * k
            op = "MOV16" if b & 8 else "MOV  "     # c8..cf: upper half-word, zero-extended
            return 1, (f"{op} {self.N.name(src):<12} -> {self.N.name(self.ptr(2))}"
                       f"{'  (P2 word++ first)' if b & 1 else ''}  ({b:02x}; probe25)")
        if b == 0xDF:
            self.p2off = getattr(self, "p2off", 0) + 4
            return 1, f"CLR  {self.N.name(self.ptr(2))} := 0  (P2 word++ first)  (df; probe23)"
        if b == 0xDD:
            self.ram = False; return 1, "ROUTE -> FIFO  (dd; sticky until dc)  [probe16]"
        if b == 0xDC:
            self.ram = True; return 1, f"ROUTE -> RAM   M[P2..] {self.N.name(self.ptr(2))}  (dc; sticky until dd)"
        if b < 0x80:
            A, B, op = (b >> 5) & 3, (b >> 3) & 3, b & 7
            a, bb = self.ptr(0) + 4 * A, self.ptr(1) + 4 * B
            ALU = {0: "ADD", 1: "RSUB", 2: "MUL", 3: "NMUL"}[op & 3]
            d = self.ptr(2) + (4 if op & 4 else 0)
            if self.ram: dest = self.N.name(d)
            else: dest = f"FIFO{ {1: 32, 2: 16, 3: 16}.get(self.width, '') }"
            return 1, f"{ALU} A={self.N.name(a):<12} B={self.N.name(bb):<12} -> {dest}"
        return 1, f"{b:02x}"

def run(img, start, end, table):
    L = lineage_of(img, start)
    d = Decoder(img, L, Namer(table))
    print(f"; lineage={L} start={start}")
    i = start
    while i < end:
        n, txt = d.step(i)
        if not (0xD8 <= img[i] <= 0xDB):
            if d.cond != "d8": txt = f"[{d.cond}] " + txt
            d.cond = "d8"                              # single-shot: governs one instruction (probe10)
        print(f"{i:5}  {img[i:i+n].hex(' '):6}  {txt}")
        i += n

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("image"); ap.add_argument("--start", type=int); ap.add_argument("--end", type=int)
    ap.add_argument("--symbols", default="auto")
    a = ap.parse_args()
    img = pathlib.Path(a.image).read_bytes(); size = len(img)
    start = a.start if a.start is not None else (4096 if size > 14000 else 1024 if size > 2000 else 512 if size == 1024 else 768)
    end = a.end or size
    syms = symbols()
    if a.symbols == "auto":
        table = data_labels(syms[3062]) if size == 3062 else data_labels(syms[2639]) if size == 2639 else dmpmap()
    elif a.symbols == "dmpmap": table = dmpmap()
    elif a.symbols == "emd": table = data_labels(syms[3062])
    elif a.symbols == "hammerhead": table = data_labels(syms[2639])
    else: table = {}
    run(img, start, end, table)
