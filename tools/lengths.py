#!/usr/bin/env python3
"""Recover per-opcode instruction lengths from labelled fragment spans.

Each labelled fragment must decompose exactly into whole instructions. Given a
length function len[opcode], parsing is deterministic, so a candidate assignment
either consumes a fragment exactly or it does not. Solve by DFS over assignments.
"""
import re, pathlib, collections, sys

MAXLEN = 4
DEF = re.compile(r'#define\s+(\w+)\s+\(?\s*([0-9][0-9xXa-fA-F\s+*\-]*?)\s*\)?\s*$', re.M)
HEX = re.compile(r'0[xX][0-9a-fA-F]{1,2}')
ARR = re.compile(r'\w+\s*\[[^\]]*\]\s*=\s*\{(.*?)\}\s*;', re.S)


def load(fn):
    src = next(pathlib.Path("eras").rglob(fn))
    t = src.read_text(errors="ignore")
    body = re.sub(r'/\*.*?\*/', '', max(ARR.findall(t), key=len), flags=re.S)
    img = bytes(int(x, 16) & 0xFF for x in HEX.findall(body))
    sy = {}
    for m in DEF.finditer(t):
        n, e = m.group(1), m.group(2).strip()
        if not re.fullmatch(r'[0-9xXa-fA-F\s+*\-]+', e):
            continue
        try:
            v = eval(e.replace('0X', '0x'), {"__builtins__": {}})
        except Exception:
            continue
        if re.match(r'(FCFG|CFG)_', n) and 0 < v < len(img):
            sy[n] = v
    return img, sy


frags = []
for fn, part in [("dmpDefault.c", "6050"), ("dmpDefaultMantis.c", "Mantis")]:
    img, sy = load(fn)
    ordered = sorted(sy.items(), key=lambda kv: kv[1])
    for i, (name, addr) in enumerate(ordered):
        end = ordered[i+1][1] if i + 1 < len(ordered) else len(img)
        f = img[addr:end]
        # cap: very long fragments are mostly unlabelled interior, weak constraints
        if 0 < len(f) <= 12:
            frags.append((f, f"{part}:{name}"))

frags.sort(key=lambda x: len(x[0]))
print(f"constraint fragments (len 1..12): {len(frags)}")
print(f"distinct bytes appearing: {len({b for f,_ in frags for b in f})}\n")

singles = {f[0] for f, _ in frags if len(f) == 1}
print(f"directly pinned to length 1 (whole fragment is one byte): "
      f"{' '.join(f'{b:02x}' for b in sorted(singles))}\n")

solutions = []
nodes = 0
LIMIT = 3_000_000


def dfs(idx, asg):
    global nodes
    nodes += 1
    if nodes > LIMIT:
        return
    if idx == len(frags):
        solutions.append(dict(asg))
        return
    frag, _ = frags[idx]
    n = len(frag)

    def walk(pos, asg):
        global nodes
        if nodes > LIMIT:
            return
        if pos == n:
            dfs(idx + 1, asg)
            return
        if pos > n:
            return
        b = frag[pos]
        if b in asg:
            walk(pos + asg[b], asg)
        else:
            for L in range(1, MAXLEN + 1):
                if pos + L > n:
                    break
                asg[b] = L
                nodes += 1
                walk(pos + L, asg)
                del asg[b]

    walk(0, asg)


dfs(0, {})
print(f"search nodes: {nodes}{'  (LIMIT HIT)' if nodes > LIMIT else ''}")
print(f"consistent solutions found: {len(solutions)}\n")

if not solutions:
    print("NO consistent assignment -> labels are not all instruction boundaries,")
    print("or some fragments contain data rather than code.")
    sys.exit(0)

allb = sorted({b for f, _ in frags for b in f})
doms = {b: sorted({s[b] for s in solutions if b in s}) for b in allb}
determined = {b: d[0] for b, d in doms.items() if len(d) == 1}
print(f"bytes with a UNIQUE length across all {len(solutions)} solutions: "
      f"{len(determined)}/{len(allb)}\n")
bylen = collections.defaultdict(list)
for b, L in sorted(determined.items()):
    bylen[L].append(b)
for L in sorted(bylen):
    print(f"  length {L} ({len(bylen[L])} opcodes):")
    row = [f"{b:02x}" for b in bylen[L]]
    for i in range(0, len(row), 16):
        print("     " + " ".join(row[i:i+16]))
amb = {b: d for b, d in doms.items() if len(d) > 1}
print(f"\n  ambiguous ({len(amb)}): " + " ".join(f"{b:02x}{d}" for b, d in sorted(amb.items())))
