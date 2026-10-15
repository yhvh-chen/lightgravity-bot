#!/usr/bin/env python3
"""Independent offline recomputation of Z2 p2 OCR CER / structure.

Reads the IMMUTABLE R3 evidence (ocr_post1.json text) + TRUTH-PREP human truth.
No network, no image edit, no model. Tests scoring-method validity:
  A. whole-page CER (protocol §1)
  B. R3's 'segment CER by best single-line overlap' (reproduces 0.3281?)
  C. corrected per-human-row CER allowing machine merged lines (layout-agnostic
     alignment: best window of concatenated machine lines, OR best line if any)
  D. structural criterion per protocol §4 (explicit counts) vs R3 invented rule
"""
import json, os, unicodedata, re
from itertools import islice

R3 = "/home/yhvh/code/lightgravity-bot-worktrees/materials-quality-20261016-r3/probes/materials-quality-20261016-r3"
TRUTH = "/home/yhvh/code/lightgravity-bot-worktrees/lg035-truth-prep/probes/lg035/TRUTH-PREP/truth/LG035-ZH-Z2.p2.txt"

def nfkc(s): return "".join(ch for ch in unicodedata.normalize("NFKC", s) if not ch.isspace())
def ed(a,b):
    if a==b: return 0
    prev=list(range(len(b)+1))
    for i,ca in enumerate(a,1):
        cur=[i]
        for j,cb in enumerate(b,1):
            cur.append(min(prev[j]+1,cur[j-1]+1,prev[j-1]+(ca!=cb)))
        prev=cur
    return prev[-1]
def cer(t,h):
    t,h=nfkc(t),nfkc(h)
    return ed(t,h)/max(1,len(t))

truth=open(TRUTH).read()
ocr=json.load(open(os.path.join(R3,"evidence","ocr_post1.json")))
hyp=ocr["text"]
hl=[l for l in hyp.splitlines() if l.strip()]
human=[l.lstrip("*") for l in truth.splitlines() if l.strip().startswith("*")]

out={}
out["whole_page_cer"]=round(cer(truth,hyp),4)
out["truth_chars"]=len(nfkc(truth)); out["hyp_chars"]=len(nfkc(hyp))

# B: R3 method
from collections import Counter
def overlap(a,b): return sum((Counter(a)&Counter(b)).values())
d=t=0
for hr in human:
    hn=nfkc(hr); best=max(hl,key=lambda l:overlap(hn,nfkc(l)))
    d+=ed(hn,nfkc(best)); t+=len(hn)
out["B_r3_method_seg_cer"]=round(d/t,4)

# C: layout-agnostic corrected: for each human row, allow matching a machine
# WINDOW of 1..2 consecutive lines; pick min CER. This mirrors the fact the
# product emits one line per visual row but sections may span.
d2=t2=0; per=[]
for hr in human:
    hn=nfkc(hr); bestc=9.9; bestw=None
    for i in range(len(hl)):
        for w in (1,2):
            cand="".join(nfkc(x) for x in hl[i:i+w])
            c=ed(hn,cand)/max(1,len(hn))
            if c<bestc: bestc=c; bestw=hl[i:i+w]
    per.append({"human":hr,"machine":bestw,"cer":round(bestc,4)})
    d2+=bestc*max(1,len(hn)); t2+=max(1,len(hn))
out["C_layout_agnostic_seg_cer"]=round(d2/t2,4)
out["C_per_row"]=per

# D: protocol §4 explicit structure counts
out["D_human_rows_star_lines"]=len(human)
markers=("國","蘇","廣","北風","世界","船","狗","末","格","的")
out["D_machine_lines"]=len(hl)
out["D_machine_lines_with_2_sections"]=sum(
  1 for l in hl if sum(1 for m in ("北風說","世界浪","世界上的","船碰","狗阿","末貓","國、","蘇、","廣、") if m in l)>=2)
out["D_machine_upper_marker_lines"]=sum(1 for l in hl if any(m in l for m in ("國、","蘇、","廣、")))
out["D_field_tokens_truth"]=re.findall(r"\d[\d,]*",nfkc(truth))
out["D_field_tokens_hyp"]=re.findall(r"\d[\d,]*",nfkc(hyp))

# Does machine preserve a 15-row x 3-col structure? Count dialect rows emitted:
out["D_machine_dialect_rows_approx"]=(
  out["D_machine_upper_marker_lines"] +           # first section 3 dialects
  sum(1 for l in hl if "北風說" in l or "北風話" in l) +
  sum(1 for l in hl if "世界" in l) +
  sum(1 for l in hl if "船碰" in l) +
  sum(1 for l in hl if "狗阿" in l))
print(json.dumps(out,ensure_ascii=False,indent=2))
open("/home/yhvh/code/lightgravity-bot-worktrees/materials-r3-audit-20261016/probes/materials-r3-audit-20261016/recompute_cer.json","w").write(json.dumps(out,ensure_ascii=False,indent=2))
