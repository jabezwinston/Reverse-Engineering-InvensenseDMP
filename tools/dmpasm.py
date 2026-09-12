#!/usr/bin/env python3
"""dmpasm - assembler for the recovered InvenSense DMP ISA (2026-09-08).

The DMP is a Q30 fixed-point machine with pointer-addressed load/store, a small
ALU, and a forward branch (ISA2.md, Findings 1-7, hardware-confirmed). This
assembler emits only instructions verified on silicon; use `.db` for anything else.

Machine model
-------------
Three pointers P0, P1, P2. address(P) = bank*256 + page*16.  A word is 4 bytes,
big-endian Q30 (2^30 = 1.0), range [-2,+2), addition wraps (modular).

  p0page N / p1page N / p2page N     high nibble 8/9/A, low nibble = page (0..15)
  p0bank N / p1bank N / p2bank N     mantis: b-family; 3050: c-family
  add   A,B[,inc]                     M[P0+4A] + M[P1+4B]   (A,B in 0..3)
  rsub  A,B[,inc]                     M[P1+4B] - M[P0+4A]   (op1)
  mul   A,B[,inc]                     M[P0+4A] * M[P1+4B]   (op2)
  nmul  A,B[,inc]                    -M[P0+4A] * M[P1+4B]   (op3)
       `inc` sets op&4, which pre-advances the P2 word index by one before the
       store (Finding 17; `hi` is accepted as the old spelling). Use `p2inc` (df)
       to reach words 2,3 of the page.
  min   A,B[,inc]                     f5 + ALU: signed min(M[P0+4A], M[P1+4B])
  store                              dc: RAM routing ON  (sticky; every following ALU op stores)
  fifo  (alias store.off)            dd: route results to the FIFO (sticky; the at-rest
                                     routing). Vendor packet emit = dd f1 <ALU ops>
  p2inc [N]                          df: P2 += 4, N times. Reaches words 2,3 of a page
  store.add / store.rsub / .mul / .nmul  A,B[,inc]
       fused: emits `dc` THEN the ALU byte, the order confirmed on hardware
       (probe6: dc precedes the op). This is the RAM-store idiom.
  branch N                           f4 (mantis) / fc (3050); target = here+2+N,
                                     forward only, 0 <= N <= 0x7f (Finding 2)
  fmode N                            f0..f3 store width; applies to RAM as well as the FIFO
       (Finding 21)  1 = 32-bit, 2 = upper half-word, 3 = lower half-word,
       0 = the A operand contributes 0 for the next op only
  min16 A,B[,inc]                    f6 + ALU: signed min, 16-bit store (upper half-word)
  trunc                              f7: M[P2] &= 0xffff0000, and the next ALU op does not store
  xchg01 (alias swap)                fc: TOGGLE -- A and MOV sources through P1, B through P0, until the next fc
  xchg02                             fd: TOGGLE -- A and MOV sources through P2, stores into P0's page, until the next fd
  test                               d1: clears N (Z := result == 0 stays)
  if le0 / if ge0 (= if z / if nz)   d9 / da: STICKY -- run everything up to the next always/if
                                     while the last result was <= 0 / >= 0 (after test: == 0 / always)
  always / if 3                      d8 / db (db = d9)
  Every ALU op, inc and dec sets N and Z -- but not while a predicate is armed (probe67/68).
  clr.next                           df: P2 word++, then M[P2] := 0   (p2inc [N] = N of these)
  inc / dec                          f8 / f9: M[P2] += 1 / -= 1 (one LSB)
  inc.next / dec.next                fa / fb: P2 word++, then INC / DEC
  p2inc2                             d0: P2 word += 2, mod 4
  mov k[,inc]                        c0..c7: copy M[P0+4k] -> M[P2]; inc pre-advances P2
  mov16 k[,inc]                      c8..cf: copy the word with its half-words exchanged (MOVX; the name is the vendor's)

Legacy FIFO-emit form (stock preambles) still assembles:
  selbank gyro|quat|accel|delay|0x9N
  emit r0..r15 | gyro_x ... | 0xNN
  nop / skip (fe) / disable (ff, halts) / .db 0x..,0x..

A bare ALU op with no `store` and no `dc` emits its result to the FIFO when a
FIFO mode is active (bench round 10); with `store`/dc it writes RAM instead.

DMP3 / ICM-20948 forms (`.lineage icm`; manual chapter 8, ISA2.md Findings 24-26)
------------------------------------------------------------------------------
  .org ADDR                          where the code will live (default 0x1000, the entry point)
  label:                             a code label (its own line, or before an instruction)
  jump LABEL|ADDR                    f4 hi lo: 16-bit absolute jump.  Enters mode 4.
  call LABEL|ADDR                    f4 hi lo with bit 14: call; `ret` (e0) returns
  ret                                e0
  mode4                              a bare f4 (no target): enter mode 4 without jumping
  if f / if nf                       d9 / da on DMP3: F = sign of the last result (== 0 after test)
       Predicates are STICKY on DMP3: a false one skips everything up to the next always/if.
  p0blk / p1blk / p2blk              bc / bd / be: add 1 KB (mod 4) to that pointer
  load k                             d4..d7: load the 4-word shifter from P0, select word k
  shl s[,adv] / sar s[,adv]          fd n: shift the register left by s (1..31, pulling the next
                                     word's fraction in) or arithmetic right by s (1..32) and
                                     store the selected word; adv pre-advances P2.  The register
                                     holds the last ALU result (a MUL's full 64-bit product) or
                                     the words a `load k` fetched, whichever came last; shifts compound
  lo / lo.next                       d2 / d3: store the low word of the last product
  int                                e2: raise DMP_INT1
  clr                                de: M[P2] := 0 in place  (e7 is the same)
  tz k / tnz k                       fc cK 00/01: F := (P1 word k == 0) / (!= 0), nothing stored --
                                     the vendor's feature gate: `tz 0` / `if f` / `jump skip`.
The flag F is updated by ALU ops, inc and dec ONLY while no predicate is armed (after
`always`); `test`, `tz` and `tnz` update it regardless.  So a loop's counter must be decremented
under `always`: `always` / `dec` / `if nf` / `jump loop` (programs/loop_icm.s).
Mode 4 rule: after any jump/call/mode4 every byte below 0x80 is a branch target, not an ALU
op, until a width byte (fmode / f5 / min16 / trunc) ends the mode -- so every jump target and
every instruction after a call must start with one.  The assembler refuses an ALU op, mov16
operand or `.db` low byte while mode 4 is armed and warns about a target that lacks one.
`branch` (the 7-bit relative form) does not exist on DMP3.

Patching
--------
  python3 dmpasm.py prog.s --patch image.bin --at 1868 --len 5 --out out.bin
`--len` is the site capacity; the fragment is NOP-padded, overruns refused.
"""
import argparse, re, sys, pathlib

# lineage-specific opcodes
LINEAGES = {
    "mantis": dict(emit=0xF1, branch=0xF4, fmode0=0xF0, bankbase=0xB0, bankstyle="b"),
    "6050":   dict(emit=0xF1, branch=0xF4, fmode0=0xF0, bankbase=0xB0, bankstyle="b"),
    "3050":   dict(emit=0xF9, branch=0xFC, fmode0=0xF8, bankbase=0xC0, bankstyle="c"),
    "icm":    dict(emit=0xF1, branch=0xF4, fmode0=0xF0, bankbase=0xB0, bankstyle="b"),   # DMP3 (ICM-20948)
}
ICM_ORG = 0x1000                  # DMP3 entry point; `.org` overrides
STORE = 0xDC                      # DINADC: commit ALU result to M[dest]
ALU_OPS = {"add": 0, "rsub": 1, "mul": 2, "nmul": 3}
NOP, SKIP, DISABLE = 0xA3, 0xFE, 0xFF
BANK_ALIAS = {"gyro": 0x9A, "quat": 0x9C, "accel": 0x99, "delay": 0x98}
REGS = {
    0x9A: {"gyro_x": 0x28, "gyro_y": 0x30, "gyro_z": 0x38},
    0x9C: {"quat_w": 0x20, "quat_x": 0x28, "quat_y": 0x30, "quat_z": 0x38},
    0x99: {"accel_x": 0x28, "accel_y": 0x30, "accel_z": 0x38},
    0x98: {"delay_t": 0x28, "delay_t1": 0x38},
}


class AsmError(Exception):
    pass


def _page_byte(hi_nibble, arg):
    n = int(arg, 0)
    if not 0 <= n <= 15:
        raise AsmError(f"page {n} out of range 0-15")
    return (hi_nibble << 4) | n


def _bank_byte(L, sel, arg):
    n = int(arg, 0)
    if L["bankstyle"] == "b":                 # mantis: 0xB0 | (sel<<2) | bank, bank 0..3
        if not 0 <= n <= 3:
            raise AsmError(f"bank {n} out of range 0-3 (mantis)")
        return L["bankbase"] | (sel << 2) | n
    else:                                      # 3050: 0xC0 | (sel<<1) | bank, bank 0..1
        if not 0 <= n <= 1:
            raise AsmError(f"bank {n} out of range 0-1 (3050)")
        return L["bankbase"] | (sel << 1) | n


def _alu_byte(op, arg):
    """Parse `A,B[,inc]` -> (A<<5)|(B<<3)|op(|4).

    The third operand sets op&4, which PRE-ADVANCES the P2 word index by one
    (mod 4) before the store -- it is not a fixed "P2+4" destination, see
    ISA2.md Finding 17.  From a freshly loaded P2 the two are identical, which
    is why the older spelling `hi` is still accepted."""
    toks = [t.strip() for t in arg.split(",") if t.strip()]
    if len(toks) < 2:
        raise AsmError(f"{op!r} needs A,B (0..3) and optional inc")
    A, B = int(toks[0], 0), int(toks[1], 0)
    if not (0 <= A <= 3 and 0 <= B <= 3):
        raise AsmError(f"operand index out of range 0-3: A={A} B={B}")
    adv = 0
    if len(toks) >= 3 and toks[2].lower() in ("inc", "adv", "hi", "1", "d1", "p2+4"):
        adv = 4
    return (A << 5) | (B << 3) | ALU_OPS[op] | adv


def assemble(text, lineage="mantis", warn=None):
    L = LINEAGES[lineage]
    out = bytearray()
    bank = None
    org = ICM_ORG
    labels, fixups, targets = {}, [], []          # icm: label -> offset; (offset, name, lineno); target offsets
    mode4 = False                                 # icm: armed by jump/call/mode4, cleared by f0-f7
    warn = warn or (lambda m: print("warning:", m, file=sys.stderr))

    def icm_only(what):
        if lineage != "icm":
            raise AsmError(f"{what} is a DMP3 (icm) form; add `.lineage icm`")

    def low_byte(what):
        if lineage == "icm" and mode4:
            raise AsmError(f"{what} while mode 4 is armed: bytes below 0x80 are branch targets here; "
                           "put an fmode/min/trunc first (the vendor's `d8 f1` at every target)")

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split(";")[0].strip()
        if not line:
            continue
        m = re.match(r"([A-Za-z_]\w*):\s*(.*)", line)
        if m and m.group(1).lower() not in ("store", "if"):
            icm_only("labels")
            if m.group(1) in labels:
                raise AsmError(f"line {lineno}: duplicate label {m.group(1)!r}")
            labels[m.group(1)] = len(out)
            line = m.group(2).strip()
            if not line:
                continue
        parts = line.split(None, 1)
        op = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""
        try:
            if op == ".lineage":
                if arg not in LINEAGES:
                    raise AsmError(f"unknown lineage {arg!r}")
                L = LINEAGES[lineage := arg]
            elif op == ".org":
                icm_only(".org"); org = int(arg, 0)
            elif op == ".db":
                for tok in arg.split(","):
                    v = int(tok.strip(), 0) & 0xFF
                    if v < 0x80: low_byte(f".db {v:#04x}")
                    out.append(v)

            # --- DMP3 control flow and extras (icm) ---
            elif op in ("jump", "call"):
                icm_only(op)
                if re.fullmatch(r"[A-Za-z_]\w*", arg) and not re.fullmatch(r"0[xX][0-9a-fA-F]+", arg):
                    fixups.append((len(out) + 1, arg, lineno, op))
                    out += bytes([L["branch"], 0, 0])
                else:
                    t = int(arg, 0)
                    if not 0 <= t <= 0x3FFF: raise AsmError(f"{op} target {t:#x} is outside the 16 KB")
                    targets.append(t)
                    t |= 0x4000 if op == "call" else 0
                    out += bytes([L["branch"], t >> 8, t & 0xFF])
                mode4 = True
            elif op == "ret":
                icm_only("ret"); out.append(0xE0)
            elif op == "mode4":
                icm_only("mode4"); out.append(0xF4); mode4 = True
            elif op in ("tz", "tnz"):            # fc cX <inv>: F := (P1 word X == 0) / (!= 0), no store (probe65)
                icm_only(op)
                Bw = int(arg, 0)
                if not 0 <= Bw <= 3: raise AsmError(f"{op} k: k is 0..3 (a P1 word)")
                out += bytes([0xFC, 0xC0 | Bw, 1 if op == "tnz" else 0])
            elif op == "int":
                icm_only("int"); out.append(0xE2)
            elif op == "clr":
                icm_only("clr"); out.append(0xDE)
            elif op in ("lo", "lo.next"):
                icm_only(op); out.append(0xD3 if op.endswith("next") else 0xD2)
            elif op in ("p0blk", "p1blk", "p2blk"):
                icm_only(op); out.append(0xBC + "012".index(op[1]))
            elif op == "load":
                icm_only("load")
                k = int(arg, 0)
                if not 0 <= k <= 3: raise AsmError("load k: k is 0..3")
                out.append(0xD4 + k)
            elif op in ("shl", "sar"):
                icm_only(op)
                toks = [t.strip().lower() for t in arg.split(",")]
                sh = int(toks[0], 0)
                adv = 0x40 if len(toks) > 1 and toks[1] in ("adv", "inc") else 0
                if op == "shl":
                    if not 1 <= sh <= 31: raise AsmError("shl s: s is 1..31")
                    n = sh
                else:
                    if not 1 <= sh <= 32: raise AsmError("sar s: s is 1..32")
                    n = 0x20 | (32 - sh)
                out += bytes([0xFD, n | adv])
            elif op == "if" and lineage == "icm" and arg.lower() in ("f", "nf"):
                out.append(0xD9 if arg.lower() == "f" else 0xDA)
            elif op == "branch" and lineage == "icm":
                raise AsmError("branch (7-bit relative) does not exist on DMP3; use jump LABEL")

            # --- pointers ---
            elif op in ("p0page", "p1page", "p2page"):
                out.append(_page_byte(0x8 + "012".index(op[1]), arg))
            elif op in ("p0bank", "p1bank", "p2bank"):
                out.append(_bank_byte(L, "012".index(op[1]), arg))

            # --- ALU (compute; emits to FIFO in fifo mode, else use store) ---
            elif op == "min16":                  # f6 + ALU byte: signed MIN, 16-bit store
                if lineage == "3050":
                    raise AsmError("min16 (f6) is mantis-only")
                mode4 = False
                out.append(0xF6); out.append(_alu_byte("add", arg))
            elif op == "trunc":                  # f7: M[P2] &= 0xffff0000 (Finding 20)
                if lineage == "3050":
                    raise AsmError("trunc (f7) is mantis-only")
                out.append(0xF7); mode4 = False
            elif op in ("swap", "xchg01"):       # fc: toggle -- A and MOV sources via P1, B via P0 (probe68)
                if lineage == "3050":
                    raise AsmError("xchg01 (fc) is mantis-only; fc is the 3050 branch")
                out.append(0xFC)
            elif op == "xchg02":                 # fd: toggle -- A and MOV sources via P2, stores into P0's page (probe67/68)
                if lineage == "3050":
                    raise AsmError("xchg02 (fd) is mantis-only")
                if lineage == "icm":
                    raise AsmError("xchg02 (fd) is an MPU form; on DMP3 fd n is the shift (shl/sar)")
                out.append(0xFD)
            elif op == "nostore":
                raise AsmError("nostore is withdrawn: fd never suppressed a store, it exchanges P0 and P2 (xchg02); use trunc (f7) for a one-op no-store")
            elif op == "min":                    # f5 + ALU byte with op field 0
                mode4 = False
                out.append(0xF5); out.append(_alu_byte("add", arg))
            elif op in ALU_OPS:
                low_byte(f"{op} {arg}")
                out.append(_alu_byte(op, arg))
            elif op == "test":                   # d1: Z := (last ALU result == 0)
                out.append(0xD1)
            elif op == "if" and arg.lower() in ("z", "nz", "le0", "ge0"):
                out.append(0xD9 if arg.lower() in ("z", "le0") else 0xDA)
            elif op == "always":                 # d8: next instruction unconditional
                out.append(0xD8)
            elif op == "if":                     # d9/da/db: predicate the NEXT instruction only
                n = int(arg, 0)
                if not 1 <= n <= 3:
                    raise AsmError("if N: N is 1..3 (d9/da/db)")
                out.append(0xD8 + n)
            elif op in ("store.off", "fifo"):    # dd: route results to FIFO (sticky) [probe16]
                out.append(0xDD)
            elif op in ("mov", "mov16"):         # cx: M[P0+4k] -> M[P2]; "mov k" / "mov k,inc"
                toks = [t.strip().lower() for t in arg.split(",")]
                k = int(toks[0], 0)
                if not 0 <= k <= 3: raise AsmError(f"{op} k: source word k is 0..3")
                out.append(0xC0 | (8 if op == "mov16" else 0) | (k << 1)
                           | (1 if len(toks) > 1 and toks[1] == "inc" else 0))
            elif op in ("inc", "dec", "inc.next", "dec.next"):   # f8 f9 fa fb
                out.append(0xF8 | (1 if op.startswith("dec") else 0) | (2 if op.endswith(".next") else 0))
            elif op == "clr.next":               # df: P2 word++, then M[P2] = 0
                out.append(0xDF)
            elif op == "p2inc2":                 # d0
                out.append(0xD0)
            elif op == "p2inc":                  # df: P2 += 4 (probe13); repeat N times
                out.extend([0xDF] * (int(arg, 0) if arg else 1))
            elif op == "store" and not arg:
                out.append(STORE)
            elif op.startswith("store.") and op[6:] in ALU_OPS:
                low_byte(op)
                out.append(STORE)                    # dc first (hardware order)
                out.append(_alu_byte(op[6:], arg))

            # --- control / fifo ---
            elif op == "branch":
                n = int(arg, 0)
                if not 0 <= n <= 0x7F:
                    raise AsmError(f"branch imm {n:#x} must be 0..0x7f (forward only)")
                out.append(L["branch"]); out.append(n)
            elif op == "fmode":
                n = int(arg, 0)
                if not 0 <= n <= 3:
                    raise AsmError("fmode 0..3")
                out.append(L["fmode0"] | n); mode4 = False

            # --- legacy FIFO-emit form ---
            elif op == "selbank":
                b = BANK_ALIAS.get(arg.lower())
                if b is None:
                    b = int(arg, 0)
                if not 0x90 <= b <= 0x9F:
                    raise AsmError(f"bank 0x{b:02x} out of range 0x90-0x9f")
                bank = b; out.append(b)
            elif op == "emit":
                low_byte("emit")
                for tok in [t.strip() for t in arg.split(",")] if arg else []:
                    if not tok:
                        continue
                    if tok in REGS.get(bank or -1, {}):
                        out.append(REGS[bank][tok])
                    elif re.fullmatch(r"r(\d+)", tok):
                        r = int(tok[1:])
                        if not 0 <= r <= 15:
                            raise AsmError(f"register {tok} out of range r0-r15")
                        out.append(r << 3)
                    elif tok.startswith("0x"):
                        out.append(int(tok, 0) & 0x7F)
                    else:
                        known = ", ".join(REGS.get(bank or -1, {}))
                        raise AsmError(f"unknown register {tok!r}" +
                            (f" for bank 0x{bank:02x} (known: {known})" if bank
                             else " - no selbank in scope, use rN or 0xNN"))
            elif op == "nop":
                out.append(NOP)
            elif op == "skip":
                out.append(SKIP)
            elif op == "disable":
                out.append(DISABLE)
            else:
                raise AsmError(
                    f"unknown mnemonic {op!r} (confirmed: p0page/p1page/p2page, "
                    "p0bank/p1bank/p2bank, add/rsub/mul/nmul, store[.op], p2inc, always, if N, branch, "
                    "fmode, min16, trunc, xchg01/swap, xchg02, selbank, emit, nop, skip, disable, .db; "
                    "icm: .org, label:, jump, call, ret, mode4, if f/nf, p0blk/p1blk/p2blk, load, shl, sar, "
                    "lo, lo.next, int, clr, tz, tnz)")
        except AsmError as e:
            raise AsmError(f"line {lineno}: {e}") from None
        except ValueError as e:
            raise AsmError(f"line {lineno}: {e}") from None
    for off, name, lineno, op in fixups:
        if name not in labels:
            raise AsmError(f"line {lineno}: undefined label {name!r}")
        t = org + labels[name]
        if not 0 <= t <= 0x3FFF:
            raise AsmError(f"line {lineno}: {name} = {t:#x} is outside the 16 KB")
        targets.append(t)
        v = t | (0x4000 if op == "call" else 0)
        out[off], out[off + 1] = v >> 8, v & 0xFF
    if lineage == "icm":
        ends = {0xF0, 0xF1, 0xF2, 0xF3, 0xF5, 0xF6, 0xF7}
        for t in set(targets):
            o = t - org
            if 0 <= o < len(out):
                head = [b for b in out[o:o + 3] if not 0xD8 <= b <= 0xDB][:1]
                if not head or head[0] not in ends:
                    warn(f"target {t:#06x} does not start with a width byte (d8 f1 ...): the mode-4 rule "
                         "makes every low byte after it a branch target")
    return bytes(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--lineage", default="mantis", choices=list(LINEAGES))
    ap.add_argument("--patch"); ap.add_argument("--at", type=int)
    ap.add_argument("--len", type=int); ap.add_argument("--out")
    a = ap.parse_args()
    try:
        code = assemble(pathlib.Path(a.source).read_text(), a.lineage)
    except AsmError as e:
        sys.exit(f"error: {e}")
    print(f"assembled {len(code)} bytes: {code.hex(' ')}")
    if not a.patch:
        return
    if a.at is None or a.len is None or not a.out:
        sys.exit("--patch requires --at, --len and --out")
    if len(code) > a.len:
        sys.exit(f"error: fragment is {len(code)} B but site capacity is {a.len} B")
    img = bytearray(pathlib.Path(a.patch).read_bytes())
    if a.at + a.len > len(img):
        sys.exit(f"error: site {a.at}+{a.len} exceeds image ({len(img)} B)")
    padded = code + bytes([NOP]) * (a.len - len(code))
    original = bytes(img[a.at:a.at + a.len])
    img[a.at:a.at + a.len] = padded
    pathlib.Path(a.out).write_bytes(bytes(img))
    print(f"site {a.at}..{a.at + a.len - 1}\n  was: {original.hex(' ')}\n  now: {padded.hex(' ')}   ({a.len - len(code)} NOP pad)\nwrote {a.out}")


if __name__ == "__main__":
    main()
