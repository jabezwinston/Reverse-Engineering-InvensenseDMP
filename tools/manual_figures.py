"""Write the manual's SVG figures into docs/manual/figures (one shared style, light and dark).

    python3 tools/manual_figures.py
"""
import math
import pathlib

OUT = pathlib.Path(__file__).resolve().parents[1] / "docs" / "manual" / "figures"
STYLE = pathlib.Path(__file__).with_name("manual_figures.style.svgpart").read_text()


def svg(name, w, h, title, desc, body):
    text = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'role="img" aria-labelledby="t d">\n<title id="t">{title}</title>\n<desc id="d">{desc}</desc>\n'
            f'{STYLE}<rect class="bg" x="0" y="0" width="{w}" height="{h}"/>\n{body}\n</svg>\n')
    (OUT / name).write_text(text)


def box(x, y, w, h, cls="box", rx=4):
    return f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}"/>'


def txt(x, y, s, cls="t", anchor="middle"):
    return f'<text class="{cls}" x="{x}" y="{y}" text-anchor="{anchor}">{s}</text>'


def arrow(x1, y1, x2, y2, cls="ln"):
    return f'<line class="{cls}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" marker-end="url(#ah)"/>'


def path(d, cls="ln", end=True):
    return f'<path class="{cls}" d="{d}"' + (' marker-end="url(#ah)"' if end else "") + "/>"


# ---------------------------------------------------------------------------- 1-1 block diagram
b = []
# pointers
for i, (name, role) in enumerate((("P0", "A operand · MOV source"), ("P1", "B operand"),
                                  ("P2  + word w", "destination"))):
    y = 70 + 66 * i
    b += [box(16, y, 170, 50), txt(101, y + 21, name, "tb"), txt(101, y + 39, role, "s")]
    b += [arrow(186, y + 25, 226, y + 25)]
b += [txt(101, 60, "block · bank · page", "s")]
b += [txt(101, 284, "MPU: xchg01 / xchg02 exchange", "s"), txt(101, 298, "P0 with P1 / with P2", "s")]
b += [box(16, 316, 170, 46), txt(101, 335, "PC", "tb"), txt(101, 352, "from PRGM_START, every pass", "s")]
b += [box(16, 374, 170, 46, "dmp3"), txt(101, 393, "return stack (DMP3)", "t"),
      txt(101, 410, "4 entries, circular", "s")]
# memory
b += [box(226, 40, 150, 380), txt(301, 64, "DMP memory", "tb"), txt(301, 84, "code and data", "s"),
      txt(301, 104, "MPU-6050: 3 KB", "s"), txt(301, 120, "ICM-20948: 16 KB", "s"),
      txt(301, 380, "sample page: rewritten", "s"), txt(301, 395, "by the hardware", "s"),
      txt(301, 410, "at every tick", "s")]
# predicate, ALU, mode, R, F, route, FIFO, shifter
b += [box(436, 16, 170, 44, "warm"), txt(521, 35, "predicate", "tb"),
      txt(521, 51, "if f · if nf · always", "s"), arrow(521, 60, 521, 84)]
b += [box(436, 84, 170, 88, "hot"), txt(521, 110, "ALU", "tb"), txt(521, 129, "32-bit, or a 16-bit lane", "s"),
      txt(521, 145, "add rsub mul nmul mac", "s"), txt(521, 161, "clamp cmp and xor", "s")]
b += [arrow(376, 110, 436, 110), txt(406, 103, "A", "m"), arrow(376, 150, 436, 150), txt(406, 143, "B", "m")]
b += [box(640, 96, 108, 64), txt(694, 120, "mode", "tb"), txt(694, 138, "register", "tb"),
      txt(694, 153, "f0–f7", "m"), arrow(640, 128, 606, 128)]
b += [arrow(521, 172, 521, 204)]
b += [box(436, 204, 170, 56, "hot"), txt(521, 226, "R", "tb"), txt(521, 244, "64-bit result · MAC sum", "s")]
b += [arrow(606, 232, 640, 232), box(640, 204, 108, 56), txt(694, 226, "F", "tb"), txt(694, 244, "the one flag", "s")]
b += [arrow(521, 260, 521, 292)]
b += [box(436, 292, 170, 50, "warm"), txt(521, 313, "route", "tb"), txt(521, 330, "store · fifo", "s")]
b += [arrow(436, 317, 376, 317), txt(406, 309, "M[P2]", "s")]
b += [arrow(606, 317, 640, 317), box(640, 292, 108, 50), txt(694, 313, "FIFO", "tb"),
      txt(694, 330, "1 KB · 4 KB", "s")]
b += [box(436, 370, 170, 50, "dmp3"), txt(521, 391, "shifter (DMP3)", "t"), txt(521, 408, "4 words, loaded from R", "s")]
b += [box(640, 370, 108, 50, "dmp3"), txt(694, 391, "I/O space", "t"), txt(694, 408, "mode 4 (DMP3)", "s")]
svg("block-diagram.svg", 764, 436, "DMP programmer's model",
    "Three pointers address one memory. Operands A and B feed the ALU, whose result goes into the "
    "result register R and sets the flag F, then through the route latch to memory at P2 or to the "
    "FIFO. A predicate gates every instruction; the mode register selects the ALU's operation set. "
    "DMP3 adds a return stack, a shifter and a register I/O space (dashed).", "\n".join(b))

# ---------------------------------------------------------------------------- 1-2 pass timeline
b = []
T0, P = 70, 200                       # first tick, period in px
for lane, (y, label) in enumerate(((44, "MPU-6050: a pass shorter than the period"),
                                   (154, "MPU-6050: a pass that overruns the period"),
                                   (264, "ICM-20948: a pass that overruns the period"))):
    b += [txt(16, y - 14, label, "tb", "start"), f'<line class="ln" x1="40" y1="{y + 40}" x2="744" y2="{y + 40}"/>']
    for k in range(4):
        x = T0 + P * k
        b += [f'<line class="ln" x1="{x}" y1="{y + 32}" x2="{x}" y2="{y + 48}"/>', txt(x, y + 62, "tick", "s")]
    if lane == 0:
        for k in range(3):
            x = T0 + P * k
            b += [box(x + 14, y + 6, 110, 26, "hot"), txt(x + 69, y + 24, "pass", "t")]
        b += [txt(T0 + 140, y + 24, "idle", "s", "start")]
    elif lane == 1:
        b += [box(T0 + 14, y + 6, 246, 26, "hot"), txt(T0 + 137, y + 24, "pass", "t")]
        b += [f'<line class="lnd" x1="{T0 + P}" y1="{y}" x2="{T0 + P}" y2="{y + 32}"/>',
              txt(T0 + P, y - 2, "samples rewritten", "s")]
        b += [txt(T0 + 268, y + 24, "waits for a tick", "s", "start")]
        b += [box(T0 + 2 * P + 14, y + 6, 246, 26, "hot"), txt(T0 + 2 * P + 137, y + 24, "next pass", "t")]
    else:
        b += [box(T0 + 18, y + 6, 246, 26, "hot"), txt(T0 + 141, y + 24, "pass", "t")]
        b += [box(T0 + 280, y + 6, 246, 26, "hot"), txt(T0 + 403, y + 24, "next pass", "t")]
        b += [txt(T0 + 272, y - 2, "~150 cycles", "s")]
b += [txt(16, 372, "The first instruction runs 110 cycles (MPU) or 130 cycles (ICM) after its tick.", "s", "start")]
svg("pass-timeline.svg", 760, 384, "When a pass runs",
    "A sample tick starts a pass about 110 (MPU) or 130 (ICM) cycles later; the pass runs to end. "
    "On the MPU a pass that overruns the period waits for the next tick, so the rate drops to a "
    "whole fraction of the sample rate; on the ICM the next pass starts as soon as the previous one "
    "ends. The hardware rewrites the sample page at every tick, even under a running pass.",
    "\n".join(b))

# ---------------------------------------------------------------------------- 2-1 MPU memory map
b = []
X, W, Y0, H = 250, 150, 30, 360        # 0x000 at Y0, 0xC00 at Y0 + H
def ya(a): return Y0 + H * a / 0xC00
b += [box(X, ya(0), W, ya(0x400) - ya(0), "hot"), box(X, ya(0x400), W, ya(0xC00) - ya(0x400))]
b += [box(X, ya(0), W, 14, "warm"), txt(X + W / 2, ya(0) + 11, "sample page", "s")]
b += [txt(X + W / 2, ya(0x200), "block 0", "tb"), txt(X + W / 2, ya(0x200) + 18, "pointer window", "s"),
      txt(X + W / 2, ya(0x800), "blocks 1–2", "tb"), txt(X + W / 2, ya(0x800) + 18, "code", "s")]
for a, s in ((0, "0x000"), (0x400, "0x400"), (0xBFF, "0xBFF")):
    yy = ya(a) + (10 if a == 0xE else 4 if a == 0 else 4)
    b += [txt(X - 10, yy, s, "m", "end")]
notes = [(ya(0) + 7, "0x000–0x00D: ax ay az temp gx gy gz, int16, written every tick"),
         (ya(0x200), "data: every pointer reaches it without a block"),
         (ya(0x400) + 14, "default entry: code here is out of P2's reach"),
         (ya(0x800), "code and data; data through p0blk / p1blk / p2blk"),
         (ya(0xBFF), "the last byte of code or data")]
for yy, s in notes:
    b += [f'<line class="lnd" x1="{X + W}" y1="{yy}" x2="{X + W + 24}" y2="{yy}"/>', txt(X + W + 30, yy + 4, s, "s", "start")]
b += [box(16, 300, 190, 60), txt(111, 322, "FIFO, 1024 B", "tb"), txt(111, 340, "outside this map:", "s"),
      txt(111, 354, "read through FIFO_R_W", "s")]
b += [txt(X + W / 2, Y0 + H + 22, "0xC00–0xFFF: not memory (reads 0)", "s")]
svg("memory-map-mpu.svg", 760, 420, "MPU-6050 DMP memory map",
    "3 KB of DMP memory, 0x000 to 0xBFF. The sample page at 0x000 to 0x00D is rewritten every tick. "
    "Block 0 (0x000 to 0x3FF) is what a pointer reaches without the block field; 0x400 to 0xBFF "
    "holds the code, and data through the block field. The 1 KB FIFO is not in the map.",
    "\n".join(b))

# ---------------------------------------------------------------------------- 2-2 ICM memory map
b = []
X, W, Y0, H = 250, 150, 30, 380        # 0x0000 at Y0, 0x4000 at Y0 + H
def yi(a): return Y0 + H * a / 0x4000
b += [box(X, yi(0), W, yi(0x1000) - yi(0), "hot"), box(X, yi(0x1000), W, yi(0x3000) - yi(0x1000)),
      box(X, yi(0x3000), W, yi(0x4000) - yi(0x3000), "warm")]
b += [box(X, yi(0), W, 14, "warm"), txt(X + W / 2, yi(0) + 11, "sample page", "s")]
b += [txt(X + W / 2, yi(0x800), "data window", "tb"), txt(X + W / 2, yi(0x800) + 18, "blocks 0–3", "s"),
      txt(X + W / 2, yi(0x2000), "code", "tb"), txt(X + W / 2, yi(0x2000) + 18, "default entry 0x1000", "s"),
      txt(X + W / 2, yi(0x3800), "FIFO", "tb"), txt(X + W / 2, yi(0x3800) + 18, "4 KB ring", "s")]
for a, s in ((0, "0x0000"), (0x1000, "0x1000"), (0x3000, "0x3000"), (0x3FFF, "0x3FFF")):
    b += [txt(X - 10, yi(a) + 4, s, "m", "end")]
notes = [(yi(0) + 7, "0x0000–0x0003 cleared, 0x0004–0x0011 samples, every tick"),
         (yi(0x80) + 18, "0x0080–0x0087: written by a device reset"),
         (yi(0x800) + 10, "every pointer reaches 0x0000–0x0FFF"),
         (yi(0x2000), "code may also sit below 0x1000"),
         (yi(0x3800), "every FIFO byte lands here; newest kept")]
for yy, s in notes:
    b += [f'<line class="lnd" x1="{X + W}" y1="{yy}" x2="{X + W + 24}" y2="{yy}"/>', txt(X + W + 30, yy + 4, s, "s", "start")]
b += [box(16, 160, 160, 104, "dmp3"), txt(96, 182, "I/O space (mode 4)", "tb"),
      txt(96, 202, "a page load in mode 4", "s"), txt(96, 217, "reaches host registers:", "s"),
      txt(96, 232, "word a = register a/4", "s"), txt(96, 247, "blocks 0–1 = banks 0–3", "s")]
svg("memory-map-icm.svg", 760, 430, "ICM-20948 DMP memory map",
    "16 KB of DMP memory, 0x0000 to 0x3FFF. The sample page at the bottom is rewritten every tick; "
    "pointers reach the 4 KB data window 0x0000 to 0x0FFF; code runs from anywhere below 0x3000, by "
    "default from 0x1000; 0x3000 to 0x3FFF is the FIFO, a 4 KB ring. In mode 4 a page load addresses "
    "the host register file instead (inset).", "\n".join(b))

# ---------------------------------------------------------------------------- 2-3 address formation
b = []
fields = [("block", 2, "p0blk p1blk p2blk", "11–10"), ("bank", 2, "p0bank n …", "9–8"),
          ("page", 4, "p0page n …", "7–4"), ("word", 2, "A, B field · P2.w", "3–2"), ("byte", 2, "0", "1–0")]
x = 60
cw = 52
for name, n, who, bits in fields:
    w = n * cw
    b += [box(x, 60, w, 44, "hot" if name != "byte" else "box"), txt(x + w / 2, 87, name, "tb"),
          txt(x + w / 2, 50, bits, "m"), txt(x + w / 2, 124, who, "s")]
    x += w
b += [txt(16, 30, "A pointer's address, 12 bits (MPU-6050: block 0–2, 0x000–0xBFF; ICM-20948: block 0–3, 0x0000–0x0FFF)", "t", "start")]
rows = [("operand A", "M[ P0 + 4·a ]", "a = bits 6–5 of the ALU byte"),
        ("operand B", "M[ P1 + 4·b ]", "b = bits 4–3 of the ALU byte"),
        ("destination", "M[ P2 + 4·w ]", "w = P2's word index: p2page sets 0; adv, .next, p2inc2 walk it")]
for i, (who, f, how) in enumerate(rows):
    y = 170 + 34 * i
    b += [txt(60, y, who, "tb", "start"), txt(200, y, f, "m", "start"), txt(360, y, how, "s", "start")]
svg("address-formation.svg", 760, 280, "How an operand address is formed",
    "A pointer holds a block, a bank and a page; the word within the page comes from the ALU byte "
    "for the two operands and from P2's walked word index for the destination.", "\n".join(b))

# ---------------------------------------------------------------------------- 2-4 word formats
b = []
X0, CW = 140, 18                        # 32 bit cells
def cells(y, groups):
    out, x = [], X0
    for n, label, cls in groups:
        out += [box(x, y, n * CW, 30, cls, 2), txt(x + n * CW / 2, y + 20, label, "t")]
        x += n * CW
    return out
for bit, xx in ((31, X0), (16, X0 + 15 * CW), (15, X0 + 16 * CW), (0, X0 + 31 * CW)):
    b += [txt(xx + CW / 2, 30, str(bit), "m")]
rows = [("integer", [(1, "s", "hot"), (31, "two's complement, −2³¹ … 2³¹ − 1", "box")]),
        ("Q30", [(1, "s", "hot"), (1, "i", "warm"), (30, "value = word / 2³⁰: from −2.0 to just under +2.0", "box")]),
        ("lanes", [(16, "high lane (f2, f6)", "box"), (16, "low lane (f3, f7)", "box")]),
        ("MPU samples", [(16, "ax · az · gx · gz", "warm"), (16, "ay · temp · gy · —", "warm")]),
        ("ICM samples", [(16, "0 · ax · az · gy · temp", "warm"), (16, "0 · ay · gx · gz · —", "warm")])]
for i, (label, groups) in enumerate(rows):
    y = 44 + 46 * i
    b += [txt(X0 - 12, y + 20, label, "tb", "end")] + cells(y, groups)
b += [txt(X0, 290, "Samples: int16 pairs. MPU: words 0–3 at 0x000. ICM: words 0–4 at 0x0000, word 0 cleared.", "s", "start")]
svg("word-formats.svg", 740, 300, "Word formats",
    "A 32-bit big-endian word read as a two's-complement integer, as Q30 fixed point (sign, one "
    "integer bit, 30 fraction bits), as two 16-bit lanes, and as the int16 sample pairs the "
    "hardware writes.", "\n".join(b))

# ---------------------------------------------------------------------------- 3-1 mode register
b = []
modes = [("f0", "MAC"), ("f1", "32-bit"), ("f2", "high lane"), ("f3", "low lane"),
         ("f5", "logic"), ("f6", "logic, high"), ("f7", "logic, low")]
for i, (m, s) in enumerate(modes):
    x = 30 + 100 * i
    b += [box(x, 40, 88, 52, "hot"), txt(x + 44, 62, m, "m"), txt(x + 44, 80, s, "s")]
b += [txt(380, 24, "fmode m: the ALU byte's meaning (sticky, kept across passes; DMP_RST gives f1)", "t")]
b += [box(200, 170, 360, 120, "warm"), txt(380, 192, "mode 4", "tb"),
      txt(380, 214, "MPU-6050: byte 00–3F = one-byte branch (branch.m4)", "s"),
      txt(380, 230, "40–7F reserved; MOV, CLR, INC, page loads run", "s"),
      txt(380, 252, "ICM-20948: byte 00–7F = two-byte jump/call target", "s"),
      txt(380, 268, "page loads address the I/O space", "s")]
b += [path("M 150 92 C 150 140, 220 150, 260 170"), txt(140, 140, "from any mode, any F4: branch,", "s", "end"),
      txt(140, 154, "jump, call; taken, not or skipped", "s", "end")]
b += [path("M 520 170 C 560 150, 620 140, 620 92"), txt(632, 140, "fmode m ends it", "s", "start")]
svg("mode-register.svg", 760, 310, "The mode register",
    "fmode sets one of seven ALU modes. Every F4 byte, whatever it does and even when a predicate "
    "skips it, puts the machine in mode 4, where low bytes are branch targets rather than ALU "
    "operations; an fmode ends mode 4.", "\n".join(b))

# ---------------------------------------------------------------------------- 3-2 return stack
b = []
cx, cy, r = 190, 150, 80
for k in range(4):
    a = math.radians(-90 + 90 * k)
    x, y = cx + r * math.cos(a), cy + r * math.sin(a)
    b += [box(x - 46, y - 18, 92, 36, "hot"), txt(x, y + 5, f"slot {k}", "m")]
for k in range(4):
    a1, a2 = math.radians(-90 + 90 * k + 30), math.radians(-90 + 90 * k + 60)
    x1, y1 = cx + (r + 4) * math.cos(a1), cy + (r + 4) * math.sin(a1)
    x2, y2 = cx + (r + 4) * math.cos(a2), cy + (r + 4) * math.sin(a2)
    b += [path(f"M {x1:.1f} {y1:.1f} A {r + 4} {r + 4} 0 0 1 {x2:.1f} {y2:.1f}")]
b += [txt(cx, cy - 4, "sp", "tb"), txt(cx, cy + 14, "next slot", "s")]
b += [txt(330, 70, "call t: slot[sp] := return address; sp := sp + 1 (mod 4)", "m", "start"),
      txt(330, 96, "ret:    sp := sp − 1 (mod 4); PC := slot[sp]", "m", "start"),
      txt(330, 136, "A fifth nested call overwrites the oldest entry: the", "s", "start"),
      txt(330, 152, "returns then cycle through the four newest callers.", "s", "start"),
      txt(330, 182, "The stack and sp survive end: a ret in a later pass", "s", "start"),
      txt(330, 198, "pops what an earlier pass pushed.", "s", "start")]
svg("return-stack.svg", 760, 260, "The DMP3 return stack",
    "Four return-address slots used as a ring by call and ret; a fifth nested call overwrites the "
    "oldest, and the stack survives the end of a pass.", "\n".join(b))

# ---------------------------------------------------------------------------- 3-3 shifter
b = []
b += [box(16, 40, 180, 50, "hot"), txt(106, 62, "R (64-bit)", "tb"), txt(106, 80, "after mul: the product", "s")]
b += [arrow(196, 65, 300, 65), txt(248, 57, "every op", "s"), txt(248, 82, "writing R", "s")]
for k, (lab, sub) in enumerate((("word 0", "R's word"), ("word 1", "R's low 30 bits"), ("word 2", "0"), ("word 3", "0"))):
    x = 300 + 110 * k
    b += [box(x, 40, 104, 50), txt(x + 52, 62, lab, "tb"), txt(x + 52, 80, sub, "s")]
b += [box(300, 120, 434, 40, "warm"), txt(517, 145, "load k: the four words of P0's page; select word k", "t")]
b += [txt(30, 200, "shl s", "m", "start"), txt(110, 200, "each word := (word &lt;&lt; s) | the top s bits of the next word's 30-bit fraction", "s", "start"),
      txt(30, 224, "sar s", "m", "start"), txt(110, 224, "each word := word &gt;&gt; s, arithmetic", "s", "start"),
      txt(30, 248, "then", "m", "start"), txt(110, 248, "store the selected word through the route; R := that word", "s", "start"),
      txt(30, 282, "mul a,b; shl 30", "m", "start"), txt(170, 282, "stores a·b mod 2³²: the integer product", "s", "start")]
svg("shifter.svg", 760, 300, "The DMP3 shifter",
    "A four-word register loaded from R by every operation that writes R (word 0 R's word, word 1 "
    "R's low 30 bits) or from P0's page by load; shl and sar shift all four words and store the "
    "selected one.", "\n".join(b))
print("ok")
