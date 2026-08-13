#!/usr/bin/env python3
"""Extract DMP firmware byte-arrays from InvenSense C sources, dedupe by SHA-256."""
import re, os, sys, json, hashlib, pathlib

ROOT = pathlib.Path("eras")
OUT = pathlib.Path("images"); OUT.mkdir(exist_ok=True)

# match:  ... name [ maybe_size ] = {   ... }  ;
ARR = re.compile(
    r'(?:static\s+|const\s+|volatile\s+)*'
    r'(?:unsigned\s+char|signed\s+char|u8|uint8_t|int8_t|char|UCHAR|BYTE)\s+'
    r'(\w+)\s*\[[^\]]*\]'
    r'(?:\s*(?:PROGMEM|__attribute__\s*\(\([^)]*\)\)|DMP_CODE_ATTR|__flash))*'
    r'\s*=\s*\{(.*?)\}\s*;',
    re.S)
HEX = re.compile(r'0[xX][0-9a-fA-F]{1,2}')

records = []
for path in ROOT.rglob("*"):
    if not path.is_file() or path.suffix not in (".c", ".h", ".cpp"):
        continue
    try:
        text = path.read_text(errors="ignore")
    except Exception:
        continue
    matches = list(ARR.finditer(text))
    if not matches:
        # bare initializer fragments (e.g. icm20948_img.dmp3a.h) are #include'd
        # inside an array elsewhere, so they carry no declaration of their own.
        stripped = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
        stripped = re.sub(r'//[^\n]*', '', stripped)
        toks = HEX.findall(stripped)
        if len(toks) >= 256 and not re.search(r'\w+\s*\(', stripped):
            blob = bytes(int(t, 16) & 0xFF for t in toks)
            digest = hashlib.sha256(blob).hexdigest()
            era = path.relative_to(ROOT).parts[0]
            records.append(dict(sha256=digest, size=len(blob),
                                symbol="(bare fragment)", era=era,
                                path=str(pathlib.Path(*path.relative_to(ROOT).parts[1:]))))
            p = OUT / f"{digest[:16]}_{len(blob)}.bin"
            if not p.exists():
                p.write_bytes(blob)
        continue

    for m in matches:
        name, body = m.group(1), m.group(2)
        # strip comments so /* bank # 0 */ markers don't pollute
        body = re.sub(r'/\*.*?\*/', '', body, flags=re.S)
        body = re.sub(r'//[^\n]*', '', body)
        toks = HEX.findall(body)
        if len(toks) < 256:            # firmware images only, not small tables
            continue
        blob = bytes(int(t, 16) & 0xFF for t in toks)
        digest = hashlib.sha256(blob).hexdigest()
        era = path.relative_to(ROOT).parts[0]
        rel = str(pathlib.Path(*path.relative_to(ROOT).parts[1:]))
        records.append(dict(sha256=digest, size=len(blob), symbol=name,
                            era=era, path=rel))
        p = OUT / f"{digest[:16]}_{len(blob)}.bin"
        if not p.exists():
            p.write_bytes(blob)

by_sha = {}
for r in records:
    by_sha.setdefault(r["sha256"], []).append(r)

print(f"array instances found : {len(records)}")
print(f"UNIQUE images (sha256): {len(by_sha)}\n")

rows = sorted(by_sha.items(), key=lambda kv: -kv[1][0]["size"])
print(f"{'size':>6}  {'sha256[:12]':<14} {'symbol':<22} {'eras':<5} example path")
print("-" * 110)
for sha, rs in rows:
    r0 = rs[0]
    eras = sorted({x["era"] for x in rs})
    syms = sorted({x["symbol"] for x in rs})
    print(f"{r0['size']:>6}  {sha[:12]:<14} {','.join(syms)[:22]:<22} "
          f"{len(eras):<5} {r0['path'][:52]}")

json.dump({"records": records,
           "unique": {k: dict(size=v[0]["size"],
                              symbols=sorted({x['symbol'] for x in v}),
                              eras=sorted({x['era'] for x in v}),
                              paths=sorted({x['path'] for x in v}))
                      for k, v in by_sha.items()}},
          open("manifest.json", "w"), indent=1)
print("\n-> manifest.json, images/*.bin")
