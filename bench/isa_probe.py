#!/usr/bin/env python3
"""isa_probe - hardware experiments for the pointer/ALU model (ISA2.md, plan P2).

Everything here is a single-step RAM diff at the 5-byte site 1868 of the MotionApps20
(1929 B) image, where the pointer state is known from the decoder:

    1851 b0  P0.bank=0      1852 87  P0.page=7  -> A words at 0x70: 0.5 0.0 1.0 1.5 (Q30)
    1846 b4  P1.bank=0      1867 9d  P1.page=d  -> B words at 0xd0 (live control data)
    1854 b9  P2.bank=1      1855 a3  P2.page=3  -> D words at 0x130 (TMP1B..TMP4B scratch)
    1857/1863 f1            FIFO mode, 32-bit

Sub-commands (each prints a prediction before the measurement and a verdict after):

  store    write `a4 30` (P2.page=4 -> 0x140, op0 A=1 B=2).  Prediction: exactly one word
           in 0x140..0x14f changes; 0x144 if the destination index is the A field, 0x148 if B.
  optable  P1 <- page 6 (0x60: 0x00400000, 1.0, 0.0436, 0.5), P2 <- 0x140. For op 0..7 and
           three (A,B) pairs read the destination word and match it against
           A+B, A-B, B-A, A*B, -(A*B), B, A.
  pred     `d9 <op> d8` and `da <op> d8` around the same op: does the write happen?
  back     `f4 imm` for imm 0x80..0xff with three emits after it: FIFO bytes per step vs
           the no-branch baseline (a backward branch re-executes code -> longer packet).

  python3 isa_probe.py --port /dev/ttyUSB0 store|optable|pred|back [--trials 3]

Method notes carried over from rounds 18-20: interleaved control before every candidate,
a stability mask built at session start and re-checked, the patch site excluded, and every
verdict requires the same address set in every trial.
"""
import argparse, pathlib, sys, time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from dmpbench import Bridge, USER_CTRL          # noqa: E402
import dmpinit                                  # noqa: E402

HOST = HERE.parent / "corpus/images/d79e55736bb5ea91_1929.bin"
SITE, SITELEN = 1868, 5
RAM = 3072
PWR_MGMT_2 = 0x6C
Q30 = 2 ** 30


def q(v):
    v &= 0xFFFFFFFF
    return (v - (1 << 32) if v & 0x80000000 else v) / Q30


def word(snap, a):
    return int.from_bytes(snap[a:a + 4], "big")


class Rig:
    def __init__(self, port):
        self.tmp = "/tmp/_isa_probe_host.bin"
        pathlib.Path(self.tmp).write_bytes(HOST.read_bytes())
        self.b = Bridge(port)
        self.reinit()

    def reinit(self):
        dmpinit.dmp_init(self.b, self.tmp, verbose=False)
        self.b.wr(PWR_MGMT_2, 0x3F)            # sensors in standby: quieter RAM
        time.sleep(0.1)

    def step(self, payload):
        """Patch the site, run exactly one DMP interrupt, return (ram, int_count, fifo_bytes)."""
        b = self.b
        payload = bytes(payload)
        assert len(payload) <= SITELEN
        b.mem_write(SITE, payload + b"\xa3" * (SITELEN - len(payload)))
        b.wr(USER_CTRL, 0x00)
        b.cmd("Z")
        b.wr(USER_CTRL, 0x4C); b.wr(USER_CTRL, 0xC0)
        t0 = time.time(); fired = 0
        while time.time() - t0 < 0.5:
            fired = b.int_state()[1]
            if fired >= 1:
                break
        b.wr(USER_CTRL, 0x00)
        fifo = b.fifo_count()
        return b.mem_read(0, RAM), fired, fifo

    def safe(self, payload):
        try:
            return self.step(payload)
        except IOError:
            try:
                self.b._reset_and_sync(); self.reinit()
                return self.step(payload)
            except Exception:
                return None, 0, 0


def build_mask(rig, n):
    snaps = []
    for _ in range(n):
        s, _, _ = rig.safe([0xA3])
        if s is None:
            sys.exit("control step failed while building the mask")
        snaps.append(s)
    ref = snaps[0]
    site = set(range(SITE, SITE + SITELEN))
    mask = {i for i in range(RAM) if i not in site and all(s[i] == ref[i] for s in snaps[1:])}
    # tighten with extra controls
    for _ in range(4):
        s, _, _ = rig.safe([0xA3])
        if s is not None:
            mask -= {i for i in mask if s[i] != ref[i]}
    print(f"stability mask: {len(mask)}/{RAM} bytes")
    return mask


def diff_words(mask, ctrl, cand):
    changed = sorted(i for i in mask if ctrl[i] != cand[i])
    words = sorted({i & ~3 for i in changed})
    return changed, words


def measure(rig, mask, payload, trials):
    """Interleaved control vs candidate; returns the word addresses that changed in EVERY trial,
    plus the last candidate snapshot."""
    common = None; last = None
    for _ in range(trials):
        c, _, _ = rig.safe([0xA3])
        s, fired, fifo = rig.safe(payload)
        if c is None or s is None:
            print("   (step failed; retrying)"); continue
        _, words = diff_words(mask, c, s)
        common = set(words) if common is None else common & set(words)
        last = s
    return sorted(common or []), last


def cmd_store(rig, mask, a):
    print("STORE PROOF  payload a4 30 : P2.page=4 (bank 1 -> 0x140), op0 A=1 B=2")
    print("  prediction: one word in 0x140..0x14f changes; 0x144 => D index = A, 0x148 => D index = B")
    words, snap = measure(rig, mask, [0xA4, 0x30], a.trials)
    hits = [w for w in words if 0x140 <= w < 0x150]
    print(f"  reproducible changed words: {[hex(w) for w in words]}")
    if hits == [0x144]:
        print("  VERDICT: destination = P2 + 4*A")
    elif hits == [0x148]:
        print("  VERDICT: destination = P2 + 4*B")
    elif not hits:
        print("  VERDICT: no write in the P2 page. Either ops do not write in FIFO mode "
              "(retry with f0 first: payload f0 a4 30) or P2 is not the destination.")
        words2, _ = measure(rig, mask, [0xF0, 0xA4, 0x30], a.trials)
        print(f"  with f0 prefix: {[hex(w) for w in words2]}")
    else:
        print(f"  VERDICT: unexpected pattern {[hex(w) for w in hits]}")
    if snap is not None and hits:
        v = word(snap, hits[0]); src = word(snap, 0xD0 + 8)
        print(f"  value written = {v:08x} ({q(v):+.6f}); M[P1+4*2]=M[0xd8] now {src:08x}")


CONST_A = {0: 0.5, 1: 0.0, 2: 1.0, 3: 1.5}                      # page 0x70
CONST_B = {0: 0x00400000 / Q30, 1: 1.0, 2: 0x02CB47A2 / Q30, 3: 0.5}  # page 0x60 (1929 image)


def candidates(av, bv):
    return {"A+B": av + bv, "A-B": av - bv, "B-A": bv - av, "A*B": av * bv,
            "-(A*B)": -av * bv, "B": bv, "A": av, "A+B+A": 2 * av + bv}


def cmd_optable(rig, mask, a):
    """Confirmed-store op table. Payload `97 ba a4 <op> dc` at the 5-byte site:
       97 -> P1.page=7 (P1=0x70), ba a4 -> P2=0x240, <op> ALU byte, dc -> store to M[0x240].
    P0 stands at 0x70 too, so BOTH operands are the Q30 constant page {0.5,0.0,1.0,1.5}.
    op byte = (A<<5)|(B<<3)|op ; result read back from 0x240 and matched against A op B."""
    CONST = {0: 0.5, 1: 0.0, 2: 1.0, 3: 1.5}
    P2 = 0x240
    print("OP TABLE via dc: P0=P1=0x70 (Q30 0.5/0.0/1.0/1.5), P2=0x240, payload dc 97 ba a4 <op>")
    # sanity: op0 A2 B0 = 1.0 + 0.5 should give +1.5
    pairs = [(2, 0), (2, 1), (0, 0), (3, 1), (2, 3)]   # (A,B): 1.0+0.5, 1.0+0.0, 0.5+0.5, 1.5+0.0, 1.0+1.5
    for op in range(8):
        for A, B in pairs:
            v = (A << 5) | (B << 3) | op
            rig.b.mem_write(P2, bytes(4))
            words, snap = measure(rig, mask, [0xDC, 0x97, 0xBA, 0xA4, v], a.trials)
            if snap is None:
                print(f"  op{op} A={A}(={CONST[A]}) B={B}(={CONST[B]}) byte {v:02x}: CRASH"); continue
            val = q(word(snap, P2))
            av, bv = CONST[A], CONST[B]
            cand = {"A+B": av+bv, "A-B": av-bv, "B-A": bv-av, "A*B": av*bv, "-A*B": -av*bv,
                    "A": av, "B": bv, "A&B~and": av if av==bv else 0.0, "0": 0.0}
            best = min(cand.items(), key=lambda kv: abs(kv[1]-val))
            wrote = 0x240 in {w for w in words}
            print(f"  op{op} A={A} B={B} byte {v:02x}: 0x240={word(snap,P2):08x} ({val:+.5f})"
                  f"  ~ {best[0]}={best[1]:+.5f} (err {abs(best[1]-val):.1e}){'' if wrote else '  [no store]'}")


def cmd_pred(rig, mask, a):
    print("PREDICATES  d9/da around `a4 30` (op0 A=1 B=2 -> D 0x144/0x148)")
    for pre in (0xD8, 0xD9, 0xDA, 0xDB):
        words, _ = measure(rig, mask, [pre, 0xA4, 0x30, 0xD8], a.trials)
        hits = [hex(w) for w in words if 0x140 <= w < 0x150]
        print(f"  {pre:02x} a4 30 d8 : P2-page writes {hits}   all: {[hex(w) for w in words][:8]}")


def cmd_back(rig, mask, a):
    print("BACKWARD BRANCH  f4 imm, imm 0x80..0xff, three emits after; FIFO bytes per single step")
    base = []
    for _ in range(3):
        _, _, f = rig.safe([0x28, 0x30, 0x38]); base.append(f)
    print(f"  baseline (28 30 38, no branch): fifo bytes {base}")
    for imm in range(0x80, 0x100, a.stride):
        s, fired, f = rig.safe([0xF4, imm, 0x28, 0x30, 0x38])
        tag = "CRASH" if s is None else f"fifo={f} int={fired}"
        flag = "  <-- longer than baseline" if s is not None and f > max(base) else ""
        print(f"  f4 {imm:02x}: {tag}{flag}")
        if s is None:
            rig.reinit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("cmd", choices=["store", "optable", "pred", "back"])
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--mask-n", type=int, default=12)
    ap.add_argument("--stride", type=int, default=4)
    a = ap.parse_args()
    rig = Rig(a.port)
    mask = build_mask(rig, a.mask_n)
    {"store": cmd_store, "optable": cmd_optable, "pred": cmd_pred, "back": cmd_back}[a.cmd](rig, mask, a)


if __name__ == "__main__":
    main()
