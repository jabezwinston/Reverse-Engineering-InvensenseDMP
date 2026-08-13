#!/usr/bin/env python3
"""Exact per-opcode length domains via (byte,length) feasibility queries.

For each byte b and candidate length L, pin len[b]=L and ask whether ANY
complete assignment satisfies every labelled fragment. Unsatisfiable (b,L)
pairs are eliminated. This avoids the enumeration-order bias of counting
solutions from a truncated DFS.
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
        if 0 < len(f) <= 12:
            frags.append((f, f"{part}:{name}"))
frags.sort(key=lambda x: len(x[0]))
allb = sorted({b for f, _ in frags for b in f})
print(f"fragments: {len(frags)}   distinct bytes: {len(allb)}")


def feasible(pin):
    """Is there a complete length assignment consistent with all fragments,
    given the pinned {byte: length} constraints?"""
    budget = [400_000]

    def dfs(idx, asg):
        if budget[0] <= 0:
            return False
        if idx == len(frags):
            return True
        frag, _ = frags[idx]
        n = len(frag)

        def walk(pos, asg):
            budget[0] -= 1
            if budget[0] <= 0:
                return False
            if pos == n:
                return dfs(idx + 1, asg)
            if pos > n:
                return False
            b = frag[pos]
            if b in asg:
                return walk(pos + asg[b], asg)
            for L in range(1, MAXLEN + 1):
                if pos + L > n:
                    break
                asg[b] = L
                if walk(pos + L, asg):
                    del asg[b]
                    return True
                del asg[b]
            return False

        return walk(0, asg)

    return dfs(0, dict(pin))


if not feasible({}):
    print("base system UNSAT"); sys.exit(1)

doms = {}
for b in allb:
    d = [L for L in range(1, MAXLEN + 1) if feasible({b: L})]
    doms[b] = d

det = {b: d[0] for b, d in doms.items() if len(d) == 1}
amb = {b: d for b, d in doms.items() if len(d) > 1}
print(f"\nUNIQUELY determined: {len(det)}/{len(allb)}")
bylen = collections.defaultdict(list)
for b, L in det.items():
    bylen[L].append(b)
for L in sorted(bylen):
    row = [f"{b:02x}" for b in sorted(bylen[L])]
    print(f"  length {L} ({len(row)}):")
    for i in range(0, len(row), 16):
        print("     " + " ".join(row[i:i+16]))

print(f"\nAMBIGUOUS: {len(amb)}")
for b, d in sorted(amb.items()):
    print(f"  {b:02x} -> {d}")

# is the uniform 1-byte encoding globally consistent?
print(f"\nuniform 1-byte encoding consistent with every fragment: "
      f"{feasible({b: 1 for b in allb})}")
