#!/usr/bin/env python3
"""Annotated DMP decoder under the pointer model (2026-09-08).

    8x  P0.page = x        bx (mantis) sel=bits[3:2] -> pointer, bank=bits[1:0]
    9x  P1.page = x        cx (3050)   sel=bits[2:1] -> pointer, bank=bit0   (c0..c5)
    ax  P2.page = x
    low byte v = 0 AA BB ooo :  A-word = P0 + 4*AA, B-word = P1 + 4*BB, op = ooo
                                 (bench: emitted value = M[B-word] + M[A-word] in FIFO mode)
    f4 imm (mantis) / fc imm (3050): branch to site+2+imm   [proven vs eMD labels]
    d8/d9/da/db: predicate prefixes (d8 = always)          [corpus structure, unverified]
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
        self.cond = "d8"; self.width = None
        if lineage == "mantis":
            self.br = 0xF4; self.bankfam = 0xB; self.fmode = range(0xF0, 0xF4)
        else:
            self.br = 0xFC; self.bankfam = None; self.fmode = range(0xF8, 0xFC)
    def ptr(self, p): return self.bank[p] * 256 + self.page[p] * 16
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
        if fam == 0xA: self.page[2] = b & 0xf; return 1, f"P2.page={b&0xf:x}   -> D@{self.ptr(2)} {self.N.name(self.ptr(2))}"
        if L == "mantis" and fam == 0xB:
            sel, bank = (b >> 2) & 3, b & 3
            if sel < 3: self.bank[sel] = bank; return 1, f"P{sel}.bank={bank}"
            return 1, f"bank-sel3 {bank}   ; unknown"
        if L == "3050" and 0xC0 <= b <= 0xC5:
            sel, bank = (b >> 1) & 3, b & 1
            self.bank[sel] = bank; return 1, f"P{sel}.bank={bank}"
        if 0xD8 <= b <= 0xDB:
            self.cond = f"{b:02x}"; return 1, {0xD8: "ALWAYS", 0xD9: "IF.1", 0xDA: "IF.2", 0xDB: "IF.3"}[b]
        if b in self.fmode:
            self.width = b & 3; return 1, f"FMODE.{b&3}   ; 1=32-bit fifo, 2/3=16-bit"
        if b < 0x80:
            A, B, op = (b >> 5) & 3, (b >> 3) & 3, b & 7
            a, bb, d = self.ptr(0) + 4 * A, self.ptr(1) + 4 * B, self.ptr(2) + 4 * B
            pre = "" if self.cond == "d8" else f"[{self.cond}] "
            ALU = {0: "ADD", 1: "RSUB", 2: "MUL", 3: "NMUL"}[op & 3]
            dst = "P2+4" if op & 4 else "P2"
            return 1, f"{pre}{ALU} A={self.N.name(a):<12} B={self.N.name(bb):<12} -> {dst} (via dc)"
        return 1, f"{b:02x}"

def run(img, start, end, table):
    L = lineage_of(img, start)
    d = Decoder(img, L, Namer(table))
    print(f"; lineage={L} start={start}")
    i = start
    while i < end:
        n, txt = d.step(i)
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
