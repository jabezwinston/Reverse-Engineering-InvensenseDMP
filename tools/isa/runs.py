"""Quantify the same-destination run anomaly, and how much of it is aliasing.

For every run of consecutive ALU stores landing on the SAME destination word
(Finding 17's anomaly), ask whether the destination aliases one of the operands.
If it does, `x = x + a` repeated is a legitimate accumulation, not a dead write.
See ISA2.md Finding 17 and 22, and UNKNOWNS.md item 1.

    python3 tools/isa/runs.py        (run from the repo root)
"""
import sys, pathlib, collections
sys.path.insert(0, "tools/isa")
from decode import Decoder, Namer, lineage_of

def start_of(s): return 4096 if s>14000 else 1024 if s>2000 else 512 if s==1024 else 768
tot = collections.Counter(); runs = collections.Counter(); examples=[]
for p in sorted(pathlib.Path("corpus/images").glob("*.bin")):
    img=p.read_bytes(); n=len(img)
    if n>14000: continue
    s=start_of(n); L=lineage_of(img,s); d=Decoder(img,L,Namer({})); i=s
    seq=[]                      # (addr, dest, Asrc, Bsrc) for ALU stores in RAM mode
    while i<n:
        b=img[i]; before=(d.ptr(0),d.ptr(1))
        k,_=d.step(i)
        if b<0x80 and d.ram:
            A,B,op=(b>>5)&3,(b>>3)&3,b&7
            dest=d.ptr(2)
            asrc=before[0]+4*A; bsrc=before[1]+4*B
            seq.append((i,dest,asrc,bsrc,b))
        elif b>=0x80:
            pass
        i+=k
    # group consecutive-in-address ALU stores by identical destination
    j=0
    while j<len(seq):
        k2=j+1
        while k2<len(seq) and seq[k2][1]==seq[j][1] and seq[k2][0]==seq[k2-1][0]+1:
            k2+=1
        if k2-j>=2:
            grp=seq[j:k2]; runs[k2-j]+=1
            alias=sum(1 for g in grp if g[1]==g[2] or g[1]==g[3])
            tot["instrs"]+=len(grp)
            tot["alias"]+=alias
            if alias==len(grp): tot["all_alias_runs"]+=1
            elif alias==0: tot["no_alias_runs"]+=1
            else: tot["mixed_runs"]+=1
            if len(examples)<6 and alias==len(grp):
                examples.append((p.name,[hex(g[4]) for g in grp],grp[0][1]))
        j=k2
print("run-length histogram:", dict(sorted(runs.items())))
print("total runs:", sum(runs.values()), " instructions in runs:", tot["instrs"])
print("instructions whose destination aliases an operand:", tot["alias"],
      f"({100*tot['alias']/max(tot['instrs'],1):.1f}%)")
print("runs fully aliasing:", tot["all_alias_runs"],
      " runs never aliasing:", tot["no_alias_runs"], " mixed:", tot["mixed_runs"])
for e in examples: print("  e.g.", e)
