#!/usr/bin/env python3
"""Symbol tables for the labelled DMP images.

image size -> {name: byte address}. Sources:
  3062  eMD 6.12 inv_mpu_dmp_motion_driver.c   (code labels + D_* data)
  2639  kernel hammerhead dmpDefaultMPU6050.c   (CFG_*/D_* ; validated 3/3 in bench round 8)
  1024  mlsdk dmpDefault.c                       (CFG_*/FCFG_* ; MPU-3050-style encoding)
  1923  mlsdk dmpDefaultMantis.c
Plus dmpmap.h names for the first 512 B of data RAM (6050 / 1024 image layout).
"""
import re, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "corpus"
DEF = re.compile(r'^\s*#define\s+([A-Za-z_]\w*)\s+(.+?)\s*$', re.M)
NUM = re.compile(r'^[\s()0-9xXa-fA-F+*\-]+$')

def parse_defines(path, keep=None):
    out = {}
    text = pathlib.Path(path).read_text(errors="ignore")
    for m in DEF.finditer(text):
        name, expr = m.group(1), m.group(2).split("//")[0].split("/*")[0].strip()
        if not NUM.match(expr):
            continue
        try:
            v = eval(expr.replace("0X", "0x"), {"__builtins__": {}})
        except Exception:
            continue
        if keep and not keep(name):
            continue
        out[name] = int(v)
    return out

CODE_LABEL = lambda n: bool(re.match(r'(CFG_|FCFG_|END_|SKIP_|X_GRT|SWING|TILT|FLAT|UPDATE|DO_NOT|CGNOTICE|TEMPLABEL)', n))
DATA_LABEL = lambda n: bool(re.match(r'(D_|CPASS|FLICK_|DMP_)', n))

def symbols():
    s = {}
    e = SRC / "sources_external/emd612__inv_mpu_dmp_motion_driver.c"
    s[3062] = parse_defines(e, lambda n: CODE_LABEL(n) or DATA_LABEL(n))
    h = SRC / "sources_kernel/hammerhead-kk__dmpDefaultMPU6050.c"
    s[2639] = parse_defines(h, lambda n: CODE_LABEL(n) or DATA_LABEL(n))
    s[1024] = parse_defines(SRC / "sources/ics-mr0__mlsdk__mllite__dmpDefault.c", CODE_LABEL)
    s[1923] = parse_defines(SRC / "sources/ics-mr0__mlsdk__mllite__dmpDefaultMantis.c", CODE_LABEL)
    for k in s:
        s[k] = {n: v for n, v in s[k].items() if 0 <= v < 16384}
    return s

def dmpmap():
    return parse_defines(SRC / "sources/ics-mr0__mlsdk__mllite__dmpmap.h", lambda n: n.startswith("DMP_"))

def dmp3map():
    """DMP3 (ICM-20948) data labels: the SparkFun ICM_20948_DMP.h `#define X (page * 16 + off)`
    family.  Addresses are DMP memory addresses (the image loads at 0x90, so they are not
    image offsets).  Names that are not memory addresses (sizes, bit masks) are dropped by
    keeping only values below 0x1000."""
    d = parse_defines(SRC / "sources_external/sparkfun_ICM_20948_DMP.h")
    skip = ("DMP_START_ADDRESS", "DMP_MEM_BANK_SIZE", "DMP_LOAD_START", "MAX_SERIAL_R_W", "DMP_CODE_SIZE")
    return {n: v for n, v in d.items() if 0 <= v < 0x1000 and n not in skip}

def code_labels(sym):
    return {n: v for n, v in sym.items() if CODE_LABEL(n)}

def data_labels(sym):
    return {n: v for n, v in sym.items() if DATA_LABEL(n)}

if __name__ == "__main__":
    for size, tab in symbols().items():
        c, d = code_labels(tab), data_labels(tab)
        print(f"{size}: {len(c)} code labels, {len(d)} data labels")
    print(f"dmpmap: {len(dmpmap())} names")
