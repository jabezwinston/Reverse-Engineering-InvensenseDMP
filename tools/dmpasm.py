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
  add   A,B[,hi]                     M[P0+4A] + M[P1+4B]   (A,B in 0..3)
  rsub  A,B[,hi]                     M[P1+4B] - M[P0+4A]   (op1)
  mul   A,B[,hi]                     M[P0+4A] * M[P1+4B]   (op2)
  nmul  A,B[,hi]                    -M[P0+4A] * M[P1+4B]   (op3)
       `hi` sets op&4 -> destination word P2+4 (default P2+0). Use `p2inc` (df)
       to reach words 2,3 of the page.
  store                              dc: RAM routing ON  (sticky; every following ALU op stores)
  fifo  (alias store.off)            dd: route results to the FIFO (sticky; the at-rest
                                     routing). Vendor packet emit = dd f1 <ALU ops>
  p2inc [N]                          df: P2 += 4, N times. Reaches words 2,3 of a page
  store.add / store.rsub / .mul / .nmul  A,B[,hi]
       fused: emits `dc` THEN the ALU byte, the order confirmed on hardware
       (probe6: dc precedes the op). This is the RAM-store idiom.
  branch N                           f4 (mantis) / fc (3050); target = here+2+N,
                                     forward only, 0 <= N <= 0x7f (Finding 2)
  fmode N                            f0..f3: FIFO width/mode (1=32-bit, 2/3=16-bit)
  test                               d1: Z := (last ALU result == 0)
  if z / if nz  (= if 1 / if 2)      d9 / da: run the NEXT instruction only if Z / not Z
  always / if 3                      d8 / db (db: true at rest, meaning open)
  clr.next                           df: P2 word++, then M[P2] := 0   (p2inc [N] = N of these)
  inc / dec                          f8 / f9: M[P2] += 1 / -= 1 (one LSB)
  inc.next / dec.next                fa / fb: P2 word++, then INC / DEC
  p2inc2                             d0: P2 word += 2, mod 4
  mov k[,inc]                        c0..c7: copy M[P0+4k] -> M[P2]; inc pre-advances P2
  mov16 k[,inc]                      c8..cf: copy the upper half-word, zero-extended

Legacy FIFO-emit form (stock preambles) still assembles:
  selbank gyro|quat|accel|delay|0x9N
  emit r0..r15 | gyro_x ... | 0xNN
  nop / skip (fe) / disable (ff, halts) / .db 0x..,0x..

A bare ALU op with no `store` and no `dc` emits its result to the FIFO when a
FIFO mode is active (bench round 10); with `store`/dc it writes RAM instead.

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
}
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
    """Parse `A,B[,hi]` -> (A<<5)|(B<<3)|op(|4)."""
    toks = [t.strip() for t in arg.split(",") if t.strip()]
    if len(toks) < 2:
        raise AsmError(f"{op!r} needs A,B (0..3) and optional hi")
    A, B = int(toks[0], 0), int(toks[1], 0)
    if not (0 <= A <= 3 and 0 <= B <= 3):
        raise AsmError(f"operand index out of range 0-3: A={A} B={B}")
    hi = 0
    if len(toks) >= 3 and toks[2].lower() in ("hi", "1", "d1", "p2+4"):
        hi = 4
    return (A << 5) | (B << 3) | ALU_OPS[op] | hi


def assemble(text, lineage="mantis"):
    L = LINEAGES[lineage]
    out = bytearray()
    bank = None
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split(";")[0].strip()
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
            elif op == ".db":
                for tok in arg.split(","):
                    out.append(int(tok.strip(), 0) & 0xFF)

            # --- pointers ---
            elif op in ("p0page", "p1page", "p2page"):
                out.append(_page_byte(0x8 + "012".index(op[1]), arg))
            elif op in ("p0bank", "p1bank", "p2bank"):
                out.append(_bank_byte(L, "012".index(op[1]), arg))

            # --- ALU (compute; emits to FIFO in fifo mode, else use store) ---
            elif op in ALU_OPS:
                out.append(_alu_byte(op, arg))
            elif op == "test":                   # d1: Z := (last ALU result == 0)
                out.append(0xD1)
            elif op == "if" and arg.lower() in ("z", "nz"):
                out.append(0xD9 if arg.lower() == "z" else 0xDA)
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
                out.append(L["fmode0"] | n)

            # --- legacy FIFO-emit form ---
            elif op == "selbank":
                b = BANK_ALIAS.get(arg.lower())
                if b is None:
                    b = int(arg, 0)
                if not 0x90 <= b <= 0x9F:
                    raise AsmError(f"bank 0x{b:02x} out of range 0x90-0x9f")
                bank = b; out.append(b)
            elif op == "emit":
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
                    "fmode, selbank, emit, nop, skip, disable, .db)")
        except AsmError as e:
            raise AsmError(f"line {lineno}: {e}") from None
        except ValueError as e:
            raise AsmError(f"line {lineno}: {e}") from None
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
