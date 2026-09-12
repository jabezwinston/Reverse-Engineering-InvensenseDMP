#!/usr/bin/env python3
"""What is in the ICM-20948's DMP RAM before we load anything?  Compare against the
vendor image at its load address (0x90) and report the match ratio per 1 KB."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *

d = ICM(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
mem = d.mem_read(0, 0x4000)
img = IMAGE.read_bytes()
pathlib.Path("/tmp/icm_ram_before_load.bin").write_bytes(mem)
print("image bytes matching RAM at 0x90:", sum(1 for i, x in enumerate(img) if mem[0x90 + i] == x), "/", len(img))
for k in range(0, 0x4000, 1024):
    seg = mem[k:k + 1024]
    print(f"  {k:#06x}: nonzero {sum(1 for x in seg if x):4d}/1024  head {seg[:12].hex()}")
