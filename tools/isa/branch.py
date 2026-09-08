#!/usr/bin/env python3
"""Branch-rule test (bk3296 technique A7): score candidate displacement rules for the
2-byte immediate-taking opcode against the vendor's own code labels, with controls.

Rule under test (from eMD 6.12 labels): target = site + 2 + imm.
"""
import random, collections, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from symbols import symbols, code_labels, ROOT

IMAGES = {p.stat().st_size: p for p in (ROOT / "corpus/images").glob("*.bin")}
def load(size): return IMAGES[size].read_bytes()

def code_start(size):
    # Family A (MotionApps20/41, Mantis) starts at PRGM_START 0x0300; Family B at 0x0400;
    # the 3050-era 1024 image around 512; ICM-20948 at 4096.
    return 4096 if size > 14000 else 1024 if size > 2000 else 512 if size == 1024 else 768
def br_opcode(img, start):
    # MPU-3050-style encoding uses f8 as block base -> imm-taker fc ; mantis-style uses f0 -> f4
    code = img[start:]
    return 0xF4 if code.count(0xF4) >= code.count(0xFC) else 0xFC

RULES = {
    "a+2+imm":        lambda a, i: a + 2 + i,
    "a+1+imm":        lambda a, i: a + 1 + i,
    "a+imm":          lambda a, i: a + i,
    "a+2+(imm&0x1f)": lambda a, i: a + 2 + (i & 0x1f),
    "a+2+2*imm":      lambda a, i: a + 2 + 2 * i,
    "page|imm":       lambda a, i: (a & ~0xff) | i,
}

def sites(img, start, op):
    return [(a, img[a + 1]) for a in range(start, len(img) - 1) if img[a] == op]

def score(sts, rule, labels):
    lab = set(labels.values())
    hits = sum(1 for a, i in sts if rule(a, i) in lab)
    return hits

def main():
    random.seed(1)
    syms = symbols()
    for size in (3062, 2639, 1923, 1024):
        img = load(size); start = code_start(size); op = br_opcode(img, start)
        labs = code_labels(syms[size])
        # labels that are plausible branch targets: anything in the code region
        labs = {n: v for n, v in labs.items() if v >= start}
        sts = sites(img, start, op)
        low = [(a, i) for a, i in sts if i < 0x80]
        print(f"\n=== {size} B  op={op:02x}  sites={len(sts)} (imm<0x80: {len(low)})  code labels={len(labs)}")
        hist = collections.Counter(i for _, i in sts)
        print("  imm histogram (top 16):", ", ".join(f"{k:02x}:{v}" for k, v in hist.most_common(16)))
        print("  imm>=0x80 sites:", sum(1 for _, i in sts if i >= 0x80),
              " bits[6:5] of low imms:", collections.Counter((i >> 5) & 3 for _, i in low))
        for name, rule in RULES.items():
            h = score(low, rule, labs)
            # control 1: shuffle immediates among sites (keeps imm distribution)
            ctrl = []
            imms = [i for _, i in low]
            for _ in range(200):
                random.shuffle(imms)
                ctrl.append(score([(a, i) for (a, _), i in zip(low, imms)], rule, labs))
            # control 2: uniform random imm in [0,0x80)
            ctrl2 = [score([(a, random.randrange(0x80)) for a, _ in low], rule, labs) for _ in range(200)]
            print(f"  {name:16} hits={h:3}/{len(low)}   shuffled-imm ctrl={sum(ctrl)/len(ctrl):5.1f}   "
                  f"random-imm ctrl={sum(ctrl2)/len(ctrl2):5.1f}")
        # per-label detail under the primary rule
        rule = RULES["a+2+imm"]
        by_target = collections.defaultdict(list)
        for a, i in low:
            by_target[rule(a, i)].append(a)
        print("  labels hit under a+2+imm:")
        for n, v in sorted(labs.items(), key=lambda kv: kv[1]):
            srcs = by_target.get(v, [])
            pre = img[v - 3:v].hex(' '); at = img[v:v + 6].hex(' ')
            mark = "  <== " + ",".join(str(s) for s in srcs) if srcs else ""
            print(f"    {v:5} {n:24} ...{pre} | {at}{mark}")
        # forbidden-landing test: target == operand byte of another branch site
        opnd = {a + 1 for a, _ in sts}
        bad = [(a, i) for a, i in low if rule(a, i) in opnd]
        print(f"  targets landing on another branch's operand byte: {len(bad)} / {len(low)}"
              f"  (expected by chance ~{len(low)*len(opnd)/max(1,len(img)-start):.1f})")

if __name__ == "__main__":
    main()
