#!/usr/bin/env python3
"""Pairwise differential + opcode-distribution analysis over the DMP image corpus."""
import pathlib, difflib, json, collections, math

imgs = {}
for p in sorted(pathlib.Path("images").glob("*.bin")):
    b = p.read_bytes()
    imgs[len(b)] = b

man = json.load(open("manifest.json"))
label = {}
for sha, u in man["unique"].items():
    label[u["size"]] = pathlib.Path(u["paths"][0]).name

def L(n): return f"{n}B ({label.get(n,'?')})"

print("=" * 78)
print("CONTAINMENT: is the 1024B MPU-6050 image embedded in the larger ones?")
print("=" * 78)
small = imgs[1024]
for n in sorted(imgs):
    if n == 1024: continue
    off = imgs[n].find(small)
    # also try longest common prefix
    o = imgs[n]
    lcp = 0
    while lcp < min(len(o), 1024) and o[lcp] == small[lcp]: lcp += 1
    print(f"  {n:>6}B  contains={off if off>=0 else 'NO':<6}  common_prefix={lcp}")

for a_n, b_n in [(1929, 1923), (1962, 1929), (3062, 3065), (2634, 2639)]:
    if a_n not in imgs or b_n not in imgs: continue
    a, b = imgs[a_n], imgs[b_n]
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    ops = sm.get_opcodes()
    changed = [o for o in ops if o[0] != 'equal']
    print()
    print("=" * 78)
    print(f"DIFF  {L(a_n)}  vs  {L(b_n)}")
    print("=" * 78)
    print(f"  similarity={sm.ratio():.4f}  change_regions={len(changed)}")
    lo = min((o[1] for o in changed), default=-1)
    hi = max((o[2] for o in changed), default=-1)
    print(f"  first change @A[{lo}]   last change @A[{hi}]")
    # 2-byte co-varying operand pattern: opcode+1 delta
    covary = collections.Counter()
    for tag, i1, i2, j1, j2 in changed:
        if tag == 'replace' and (i2 - i1) == (j2 - j1) == 2:
            covary[(a[i1], b[j1], b[j1+1] - a[i1+1])] += 1
    if covary:
        print("  co-varying 2-byte replacements (opcodeA -> opcodeB, operand delta):")
        for (oa, ob, d), c in covary.most_common(10):
            print(f"    {oa:02x} -> {ob:02x}   operand{d:+#05x}   x{c}")

print()
print("=" * 78)
print("OPCODE DISTRIBUTION  (code region only, offset >= 1024)")
print("=" * 78)
def prof(b, start=1024):
    c = collections.Counter(b[start:])
    tot = sum(c.values()) or 1
    hi = sum(v for k, v in c.items() if k >= 0x80) / tot
    ent = -sum((v/tot) * math.log2(v/tot) for v in c.values())
    return c, hi, ent, tot

profs = {}
for n in sorted(imgs):
    c, hi, ent, tot = prof(imgs[n])
    profs[n] = c
    top = ' '.join(f"{k:02x}" for k, _ in c.most_common(8))
    print(f"  {n:>6}B  bytes={tot:<6} hi-nibble>=0x80: {hi*100:5.1f}%  "
          f"entropy={ent:.2f}  top: {top}")

print()
print("=" * 78)
print("ISA COMPATIBILITY: cosine similarity of code-region byte histograms")
print("=" * 78)
def cos(c1, c2):
    ks = set(c1) | set(c2)
    d = math.sqrt(sum(c1[k]**2 for k in ks)) * math.sqrt(sum(c2[k]**2 for k in ks))
    return sum(c1[k]*c2[k] for k in ks) / d if d else 0.0

ns = sorted(profs)
print("        " + " ".join(f"{n:>6}" for n in ns))
for i in ns:
    print(f"  {i:>5} " + " ".join(f"{cos(profs[i], profs[j]):6.3f}" for j in ns))
