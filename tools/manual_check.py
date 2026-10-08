#!/usr/bin/env python3
"""Check docs/manual: every example runs as it says, no banned terms, every link resolves.

    python3 tools/manual_check.py --asm       assemble and run every ```asm block in the emulator
    python3 tools/manual_check.py --banned    the manual states conclusions only (no history,
                                              no evidence tags, no vendor firmware)
    python3 tools/manual_check.py --links     relative links, anchors and figures resolve
    python3 tools/manual_check.py --all       all three (the default)

An example is a fenced block whose info string starts with `asm` and names its core:
`asm mpu6050`, `asm icm20948` or `asm both`.  A block with `.chip` is a whole program.  Any
other block runs inside the definitions harness (`harness=defs`): P0 -> 0x100, P1 -> 0x110,
P2 -> 0x120, mode f1, no predicate, results to RAM, then the block, then `end`.

Checked comments, anywhere in a block:

    ; given 0x100 = 0.75q, 3i, 7fffffff     words written before the first pass
    ; sample ax=100 gz=-5                   the sample every pass sees
    ; passes 3                              run three passes (default 1)
    ; expect 0x120 = 1.25q                  words in memory afterwards
    ; expect fifo = 40000000 0001           the FIFO's bytes, in hex
    ; expect F = 1                          the flag after the last pass
    ; expect R = 2i                         the result register's word
    ; expect ints = 1                       interrupts raised in the last pass
    ; expect cycles = 133                   cycles of the last pass, tick to end
    ; expect bytes = f4 37                  the block's own bytes (harness blocks only)
    ; expect error "mode 4"                 assembly fails with this text
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANUAL = ROOT / "docs" / "manual"
sys.path.insert(0, str(ROOT.parent / "opendmp"))
from opendmp.emu import Machine, Sample                    # noqa: E402
from opendmp.emu.machine import DmpFault, Unmodelled      # noqa: E402
from opendmp.isa import AsmError, assemble                # noqa: E402
from opendmp.q30 import parse_word                        # noqa: E402

MPU, ICM = "mpu6050", "icm20948"
ENTRY = {MPU: 0x400, ICM: 0x1000}
HARNESS = ("fmode 1\nalways\nstore\np0bank 1\np0page 0\np1bank 1\np1page 1\np2bank 1\np2page 2\n")
FENCE = re.compile(r"^```asm(?P<info>[^\n]*)\n(?P<body>.*?)^```", re.M | re.S)


# --------------------------------------------------------------------------- examples
def blocks(path):
    text = path.read_text()
    for m in FENCE.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        info = m.group("info").split()
        body = m.group("body")
        chips = [MPU, ICM] if "both" in info else [c for c in (MPU, ICM) if c in info]
        mc = re.search(r"^\s*\.chip\s+(\S+)", body, re.M)
        if mc:
            chips = [MPU if "mpu" in mc.group(1) else ICM]
        yield line, chips, body, bool(mc)


def words_of(text):
    return [parse_word(t) for t in re.split(r"[,\s]+", text.strip()) if t]


def directives(body):
    d = {"given": [], "expect": [], "sample": None, "passes": 1}
    for raw in body.splitlines():
        if ";" not in raw:
            continue
        c = raw.split(";", 1)[1].strip()
        m = re.match(r"given\s+(0x[0-9a-fA-F]+)\s*=\s*(.+)$", c)
        if m:
            d["given"].append((int(m.group(1), 16), words_of(m.group(2))))
            continue
        m = re.match(r"sample\s+(.+)$", c)
        if m:
            d["sample"] = Sample(**{k: int(v, 0) for k, v in (kv.split("=") for kv in m.group(1).split())})
            continue
        m = re.match(r"passes\s+(\d+)$", c)
        if m:
            d["passes"] = int(m.group(1))
            continue
        m = re.match(r"expect\s+(.+)$", c)
        if m:
            d["expect"].append(m.group(1).strip())
    return d


def run_block(chip, body, whole):
    """Errors (a list of strings) for one block on one core."""
    d = directives(body)
    e = ENTRY[chip]
    src = body if whole else f".chip {chip}\n.entry {e:#x}\n.org {e:#x}\n{HARNESS}{body}\nend\n"
    want_err = [x for x in d["expect"] if x.startswith("error")]
    try:
        prog = assemble(src, chip)
    except AsmError as err:
        if want_err and want_err[0].split('"')[1] in str(err):
            return []
        return [f"assembly failed: {err}"]
    if want_err:
        return [f"assembled, but {want_err[0]} was expected"]
    m = Machine(chip)
    for a, data in prog.segments():
        m.load(data, a)
    m.entry = prog.entry
    for a, ws in d["given"]:
        m.poke_words(a, ws)
    try:
        for _ in range(d["passes"]):
            res = m.run_pass(d["sample"] or Sample())
    except (Unmodelled, DmpFault) as err:
        return [f"the emulator stopped: {err}"]
    errs = []
    for x in d["expect"]:
        mm = re.match(r"(0x[0-9a-fA-F]+)\s*=\s*(.+)$", x)
        if mm:
            a = int(mm.group(1), 16)
            want = [w & 0xFFFFFFFF for w in words_of(mm.group(2))]
            got = [m.peek_word(a + 4 * i) & 0xFFFFFFFF for i in range(len(want))]
            if got != want:
                errs.append(f"{x}: memory holds {' '.join(f'{g:08x}' for g in got)}")
        elif x.startswith("fifo"):
            want = re.sub(r"\s", "", x.split("=", 1)[1]).lower()
            if bytes(res.fifo).hex() != want:
                errs.append(f"{x}: the FIFO got {bytes(res.fifo).hex() or 'nothing'}")
        elif x.startswith("F"):
            if int(m.f) != int(x.split("=")[1]):
                errs.append(f"{x}: F is {int(m.f)}")
        elif x.startswith("R"):
            want = parse_word(x.split("=")[1].strip()) & 0xFFFFFFFF
            if m._r_word() != want:
                errs.append(f"{x}: R's word is {m._r_word():08x}")
        elif x.startswith("ints"):
            if res.ints != int(x.split("=")[1]):
                errs.append(f"{x}: {res.ints} interrupts")
        elif x.startswith("cycles"):
            if res.cycles != int(x.split("=")[1]):
                errs.append(f"{x}: {res.cycles} cycles")
        elif x.startswith("bytes"):
            want = re.sub(r"\s", "", x.split("=", 1)[1]).lower()
            head = len(assemble(f".chip {chip}\n.entry {e:#x}\n.org {e:#x}\n{HARNESS}", chip).code())
            got = prog.code()[head:-1].hex()
            if got != want:
                errs.append(f"{x}: the block assembles to {got}")
        else:
            errs.append(f"unknown expectation {x!r}")
    return errs


def check_asm() -> int:
    bad = n = 0
    for path in sorted(MANUAL.glob("*.md")):
        for line, chips, body, whole in blocks(path):
            if not chips:
                print(f"{path.name}:{line}: asm block names no core (asm mpu6050 | icm20948 | both)")
                bad += 1
                continue
            for chip in chips:
                n += 1
                for err in run_block(chip, body, whole):
                    print(f"{path.name}:{line} [{chip}]: {err}")
                    bad += 1
    print(f"asm: {n} block runs, {bad} problems")
    return bad


# --------------------------------------------------------------------------- banned terms
BANNED = [
    (r"\b(1024|1923|1929|1962|2634|2639|2943|3035|3062|3065|14290|14301)[- ]?(B|byte)?\s*image", "a stock image"),
    (r"(?<!memory )\bimages?\b", "firmware images"),
    (r"Family [AB]\b", "image families"),
    (r"MotionApps|\beMD\b|mlsdk|dmpmap|dmpKey|DINA[0-9A-F]|DINB|i2cdevlib|SparkFun|ml_load_dmp|"
     r"\binv_|DMP_FEATURE|dmpDefault", "vendor software"),
    (r"\bcorpus\b|\bpatch(ing|es|ed)?\b|selbank|dmpasm|\.lineage|\bmantis\b|\blineage\b|MPU-?3050", "the old toolchain or lineage"),
    (r"\[(HW|VENDOR|INFER|STATIC|measured|firmware|constructed)\b", "evidence tags"),
    (r"\bFindings?\s+\d|\bprobe\d|\bprobes?\b|\bISA2\b|FINDINGS|UNKNOWNS", "research citations"),
    (r"\bvendor|\bstock\b|\bshipped\b|\bshipping\b", "the vendor's firmware"),
    (r"\bearlier (edition|reading|readings)|\bwas (wrong|read as)|\bcorrected\b|\bwithdraw|"
     r"\bpreviously\b|\bused to be\b|\bno longer\b|\bit turned out\b|\bwe (found|thought)\b", "history"),
    (r"TMP1[AB]|\bQT[1-4]\b|\b0_0\b|constant page|scratch page", "the vendor's data map"),
    (r"99\.9|17297|10349|17284", "coverage statistics"),
]
ALLOW = {("README.md", "research citations")}           # the README's one pointer to the evidence


def check_banned() -> int:
    bad = 0
    files = sorted(MANUAL.glob("*.md")) + sorted((MANUAL / "figures").glob("*.svg"))
    for path in files:
        for no, line in enumerate(path.read_text().splitlines(), 1):
            for pat, what in BANNED:
                if (path.name, what) in ALLOW and "ISA2" in line:
                    continue
                if re.search(pat, line, re.I if what in ("history", "the vendor's firmware") else 0):
                    print(f"{path.relative_to(ROOT)}:{no}: {what}: {line.strip()[:110]}")
                    bad += 1
    print(f"banned: {bad} hits")
    return bad


# --------------------------------------------------------------------------- links
INBOUND = ["README.md", "UNKNOWNS.md", "FIRMWARE.md", "FINDINGS.md", "PLAN.md", "bench/README.md",
           "bench/RESULTS.md"]
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)|(?:href|src)=\"([^\"]+)\"")


def slug(heading: str) -> str:
    h = re.sub(r"<[^>]+>", "", heading).strip().lower()
    h = re.sub(r"[^\w\- ]", "", h)
    return h.replace(" ", "-")


def anchors(path: pathlib.Path) -> set:
    out, seen = set(), {}
    text = path.read_text()
    text = re.sub(r"^```.*?^```", "", text, flags=re.M | re.S)
    for m in re.finditer(r"^#{1,6}\s+(.+?)\s*$", text, re.M):
        s = slug(m.group(1))
        n = seen.get(s, 0)
        out.add(s if n == 0 else f"{s}-{n}")
        seen[s] = n + 1
    out |= set(re.findall(r"<a\s+id=\"([^\"]+)\"", text))
    out |= set(re.findall(r"\sid=\"([^\"]+)\"", text))
    return out


def check_links() -> int:
    bad = 0
    files = sorted(MANUAL.glob("*.md")) + [ROOT / f for f in INBOUND if (ROOT / f).exists()]
    for path in files:
        text = re.sub(r"^```.*?^```", "", path.read_text(), flags=re.M | re.S)
        for m in LINK.finditer(text):
            target = m.group(1) or m.group(2)
            if re.match(r"[a-z]+:", target) or target.startswith("mailto"):
                continue
            file, _, frag = target.partition("#")
            dest = (path.parent / file).resolve() if file else path
            if not dest.exists():
                print(f"{path.relative_to(ROOT)}: missing {target}")
                bad += 1
                continue
            if frag and dest.suffix == ".md" and frag not in anchors(dest):
                print(f"{path.relative_to(ROOT)}: no anchor #{frag} in {dest.relative_to(ROOT)}")
                bad += 1
    print(f"links: {bad} broken")
    return bad


def main():
    args = set(sys.argv[1:]) or {"--all"}
    bad = 0
    if args & {"--asm", "--all"}:
        bad += check_asm()
    if args & {"--banned", "--all"}:
        bad += check_banned()
    if args & {"--links", "--all"}:
        bad += check_links()
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
