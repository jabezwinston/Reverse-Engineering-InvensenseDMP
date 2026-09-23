#!/usr/bin/env python3
"""Lift a DMP image into C-like pseudo-code, and cross-reference its data flow.

This is a second, semantics-first pass over the same ISA that tools/isa/decode.py
renders as a listing.  decode.py answers "what is this byte"; pseudo.py answers
"what does this program compute".  The two are kept honest by --check, which
asserts they agree on every instruction length in every corpus image.

Model (see ISA2.md Findings 6-16; every rule below is hardware-confirmed unless
the comment says CONJECTURE):

    P0/P1/P2 pointers; page = 8x/9x/ax, bank = bx.  addr = bank*256 + page*16.
    low byte  v = 0 AA BB ooo  ->  M[P0+4A] <op> M[P1+4B],  op&3 = ADD/B-A/MUL/-MUL,
                                   op&4 pre-advances the P2 word index (probe32).
    dc/dd     route results to RAM / to the FIFO (sticky).
    c0..cf    MOV/MOV16 M[P0+4k] -> M[P2]; f8..fb INC/DEC; de/df CLR; d0 P2 word += 2.
    d1        Z := (result == 0); d9/da/db single-shot IF.Z / IF.NZ / IF.3.
    f4 imm    forward-only branch to site+2+imm (7-bit); f5 signed MIN prefix.

    python3 pseudo.py <image.bin> [--start N] [--end N] [--xref] [--check]

NOTE (2026-09-23): this lifter predates Findings 27-40 and has not been brought up to date.
It renders predicates as single-shot tests of a Z flag; they are sticky until the next d8-db
and test one flag F (the exact result's sign, or == 0 after d1), and `f4` 0x20-0x3f branch
backwards.  decode.py is current; read this file's output against manual chapter 2.
"""
import argparse, collections, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from symbols import symbols, dmpmap, data_labels
from decode import Decoder, Namer, lineage_of

# ---------------------------------------------------------------- conjectures
# Bytes with no hardware-confirmed meaning.  Each entry is
#   byte -> (pseudo-code rendering, one-line rationale)
# The rationale is the static evidence from the corpus; see UNKNOWNS.md.
CONJECTURE = {}     # nothing in the mantis lineage is conjectural any more (Findings 19-21)


class Lifter:
    """Walks the instruction stream keeping pointer, routing and predicate state,
    and emits one pseudo-code line per instruction that has an effect."""

    def __init__(self, img, lineage, namer):
        self.img, self.L, self.N = img, lineage, namer
        self.page = [0, 0, 0]
        self.bank = [0, 0, 0]
        self.p2off = 0
        self.ram = False            # dd/dc routing; the FIFO is the at-rest route
        self.width = None
        self.cond = None            # pending single-shot predicate
        self.minpfx = False
        self.swap = False           # fc: exchange the operand pointers for one op
        self.nostore = False        # f7 / fd: the next result is not written
        self.half = False           # f6: 16-bit store
        self.pfx = None
        self.reads = collections.Counter()
        self.writes = collections.Counter()
        self.br = 0xF4 if lineage == "mantis" else 0xFC

    # ---- addressing -------------------------------------------------------
    def ptr(self, p):
        return self.bank[p] * 256 + self.page[p] * 16 + (self.p2off if p == 2 else 0)

    def nm(self, a):
        return self.N.name(a)

    def dest(self, extra=0):
        d = self.ptr(2) + extra
        self.writes[d] += 1
        return "FIFO" if not self.ram else self.nm(d)

    def src(self, p, k):
        a = self.ptr(p) + 4 * k
        self.reads[a] += 1
        return self.nm(a)

    # ---- one instruction --------------------------------------------------
    def step(self, i):
        """Return (length, pseudo-code or None, is_control_flow)."""
        b = self.img[i]
        g = lambda s: self.guard(s)

        if b == self.br and i + 1 < len(self.img):
            imm = self.img[i + 1]
            if imm < 0x80:
                c = self.cond
                self.cond = None
                tgt = i + 2 + imm
                return 2, (f"goto L{tgt};" if c is None else f"if ({c}) goto L{tgt};"), tgt
            return 1, None, None            # bit7 set: falls through, byte executes

        fam = b >> 4
        if fam == 8:
            self.page[0] = b & 0xf; return 1, None, None
        if fam == 9:
            self.page[1] = b & 0xf; return 1, None, None
        if fam == 0xA:
            self.page[2] = b & 0xf; self.p2off = 0; return 1, None, None
        if self.L == "mantis" and fam == 0xB:
            sel, bk = (b >> 2) & 3, b & 3
            if sel < 3: self.bank[sel] = bk
            return 1, None, None
        if self.L == "3050" and 0xC0 <= b <= 0xC5:
            self.bank[(b >> 1) & 3] = b & 1; return 1, None, None

        if 0xD8 <= b <= 0xDB:
            self.cond = {0xD8: None, 0xD9: "Z", 0xDA: "!Z", 0xDB: "F3"}[b]
            return 1, None, None
        if b == 0xD1:
            return 1, g("Z = (result == 0);"), None
        if b == 0xD0:
            self.p2off = (self.p2off + 8) % 16; return 1, None, None
        if b == 0xDC:
            self.ram = True; return 1, None, None
        if b == 0xDD:
            self.ram = False; return 1, None, None
        if b in (range(0xF0, 0xF4) if self.L == "mantis" else range(0xF8, 0xFC)):
            self.width = b & 3; return 1, None, None
        if self.L == "3050" and 0xFD <= b <= 0xFF:
            # The DINAF8 family is at 0xf8 in the 3050 lineage and 0xf0 in mantis (dmpKey.h),
            # so 3050 fc..ff are mantis f4..f7; fc is already the branch on that basis.
            # 0xff cannot be halt here -- image 1024 has an unconditional one at 825 (CFG_6)
            # with FCFG_1..FCFG_3 at 868..936 still to run.  CONJECTURE, see UNKNOWNS.md.
            if b == 0xFF:
                self.nostore = True
                return 1, g(f"{self.dest()} &= 0xFFFF0000;   /* CONJECTURE: 3050 ff = mantis f7 */"), None
            self.minpfx = True
            self.half = (b == 0xFE)
            return 1, None, None
        if b == 0xFF:
            return 1, g("halt();"), None
        if b == 0xFE:
            return 1, None, None

        if b == 0xDE:                        # clear in place, no advance (probe31 B)
            return 1, g(f"{self.dest()} = 0;"), None
        if b == 0xDF:
            self.p2off = (self.p2off + 4) % 16
            return 1, g(f"{self.dest()} = 0;"), None
        if self.L == "mantis" and 0xF8 <= b <= 0xFB:
            if b & 2: self.p2off = (self.p2off + 4) % 16
            return 1, g(f"{self.dest()}{'--' if b & 1 else '++'};"), None
        if 0xC0 <= b <= 0xCF and (self.L == "mantis" or b >= 0xC8):
            k = (b >> 1) & 3
            if b & 1: self.p2off = (self.p2off + 4) % 16
            s = self.src(0, k)
            return 1, g(f"{self.dest()} = {s}{' >> 16' if b & 8 else ''};"), None
        if b == 0xF5 and self.L == "mantis":
            self.minpfx = True; return 1, None, None
        if b == 0xF6 and self.L == "mantis":            # MIN, 16-bit store (probe31/36)
            self.minpfx = True; self.half = True; return 1, None, None
        if b == 0xF7 and self.L == "mantis":            # clear the destination's low half-word
            self.nostore = True
            return 1, g(f"{self.dest()} &= 0xFFFF0000;"), None
        if b == 0xFC and self.L == "mantis":            # exchange the operand pointers (probe35)
            self.swap = True; return 1, None, None
        if b == 0xFD and self.L == "mantis":            # results are not written (probe31)
            self.nostore = True; return 1, None, None

        if b in CONJECTURE:
            self.pfx = b
            return 1, g(CONJECTURE[b][0]), None

        if b < 0x80:
            A, B, op = (b >> 5) & 3, (b >> 3) & 3, b & 7
            if self.swap:                                # fc: operand pointers exchanged
                self.swap = False
                a, bb = self.src(1, A), self.src(0, B)
            else:
                a, bb = self.src(0, A), self.src(1, B)
            if self.minpfx and op & 3 == 0:
                self.minpfx = False
                expr = f"min({a}, {bb})"
            else:
                self.minpfx = False
                expr = {0: f"{a} + {bb}", 1: f"{bb} - {a}",
                        2: f"{a} * {bb}", 3: f"-({a} * {bb})"}[op & 3]
            if self.pfx is not None:
                expr += f"   {CONJECTURE[self.pfx][0]}"
                self.pfx = None
            if op & 4:                       # pre-advance the destination word (probe32)
                self.p2off = (self.p2off + 4) % 16
            if self.nostore:                 # f7 / fd suppressed this write
                self.nostore = False
                return 1, g(f"/* {expr}; discarded */"), None
            if self.ram:
                half = self.half or self.width in (2, 3)
                self.half = False
                suffix = "" if not half else (".hi" if self.width != 3 else ".lo")
                return 1, g(f"{self.dest()}{suffix} = {expr};"), None
            w = {1: 32, 2: 16, 3: 16}.get(self.width, 32)
            return 1, g(f"fifo{w}({expr});"), None
        return 1, g(f"/* {b:02x} */"), None

    def guard(self, s):
        c, self.cond = self.cond, None
        return s if c is None else f"if ({c}) {s}"


def lift(img, start, end, table, lineage=None):
    L = lineage or lineage_of(img, start)
    lf = Lifter(img, L, Namer(table))
    out, targets = [], set()
    i = start
    while i < end:
        n, txt, tgt = lf.step(i)
        if tgt: targets.add(tgt)
        out.append((i, img[i:i + n].hex(' '), txt))
        i += n
    return lf, out, targets


def render(out, targets, show_all=False):
    for a, h, txt in out:
        if a in targets:
            print(f"\nL{a}:")
        if txt is None:
            if show_all: print(f"  {a:5} {h:6}   ;")
            continue
        print(f"  {a:5} {h:6}   {txt}")


def check(table):
    """decode.py and pseudo.py must agree on every instruction boundary."""
    bad = 0
    for p in sorted(pathlib.Path("corpus/images").glob("*.bin")):
        img = p.read_bytes(); size = len(img)
        start = 4096 if size > 14000 else 1024 if size > 2000 else 512 if size == 1024 else 768
        L = lineage_of(img, start)
        d = Decoder(img, L, Namer(table)); lf = Lifter(img, L, Namer(table))
        i = j = start
        while i < size and j < size:
            n1, _ = d.step(i)
            if not (0xD8 <= img[i] <= 0xDB): d.cond = "d8"
            n2, _, _ = lf.step(j)
            if i != j or n1 != n2:
                print(f"  MISMATCH {p.name} decode@{i}+{n1} vs pseudo@{j}+{n2}"); bad += 1; break
            i += n1; j += n2
    print("length agreement: OK" if not bad else f"{bad} images disagree")
    return bad


def xref(lf, table):
    n = Namer(table)
    print("\n; ---- data cross-reference (reads / writes) ----")
    allad = sorted(set(lf.reads) | set(lf.writes))
    for a in allad:
        print(f";  {n.name(a):<16} @{a:<5} r={lf.reads.get(a,0):<4} w={lf.writes.get(a,0)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image"); ap.add_argument("--start", type=int); ap.add_argument("--end", type=int)
    ap.add_argument("--symbols", default="auto")
    ap.add_argument("--xref", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--all", action="store_true", help="show pointer-setup lines too")
    a = ap.parse_args()
    img = pathlib.Path(a.image).read_bytes(); size = len(img)
    syms = symbols()
    table = (data_labels(syms[3062]) if size == 3062 else
             data_labels(syms[2639]) if size == 2639 else dmpmap())
    if a.symbols == "dmpmap": table = dmpmap()
    if a.check:
        sys.exit(1 if check(table) else 0)
    start = a.start if a.start is not None else (4096 if size > 14000 else 1024 if size > 2000 else 512 if size == 1024 else 768)
    end = a.end or size
    lf, out, targets = lift(img, start, end, table)
    print(f"; {pathlib.Path(a.image).name}  lineage={lf.L}  code {start}..{end}")
    render(out, targets, a.all)
    if a.xref: xref(lf, table)


if __name__ == "__main__":
    main()
