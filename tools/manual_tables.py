#!/usr/bin/env python3
"""Generate the tables in docs/manual from opendmp's instruction tables and cycle model.

Every generated table sits between markers in a chapter:

    <!-- BEGIN generated:NAME -->
    ...
    <!-- END generated:NAME -->

and this script rewrites what lies between them.  The names it knows:

    formats                 the instruction formats, as a bit-field table (checked against the decoder)
    formats-multibyte       the two- and three-byte forms
    summary-<class>         the instruction summary, one table per class
    enc-<entry>             an instruction definition's encoding, bytes and cycles
    opmap-mpu6050           the 16 x 16 opcode map, and the same for icm20948
    opmap-alu               what the ALU byte's op field means under each mode
    opmap-mode4             the mode-4 reading of bytes 00-7f
    budget                  instructions per sample period

Sources: opendmp/isa/core.py (decode, encode, cost_key) and opendmp/emu/chips.py (cycles).

    python3 tools/manual_tables.py           rewrite the generated tables
    python3 tools/manual_tables.py --check   exit 1 if any table is out of date
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / "opendmp"))
from opendmp.emu.chips import ICM20948, MPU6050          # noqa: E402
from opendmp.isa.core import Insn, cost_key, decode, encode  # noqa: E402

MANUAL = ROOT / "docs" / "manual"
MPU, ICM = "mpu6050", "icm20948"
BOTH = (MPU, ICM)
CHIP = {MPU: MPU6050, ICM: ICM20948}
NAME = {MPU: "MPU-6050", ICM: "ICM-20948"}


# --------------------------------------------------------------------------- bit fields
def fields(pattern: str) -> list[tuple[int, str]]:
    """'0 A:2 B:2 adv op:2' -> [(1, '0'), (2, 'A'), (2, 'B'), (1, 'adv'), (2, 'op')]."""
    out = []
    for tok in pattern.split():
        if ":" in tok:
            name, w = tok.rsplit(":", 1)
            out.append((int(w), name))
        else:
            out.append((1, tok))
    assert sum(w for w, _ in out) == 8, pattern
    return out


def matches(pattern: str, b: int) -> bool:
    bit = 7
    for w, name in fields(pattern):
        if name in ("0", "1"):
            if (b >> bit) & 1 != int(name):
                return False
        bit -= w
    return True


def bit_cells(pattern: str) -> str:
    return "".join(f'<td colspan="{w}">{name}</td>' if w > 1 else f"<td>{name}</td>"
                   for w, name in fields(pattern))


HEAD_BITS = "".join(f"<th>{i}</th>" for i in range(7, -1, -1))


# --------------------------------------------------------------------------- formats
# (class, format, pattern, hex, what it holds, cores, mode the decoder reads it in, ops it must decode to)
FORMATS = [
    ("Arithmetic and logic", "ALU", "0 A:2 B:2 adv op:2", "00–7F",
     "under f1–f3: add rsub mul nmul · f0: mac macn · f5–f7: clamp cmp and xor", BOTH, 1,
     {"add", "rsub", "mul", "nmul"}),
    ("Arithmetic and logic", "one-byte branch (MPU, mode 4)", "0 0 d:6", "00–3F",
     "branch.m4: to its own address + 1 + d (d signed)", (MPU,), 4, {"branch.m4"}),
    ("Arithmetic and logic", "branch target (DMP3, mode 4)", "0 call t:6", "00–7F",
     "the high byte of a jump.m4 (call = 0) or call.m4 (call = 1); the next byte is t[7:0]", (ICM,), 4,
     {"jump.m4", "call.m4"}),
    ("Pointer control", "page", "1 0 P:2 page:4", "80–AF", "p0page p1page p2page (P = 0, 1, 2)", BOTH, 1,
     {"p0page", "p1page", "p2page"}),
    ("Pointer control", "bank", "1 0 1 1 P:2 bank:2", "B0–BB", "p0bank p1bank p2bank (P = 0, 1, 2)", BOTH, 1,
     {"p0bank", "p1bank", "p2bank"}),
    ("Pointer control", "block", "1 0 1 1 1 1 P:2", "BC–BF",
     "p0blk p1blk p2blk (P = 0, 1, 2); P = 3: DMP3 movz, reserved on the MPU", BOTH, 1,
     {"p0blk", "p1blk", "p2blk", "movz", ".db"}),
    ("Data transfer", "move", "1 1 0 0 x k:2 adv", "C0–CF", "mov (x = 0), movx (x = 1): from P0's word k", BOTH, 1,
     {"mov", "movx"}),
    ("Control", "D group", "1 1 0 1 fn:4", "D0–DF",
     "p2inc2 test · MPU: clear aliases d2–d7 · DMP3: lo lo.next load · always if store fifo clr clr.next",
     BOTH, 1, None),
    ("Control", "E group", "1 1 1 0 fn:4", "E0–EF", "MPU: clear aliases · DMP3: ret (E0), int (E2), clear alias (E7)",
     BOTH, 1, None),
    ("Mode and flow", "mode", "1 1 1 1 0 m:3", "F0–F7",
     "fmode m (m ≠ 4) · F4 enters mode 4 and is the branch / jump / call prefix", BOTH, 1, None),
    ("Mode and flow", "increment", "1 1 1 1 1 0 adv dec", "F8–FB", "inc dec inc.next dec.next", BOTH, 1,
     {"inc", "dec", "inc.next", "dec.next"}),
    ("Mode and flow", "system", "1 1 1 1 1 1 fn:2", "FC–FF",
     "MPU: xchg01 xchg02 int · DMP3: the cmp.cond and shift prefixes · end (FF) on both", BOTH, 1, None),
]


def check_formats():
    """Every byte a FORMATS row covers decodes, on the cores it names, to one of its ops."""
    errors = []
    for cls, fmt, pat, hx, _, cores, mode, ops in FORMATS:
        if ops is None:
            continue
        lo, hi = (int(x, 16) for x in hx.split("–"))
        for chip in cores:
            for b in range(lo, hi + 1):
                if not matches(pat, b):
                    errors.append(f"{fmt}: byte {b:02x} is in {hx} but does not fit {pat}")
                else:
                    insn, _ = decode(bytes([b, 0x80, 0x80]), 0, chip, mode)
                    if insn.op not in ops:
                        errors.append(f"{fmt} on {chip}: byte {b:02x} decodes as {insn.op}")
    return errors


def gen_formats() -> str:
    rows = [f"<table>\n<tr><th>Class</th><th>Format</th>{HEAD_BITS}<th>Hex</th><th>Instructions</th></tr>"]
    spans = {}
    for cls, *_ in FORMATS:
        spans[cls] = spans.get(cls, 0) + 1
    seen = set()
    for cls, fmt, pat, hx, what, *_ in FORMATS:
        head = "" if cls in seen else f'<td rowspan="{spans[cls]}">{cls}</td>'
        seen.add(cls)
        rows.append(f"<tr>{head}<td>{fmt}</td>{bit_cells(pat)}<td>{hx}</td><td>{what}</td></tr>")
    rows.append("</table>")
    return "\n".join(rows)


MULTIBYTE = [
    ("MPU-6050", "branch", ["1 1 1 1 0 1 0 0", "0 0 d:6"], "F4 00–3F",
     "to the F4's address + 2 + d, d a signed 6-bit displacement"),
    ("MPU-6050", "int.f4", ["1 1 1 1 0 1 0 0", "0 1 n:6"], "F4 41–7F",
     "n with a non-zero low five bits: raise DMP_INT; F4 40: nothing (nop.f440); F4 60: reserved"),
    ("MPU-6050", "nop.f4", ["1 1 1 1 0 1 0 0"], "F4 + byte ≥ 80",
     "one byte: enters mode 4; the next byte is the next instruction"),
    ("ICM-20948", "jump / call", ["1 1 1 1 0 1 0 0", "0 call t13–t8:6", "t7–t0:8"], "F4 00–7F xx",
     "to t, absolute; call = 1 pushes the address after the instruction"),
    ("ICM-20948", "mode4", ["1 1 1 1 0 1 0 0"], "F4 + byte ≥ 80", "one byte: enters mode 4"),
    ("ICM-20948", "cmp.cond", ["1 1 1 1 1 1 0 0", "1 1 0 0 0 0 k:2", "t:6 c:2"], "FC C0–C3 xx",
     "F := (P1 word k & 0x3F) cond t, cond c = 0 ==, 1 >, 2 <, 3 ≠"),
    ("ICM-20948", "shl / sar", ["1 1 1 1 1 1 0 1", "0 adv r s:5"], "FD 01–7F",
     "r = 0: shl s (s = 1–31); r = 1: sar 32 − s (s = 0 gives sar 32)"),
]


def gen_formats_multibyte() -> str:
    rows = [f"<table>\n<tr><th>Core</th><th>Instruction</th><th>Byte</th>{HEAD_BITS}<th>Hex</th><th>Meaning</th></tr>"]
    for core, insn, pats, hx, what in MULTIBYTE:
        n = len(pats)
        for i, pat in enumerate(pats):
            lead = (f'<td rowspan="{n}">{core}</td><td rowspan="{n}">{insn}</td>' if i == 0 else "")
            tail = (f'<td rowspan="{n}">{hx}</td><td rowspan="{n}">{what}</td>' if i == 0 else "")
            rows.append(f"<tr>{lead}<td>{i + 1}</td>{bit_cells(pat)}{tail}</tr>")
    rows.append("</table>")
    return "\n".join(rows)


# --------------------------------------------------------------------------- instruction entries
class Form:
    """One encoding of an entry: its syntax, bit pattern(s), an example for bytes and cycles,
    the modes it is timed in, the cores that have it, and a summary line."""

    def __init__(self, syntax, patterns, example, modes=((None, 1),), cores=BOTH, desc="", f="—", r="—",
                 cycles=None):
        self.syntax, self.patterns, self.example = syntax, patterns, example
        self.modes, self.cores, self.desc, self.f, self.r = modes, cores, desc, f, r
        self.cycles = cycles or {}               # chip -> text, where the model cannot say


ARITH_MODES = (("32-bit", 1), ("lane", 3))
LOGIC_MODES = (("32-bit", 5), ("lane", 7))
LANE_INC = (("32-bit", 1), ("lane", 3))
A = "0 A:2 B:2 adv"

ENTRIES = {
    "add": [Form("add A,B[,inc]", [f"{A} 0 0"], Insn("add", (0, 0, False)), ARITH_MODES,
                 desc="R := A + B; store or emit", f="exact sign", r="written")],
    "rsub": [Form("rsub A,B[,inc]", [f"{A} 0 1"], Insn("rsub", (0, 0, False)), ARITH_MODES,
                  desc="R := B − A; store or emit", f="exact sign", r="written")],
    "mul": [Form("mul A,B[,inc]", [f"{A} 1 0"], Insn("mul", (0, 0, False)), ARITH_MODES,
                 desc="R := A·B; store ⌊A·B / 2³⁰⌋", f="exact sign", r="written")],
    "nmul": [Form("nmul A,B[,inc]", [f"{A} 1 1"], Insn("nmul", (0, 0, False)), ARITH_MODES,
                  desc="R := −A·B; store ⌊−A·B / 2³⁰⌋", f="exact sign", r="written")],
    "mac": [Form("mac A,B[,inc]", [f"{A} x 0"], Insn("mac", (0, 0, False)), (("f0", 0),),
                 desc="R := R + A·B; store ⌊R / 2³⁰⌋", f="sign of R", r="accumulated")],
    "macn": [Form("macn A,B[,inc]", [f"{A} x 1"], Insn("macn", (0, 0, False)), (("f0", 0),),
                  desc="R := R − A·B; store ⌊R / 2³⁰⌋", f="sign of R", r="accumulated")],
    "inc": [Form("inc / inc.next", ["1 1 1 1 1 0 next 0"], Insn("inc"), LANE_INC,
                 desc="M[P2] + 1 LSB of the lane, through the route", f="exact sign", r="written")],
    "dec": [Form("dec / dec.next", ["1 1 1 1 1 0 next 1"], Insn("dec"), LANE_INC,
                 desc="M[P2] − 1 LSB of the lane, through the route", f="exact sign", r="written")],
    "clamp": [Form("clamp A,B[,inc]", [f"{A} 0 0"], Insn("clamp", (0, 0, False)), LOGIC_MODES,
                   desc="A clamped to [−B, B]; store", f="A was clamped", r="the compare D")],
    "cmp": [Form("cmp A,B", [f"{A} 0 1"], Insn("cmp", (0, 0, False)), LOGIC_MODES,
                 desc="F := A < 0 ≤ B; nothing stored", f="sign test", r="—")],
    "and": [Form("and A,B[,inc]", [f"{A} 1 0"], Insn("and", (0, 0, False)), LOGIC_MODES,
                 desc="A AND B; store", f="—", r="—")],
    "xor": [Form("xor A,B[,inc]", [f"{A} 1 1"], Insn("xor", (0, 0, False)), LOGIC_MODES,
                 desc="A XOR B; store", f="—", r="—")],
    "test": [Form("test", ["1 1 0 1 0 0 0 1"], Insn("test"), desc="F := (R's word == 0), at the lane",
                  f="R == 0", r="—")],
    "cmp.cond": [Form("cmp.eq / gt / lt / ne k,t", ["1 1 1 1 1 1 0 0", "1 1 0 0 0 0 k:2", "t:6 c:2"],
                      Insn("cmp.eq", (0, 0)), cores=(ICM,), desc="F := (P1 word k & 0x3F) cond t",
                      f="the compare", r="—")],
    "mov": [Form("mov k[,inc]", ["1 1 0 0 0 k:2 adv"], Insn("mov", (0, False)), ARITH_MODES,
                 desc="P0 word k, through the route", r="—")],
    "movx": [Form("movx k[,inc]", ["1 1 0 0 1 k:2 adv"], Insn("movx", (0, False)), ARITH_MODES,
                  desc="P0 word k with its half-words exchanged", r="—")],
    "clr": [Form("clr", ["1 1 0 1 1 1 1 0"], Insn("clr"), desc="M[P2] := 0", r="—"),
            Form("clr.d2 … clr.d7 (MPU), clr.e0 … clr.ef (MPU), clr.e7 (DMP3)", ["1 1 1 0 n:4"],
                 Insn("clr.e7"), desc="clear aliases", r="—",
                 cycles={MPU: "28", ICM: "26"})],
    "clr.next": [Form("clr.next", ["1 1 0 1 1 1 1 1"], Insn("clr.next"), desc="P2.w += 1; M[P2] := 0",
                      r="MPU: zeroed")],
    "movz": [Form("movz", ["1 0 1 1 1 1 1 1"], Insn("movz"), cores=(ICM,), desc="toggle: MOV stores a FIFO-dependent value (do not use)")],
    "lo": [Form("lo / lo.next", ["1 1 0 1 0 0 1 next"], Insn("lo"), cores=(ICM,),
                desc="store R's low 30 bits, sign-extended", r="—")],
    "load": [Form("load k", ["1 1 0 1 0 1 k:2"], Insn("load", (0,)), cores=(ICM,),
                  desc="shifter := P0's page; select word k", r="the word")],
    "shift": [Form("shl s[,adv] / sar s[,adv]", ["1 1 1 1 1 1 0 1", "0 adv r s:5"], Insn("shl", (1, False)),
                   cores=(ICM,), desc="shift the shifter; store the selected word", r="the word")],
    "page": [Form("p0page n / p1page n / p2page n", ["1 0 P:2 page:4"], Insn("p0page", (0,)),
                  desc="Pn.page := n (p2page also sets P2.w := 0)", r="MPU p2page: zeroed")],
    "bank": [Form("p0bank n / p1bank n / p2bank n", ["1 0 1 1 P:2 bank:2"], Insn("p0bank", (0,)),
                  desc="Pn.bank := n", r="MPU p2bank: zeroed")],
    "blk": [Form("p0blk / p1blk / p2blk", ["1 0 1 1 1 1 P:2"], Insn("p0blk"),
                 desc="Pn.block += 1 (MPU mod 3, DMP3 mod 4)")],
    "p2inc2": [Form("p2inc2", ["1 1 0 1 0 0 0 0"], Insn("p2inc2"), desc="P2.w += 2", r="MPU: zeroed")],
    "xchg01": [Form("xchg01", ["1 1 1 1 1 1 0 0"], Insn("xchg01"), cores=(MPU,),
                    desc="toggle: A and MOV through P1, B through P0")],
    "xchg02": [Form("xchg02", ["1 1 1 1 1 1 0 1"], Insn("xchg02"), cores=(MPU,),
                    desc="toggle: A and MOV through P2, store through P0")],
    "store": [Form("store", ["1 1 0 1 1 1 0 0"], Insn("store"), desc="route := RAM")],
    "fifo": [Form("fifo", ["1 1 0 1 1 1 0 1"], Insn("fifo"), desc="route := FIFO")],
    "always": [Form("always", ["1 1 0 1 1 0 0 0"], Insn("always"), desc="disarm the predicate")],
    "if": [Form("if f / if nf / if f.alt", ["1 1 0 1 1 0 c:2"], Insn("if f"),
                desc="arm: run while F / while not F")],
    "fmode": [Form("fmode m", ["1 1 1 1 0 m:3"], Insn("fmode", (1,)), desc="mode := m (m ≠ 4)")],
    "mode4": [Form("mode4 (DMP3), nop.f4 (MPU)", ["1 1 1 1 0 1 0 0"], Insn("mode4"),
                   desc="mode := 4; next byte ≥ 0x80 runs"),
              Form("nop.f440", ["1 1 1 1 0 1 0 0", "0 1 0 0 0 0 0 0"], Insn("nop.f440"), cores=(MPU,),
                   desc="mode := 4, nothing else", cycles={MPU: "10"})],
    "branch": [Form("branch t", ["1 1 1 1 0 1 0 0", "0 0 d:6"], Insn("branch", (2,)), cores=(MPU,),
                    desc="PC := PC + 2 + d; mode := 4", cycles={MPU: "15 taken, 10 skipped"}),
               Form("branch.m4 t", ["0 0 d:6"], Insn("branch.m4", (1,)), cores=(MPU,),
                    modes=(("mode 4", 4),), desc="in mode 4: PC := PC + 1 + d",
                    cycles={MPU: "10 taken, 5 skipped"})],
    "jump": [Form("jump t", ["1 1 1 1 0 1 0 0", "0 0 t:6", "t:8"], Insn("jump", (0,)), cores=(ICM,),
                  desc="PC := t; mode := 4", cycles={ICM: "13 taken, 12 skipped"}),
             Form("jump.m4 t", ["0 0 t:6", "t:8"], Insn("jump.m4", (0,)), cores=(ICM,),
                  modes=(("mode 4", 4),), desc="in mode 4: PC := t", cycles={ICM: "9"})],
    "call": [Form("call t", ["1 1 1 1 0 1 0 0", "0 1 t:6", "t:8"], Insn("call", (0,)), cores=(ICM,),
                  desc="push PC + 3; PC := t; mode := 4", cycles={ICM: "13"}),
             Form("call.m4 t", ["0 1 t:6", "t:8"], Insn("call.m4", (0,)), cores=(ICM,),
                  modes=(("mode 4", 4),), desc="in mode 4: push PC + 2; PC := t", cycles={ICM: "9"})],
    "ret": [Form("ret", ["1 1 1 0 0 0 0 0"], Insn("ret"), cores=(ICM,), desc="PC := pop")],
    "end": [Form("end", ["1 1 1 1 1 1 1 1"], Insn("end"), desc="end the pass",
                 cycles={MPU: "—", ICM: "—"})],
    "int": [Form("int", ["1 1 1 1 1 1 1 0"], Insn("int"), cores=(MPU,), desc="raise DMP_INT"),
            Form("int", ["1 1 1 0 0 0 1 0"], Insn("int"), cores=(ICM,), desc="raise DMP_INT1"),
            Form("int.f4 n", ["1 1 1 1 0 1 0 0", "0 1 n:6"], Insn("int.f4", (0x41,)), cores=(MPU,),
                 desc="raise DMP_INT; mode := 4", cycles={MPU: "10"})],
}

SUMMARY = {
    "arith": ["add", "rsub", "mul", "nmul", "mac", "macn", "inc", "dec"],
    "logic": ["clamp", "cmp", "and", "xor", "test", "cmp.cond"],
    "transfer": ["mov", "movx", "clr", "clr.next", "movz", "lo", "load", "shift"],
    "pointer": ["page", "bank", "blk", "p2inc2", "xchg01", "xchg02"],
    "route": ["store", "fifo", "always", "if"],
    "flow": ["fmode", "mode4", "branch", "jump", "call", "ret", "int", "end"],
}


def cycles_text(form: Form, chip: str) -> str:
    if chip not in form.cores:
        return "—"
    if chip in form.cycles:
        return form.cycles[chip]
    c = CHIP[chip]
    ins = Insn("nop.f4") if chip == MPU and form.example.op == "mode4" else form.example
    vals = [(label, c.cyc(cost_key(ins, mode))) for label, mode in form.modes]
    if len({n for _, n in vals}) == 1:
        return str(vals[0][1])
    return ", ".join(str(n) if i == 0 else f"{label} {n}" for i, (label, n) in enumerate(vals))


def bytes_text(form: Form, chip: str) -> str:
    if chip not in form.cores:
        return "—"
    return str(len(form.patterns))


def enc_table(form: Form) -> str:
    rows = [f"<table>\n<tr><th>{form.syntax}</th>{HEAD_BITS}</tr>"]
    for i, pat in enumerate(form.patterns):
        label = "byte 1" if len(form.patterns) == 1 else f"byte {i + 1}"
        rows.append(f"<tr><td>{label}</td>{bit_cells(pat)}</tr>")
    rows.append("</table>")
    return "\n".join(rows)


def gen_enc(entry: str) -> str:
    out = []
    for form in ENTRIES[entry]:
        out.append(enc_table(form))
        out.append("")
        out.append("| | MPU-6050 | ICM-20948 |\n|---|---|---|")
        out.append(f"| Bytes | {bytes_text(form, MPU)} | {bytes_text(form, ICM)} |")
        out.append(f"| Cycles | {cycles_text(form, MPU)} | {cycles_text(form, ICM)} |")
        out.append("")
    return "\n".join(out).rstrip()


def gen_summary(cls: str) -> str:
    out = ["| Mnemonic | Operation | Bytes | Cycles MPU | Cycles ICM | F | R |",
           "|---|---|---:|---|---|---|---|"]
    for entry in SUMMARY[cls]:
        for form in ENTRIES[entry]:
            nbytes = len(form.patterns)
            cores = "" if form.cores == BOTH else (" (MPU)" if form.cores == (MPU,) else " (DMP3)")
            out.append(f"| [`{form.syntax}`](05-instruction-definitions.md#{anchor(entry)}){cores} | {form.desc} | "
                       f"{nbytes} | {cycles_text(form, MPU)} | {cycles_text(form, ICM)} | {form.f} | {form.r} |")
    return "\n".join(out)


def anchor(entry: str) -> str:
    return "i-" + entry.replace(".", "-")


# --------------------------------------------------------------------------- opcode maps
def short(insn: Insn) -> str:
    op, a = insn.op, insn.args
    if op == ".db":
        return "—"
    if op in ("add", "rsub", "mul", "nmul") or op in ("mov", "movx"):
        *ops, adv = a
        return f"{op} {','.join(str(x) for x in ops)}" + ("+" if adv else "")
    if op.endswith(("page", "bank")):
        return f"{op} {a[0]}"
    if op == "fmode":
        return f"fmode {a[0]}"
    if op == "load":
        return f"load {a[0]}"
    if op in ("nop.f4", "mode4", "branch", "jump", "call", "int.f4", "nop.f440"):
        return "F4 prefix"
    if op.startswith("cmp.") or (op == ".db" and a[:1] == (0xFC,)):
        return "cmp.cond"
    if op in ("shl", "sar"):
        return "shl/sar"
    return op


def gen_opmap(chip: str) -> str:
    rows = ["| | " + " | ".join(f"x{i:X}" for i in range(16)) + " |", "|---" * 17 + "|"]
    for hi in range(16):
        cells = []
        for lo in range(16):
            b = hi << 4 | lo
            buf = bytes([b, 0x00, 0x00]) if b in (0xF4, 0xFC, 0xFD) else bytes([b, 0x80, 0x80])
            if chip == ICM and b == 0xFC:
                buf = bytes([0xFC, 0xC0, 0x00])
            if chip == ICM and b == 0xFD:
                buf = bytes([0xFD, 0x01])
            insn, _ = decode(buf, 0, chip, 1)
            cells.append(short(insn))
        rows.append(f"| **{hi:X}x** | " + " | ".join(cells) + " |")
    return "\n".join(rows)


def gen_opmap_alu() -> str:
    out = ["| op field | `fmode 0` | `fmode 1`–`3` | `fmode 5`–`7` |", "|---|---|---|---|"]
    for op in range(4):
        out.append(f"| {op} (`{op:02b}`) | {decode(bytes([op]), 0, MPU, 0)[0].op} | "
                   f"{decode(bytes([op]), 0, MPU, 1)[0].op} | {decode(bytes([op]), 0, MPU, 5)[0].op} |")
    return "\n".join(out)


def gen_opmap_mode4() -> str:
    return ("| Bytes in mode 4 | MPU-6050 | ICM-20948 |\n|---|---|---|\n"
            "| 00–3F | `branch.m4`: one byte, to its address + 1 + d (d = the byte, signed 6-bit) | "
            "`jump.m4`: the high byte of a two-byte absolute target |\n"
            "| 40–7F | reserved: no branch, no interrupt | `call.m4`: the high byte of a two-byte call target |\n"
            "| 80–FF | as in any mode | as in any mode, except that `p0page`/`p1page`/`p2page` select the I/O space |")


# --------------------------------------------------------------------------- budget
def gen_budget() -> str:
    out = ["| Sample rate | Period | MPU-6050: cycles | ADDs | MOVs | ICM-20948: cycles | ADDs | MOVs |",
           "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for rate in (1000, 500, 200, 100, 50):
        period = 1 / rate
        row = [f"{rate} Hz", f"{period * 1e3:g} ms"]
        for chip in BOTH:
            c = CHIP[chip]
            cyc = int(period * c.clock_hz) - c.start_cycles
            row += [f"{cyc:,}", f"{cyc // c.cyc('add'):,}", f"{cyc // c.cyc('mov'):,}"]
        out.append("| " + " | ".join(row) + " |")
    return "\n".join(out)


# --------------------------------------------------------------------------- driver
def generators() -> dict:
    g = {"formats": gen_formats, "formats-multibyte": gen_formats_multibyte,
         "opmap-mpu6050": lambda: gen_opmap(MPU), "opmap-icm20948": lambda: gen_opmap(ICM),
         "opmap-alu": gen_opmap_alu, "opmap-mode4": gen_opmap_mode4, "budget": gen_budget}
    for cls in SUMMARY:
        g[f"summary-{cls}"] = (lambda c=cls: gen_summary(c))
    for entry in ENTRIES:
        g[f"enc-{entry}"] = (lambda e=entry: gen_enc(e))
    return g


BLOCK = re.compile(r"(<!-- BEGIN generated:([\w.-]+) -->\n)(.*?)(<!-- END generated:\2 -->)", re.S)


def process(check: bool) -> int:
    errors = check_formats()
    for e in errors:
        print("formats:", e)
    gens = generators()
    stale, used = [], set()
    for path in sorted(MANUAL.glob("*.md")):
        text = path.read_text()

        def repl(m):
            name = m.group(2)
            used.add(name)
            if name not in gens:
                errors.append(f"{path.name}: unknown generated block {name!r}")
                return m.group(0)
            return m.group(1) + gens[name]() + "\n" + m.group(4)
        new = BLOCK.sub(repl, text)
        if new != text:
            stale.append(path.name)
            if not check:
                path.write_text(new)
    for e in errors:
        print(e)
    if check and stale:
        print("out of date:", ", ".join(stale))
    return 1 if errors or (check and stale) else 0


if __name__ == "__main__":
    sys.exit(process("--check" in sys.argv))
