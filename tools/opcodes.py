#!/usr/bin/env python3
"""Recover the DMP output-routine template and split opcode vs operand bytes."""
import re, pathlib, json, itertools, collections

SYMFILE = "eras/_kernel_hammerhead-lmr1/dmpDefaultMPU6050.c"

# ---- 1. parse symbol map, evaluating the bank arithmetic -------------------
DEF = re.compile(r'#define\s+(\w+)\s+\(([^)]*)\)')
syms = {}
for m in DEF.finditer(pathlib.Path(SYMFILE).read_text()):
    name, expr = m.group(1), m.group(2).strip()
    if not re.fullmatch(r'[0-9xXa-fA-F\s+*\-]+', expr):
        continue
    try:
        syms[name] = eval(expr.replace('0X', '0x'), {"__builtins__": {}})
    except Exception:
        pass

print(f"symbols parsed: {len(syms)}")
data = {k: v for k, v in syms.items() if v < 1024}
code = {k: v for k, v in syms.items() if v >= 1024}
print(f"  data (<1024): {len(data)}   code (>=1024): {len(code)}")
print(f"  highest data symbol: {max(data.items(), key=lambda kv: kv[1])}")
print(f"  lowest  code symbol: {min(code.items(), key=lambda kv: kv[1])}")

# ---- 2. the seven output routines -----------------------------------------
SENSORS = ["3QUAT", "QUAT", "PQUAT", "ACCL", "GYRO", "CPASS", "PRESS"]
routines = []
for s in SENSORS:
    cfg, dat = syms.get(f"CFG_OUT_{s}"), syms.get(f"OUT_{s}_DAT")
    if cfg and dat:
        routines.append((s, cfg, dat))
print("\noutput routines (CFG -> DAT):")
prev = None
for s, cfg, dat in routines:
    stride = f"  stride={cfg-prev}" if prev else ""
    print(f"  {s:<6} cfg={cfg:<5} dat={dat:<5} delta={dat-cfg}{stride}")
    prev = cfg

# ---- 3. which image do these index into? ----------------------------------
imgs = {}
for p in sorted(pathlib.Path("images").glob("*.bin")):
    b = p.read_bytes(); imgs[len(b)] = b

def blocks(img, span=34):
    return [img[cfg:cfg+span] for _, cfg, _ in routines]

def pair_sim(bs):
    tot = n = 0
    for a, b in itertools.combinations(bs, 2):
        if len(a) != len(b) or not a: continue
        tot += sum(x == y for x, y in zip(a, b)) / len(a); n += 1
    return tot / n if n else 0

print("\nself-validating fit: mean pairwise byte-identity of the 7 blocks per image")
scores = {}
for n in sorted(imgs):
    if n <= max(c for _, c, _ in routines) + 34:
        print(f"  {n:>6}B  (too short)"); continue
    s = pair_sim(blocks(imgs[n]))
    scores[n] = s
    print(f"  {n:>6}B  {s*100:5.1f}%  {'#'*int(s*50)}")

best = max(scores, key=scores.get)
print(f"\n-> best fit: {best}B image ({scores[best]*100:.1f}% mean identity)")

# ---- 4. align the templates ----------------------------------------------
img = imgs[best]
bs = blocks(img)
print(f"\n{'='*78}\nOUTPUT-ROUTINE TEMPLATE  ({best}B image)\n{'='*78}")
print(f"{'sensor':<7} {'addr':<6} bytes")
for (s, cfg, _), b in zip(routines, bs):
    print(f"{s:<7} {cfg:<6} {b.hex(' ')}")

print(f"\n{'pos':<5} {'':<7} consensus / variation")
span = len(bs[0])
varying = []
for i in range(span):
    col = [b[i] for b in bs]
    uniq = collections.Counter(col)
    if len(uniq) == 1:
        print(f"  {i:<3}  CONST  {col[0]:02x}")
    else:
        varying.append(i)
        print(f"  {i:<3}  VARY   " + ' '.join(f"{c:02x}" for c in col)
              + f"   ({len(uniq)} distinct)")
print(f"\nconstant positions: {span-len(varying)}/{span}   varying: {varying}")
