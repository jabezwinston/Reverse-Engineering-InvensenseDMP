#!/usr/bin/env python3
"""Dump labeled code fragments from the two self-consistent image+symbol pairs."""
import re, pathlib, hashlib

PAIRS = [("dmpDefault.c", 1024, "MPU-6050"),
         ("dmpDefaultMantis.c", 1923, "MPU-6500 Mantis")]
DEF = re.compile(r'#define\s+(\w+)\s+\(?\s*([0-9][0-9xXa-fA-F\s+*\-]*?)\s*\)?\s*$', re.M)
HEX = re.compile(r'0[xX][0-9a-fA-F]{1,2}')
ARR = re.compile(r'\w+\s*\[[^\]]*\]\s*=\s*\{(.*?)\}\s*;', re.S)

for fname, size, part in PAIRS:
    src = next(pathlib.Path("eras").rglob(f"*/{fname}"), None) \
       or next(pathlib.Path("eras").rglob(fname), None)
    text = src.read_text(errors="ignore")

    body = max(ARR.findall(text), key=len)
    body = re.sub(r'/\*.*?\*/', '', body, flags=re.S)
    img = bytes(int(t, 16) & 0xFF for t in HEX.findall(body))

    syms = {}
    for m in DEF.finditer(text):
        n, e = m.group(1), m.group(2).strip()
        if not re.fullmatch(r'[0-9xXa-fA-F\s+*\-]+', e):
            continue
        try:
            v = eval(e.replace('0X', '0x'), {"__builtins__": {}})
        except Exception:
            continue
        # keep only in-range CFG/FCFG code labels
        if re.match(r'(FCFG|CFG)_', n) and 0 < v < len(img):
            syms[n] = v

    print("=" * 78)
    print(f"{part}   {fname}   image={len(img)}B (expected {size})  "
          f"sha256={hashlib.sha256(img).hexdigest()[:12]}")
    print("=" * 78)

    ordered = sorted(syms.items(), key=lambda kv: kv[1])
    for i, (name, addr) in enumerate(ordered):
        end = ordered[i+1][1] if i+1 < len(ordered) else min(addr+24, len(img))
        frag = img[addr:end]
        gap = end - addr
        shown = frag[:28]
        print(f"  {addr:>5} {name:<18} len={gap:<4} {shown.hex(' ')}"
              + (" ..." if gap > 28 else ""))
    print()
