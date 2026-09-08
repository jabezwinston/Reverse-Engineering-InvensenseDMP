#!/usr/bin/env python3
"""Destination-rule consistency test over fully-named images (512 B data, dmpmap.h).

For each candidate rule for where a low-byte op writes, simulate the pointer state through
the program and collect the written words. Score:
  - writes into constant words (Q30 unit constants, scale factors) : violation
  - writes into hardware sensor-input words (0..13)                 : violation
  - reads of words that are never written and are not constants/inputs : dangling
  - quaternion words (192..207) written                              : required
Control: same scoring on a byte-shuffled code region.
"""
import random, collections, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from symbols import dmpmap
from branch import IMAGES, code_start
from decode import lineage_of

CONST_WORDS = {112, 116, 120, 124,   # 0.5 0.0 1.0 1.5
               64, 68, 72, 76,       # 1000, 1, 98303, -98303 (thresholds, host-written)
               96, 100, 104, 108}    # 0x3e0330 1.0 2.5deg 0.98
INPUT_WORDS = {0, 4, 8, 12}          # PTAT/XGYR, YGYR/ZGYR, XACC/YACC, ZACC/ADC1
QUAT = {192, 196, 200, 204}

RULES = {
    "D=P2+4A": lambda A, B, p: p[2] + 4 * A,
    "D=P2+4B": lambda A, B, p: p[2] + 4 * B,
    "D=Aword": lambda A, B, p: p[0] + 4 * A,
    "D=Bword": lambda A, B, p: p[1] + 4 * B,
    "D=P2+4A(op&4)else4B": lambda A, B, p, : None,  # filled below
}

def simulate(img, start, rule, lineage, only_ops=None):
    page = [0, 0, 0]; bank = [0, 0, 0]
    br = 0xF4 if lineage == "mantis" else 0xFC
    reads = collections.Counter(); writes = collections.Counter(); wsites = collections.defaultdict(list)
    i = start
    while i < len(img):
        b = img[i]
        if b == br: i += 2; continue
        fam = b >> 4
        if fam in (8, 9, 0xA): page[fam - 8] = b & 0xf
        elif lineage == "mantis" and fam == 0xB and ((b >> 2) & 3) < 3: bank[(b >> 2) & 3] = b & 3
        elif lineage == "3050" and 0xC0 <= b <= 0xC5: bank[(b >> 1) & 3] = b & 1
        elif b < 0x80:
            A, B, op = (b >> 5) & 3, (b >> 3) & 3, b & 7
            p = [bank[k] * 256 + page[k] * 16 for k in range(3)]
            reads[p[0] + 4 * A] += 1; reads[p[1] + 4 * B] += 1
            if only_ops is None or op in only_ops:
                d = rule(A, B, p, op) if rule.__code__.co_argcount == 4 else rule(A, B, p)
                writes[d] += 1; wsites[d].append(i)
        i += 1
    return reads, writes, wsites

def score(reads, writes, data_size):
    w = {a for a in writes if a < data_size}
    r = {a for a in reads if a < data_size}
    bad_const = sorted(w & CONST_WORDS); bad_in = sorted(w & INPUT_WORDS)
    dangling = sorted(r - w - CONST_WORDS - INPUT_WORDS)
    return dict(n_write_words=len(w), const_viol=bad_const, input_viol=bad_in,
                quat_written=sorted(w & QUAT), dangling=len(dangling), dangling_list=dangling[:12])

def main():
    random.seed(3)
    dm = dmpmap(); names = {v: k.replace("DMP_", "") for k, v in sorted(dm.items(), key=lambda kv: -len(kv[0]))}
    rules = dict(RULES)
    rules["D=P2+4A(op&4)else4B"] = lambda A, B, p, op: p[2] + 4 * (A if op & 4 else B)
    rules["D=P2+4B(op&4)else4A"] = lambda A, B, p, op: p[2] + 4 * (B if op & 4 else A)
    for size in (1024, 1923, 1929):
        img = IMAGES[size].read_bytes(); start = 512 if size == 1024 else 1024
        L = lineage_of(img, start)
        print(f"\n=== {size} B  lineage={L}  code [{start}:{len(img)}]")
        for name, rule in rules.items():
            r, w, ws = simulate(img, start, rule, L)
            s = score(r, w, 512)
            print(f"  {name:24} written words={s['n_write_words']:3}  const-viol={[names.get(a,a) for a in s['const_viol']]}  "
                  f"input-viol={s['input_viol']}  quat={len(s['quat_written'])}/4  dangling-reads={s['dangling']}")
        # per-op-class breakdown for the two P2 rules
        for name in ("D=P2+4A", "D=P2+4B"):
            for ops in ((0, 1, 4, 5), (2, 3, 6, 7)):
                r, w, ws = simulate(img, start, rules[name], L, only_ops=set(ops))
                s = score(r, w, 512)
                print(f"    {name} ops{ops}: const-viol={[names.get(a,a) for a in s['const_viol']]} quat={len(s['quat_written'])}/4")
        # control
        code = bytearray(img[start:]); random.shuffle(code); sh = img[:start] + bytes(code)
        r, w, ws = simulate(sh, start, rules["D=P2+4A"], L); s = score(r, w, 512)
        print(f"  shuffled ctrl (P2+4A):     written words={s['n_write_words']:3}  const-viol={len(s['const_viol'])}  input-viol={len(s['input_viol'])}  dangling={s['dangling']}")
    img = IMAGES[1024].read_bytes()
    c = collections.Counter(img[512:])
    print("\n1024 image code-byte counts f0-ff:", {f"{k:02x}": c[k] for k in range(0xF0, 0x100) if c[k]})
    print("1024 image code-byte counts c0-cf:", {f"{k:02x}": c[k] for k in range(0xC0, 0xD0) if c[k]})
    print("1024 image code-byte counts d0-df:", {f"{k:02x}": c[k] for k in range(0xD0, 0xE0) if c[k]})

if __name__ == "__main__":
    main()
