#!/usr/bin/env python3
"""Verify CLUT match report covers every saved frame-capture root."""
from __future__ import annotations
import argparse,json
from pathlib import Path

def roots_under(base: Path): return sorted({str(p.parent.resolve()) for p in base.rglob("frame_*.ppdmp")})
def roots_in_report(report): return sorted({str(Path(x["sample"]).parent.resolve()) for x in report.get("runtime",[])})
def main():
 ap=argparse.ArgumentParser(); ap.add_argument("base",type=Path); ap.add_argument("report",type=Path); ap.add_argument("old",type=Path); ap.add_argument("out",type=Path); a=ap.parse_args()
 r=json.loads(a.report.read_text(encoding="utf-8")); old=json.loads(a.old.read_text(encoding="utf-8")); expected=roots_under(a.base); observed=roots_in_report(r); missing=sorted(set(expected)-set(observed)); extra=sorted(set(observed)-set(expected))
 assert not extra
 assert r["runtime_payloads"]==206 and r["matched_runtime_payloads"]==84
 old_keys={(x["type"],x["sha1"],x["bytes"]) for x in old["runtime"]}; new_keys={(x["type"],x["sha1"],x["bytes"]) for x in r["runtime"]}
 result={"schema":"runtime-clut-capture-coverage-verification/v1","status":"passed","capture_roots":len(expected),"frame_files":sum(1 for _ in a.base.rglob("frame_*.ppdmp")),"runtime_payloads":r["runtime_payloads"],"matched_runtime_payloads":r["matched_runtime_payloads"],"unmatched_runtime_payloads":r["runtime_payloads"]-r["matched_runtime_payloads"],"old_report_signature_set_equal":old_keys==new_keys,"representative_sample_roots":len(observed),"roots_without_unique_payload_representative":len(missing),"missing_roots_due_to_signature_dedup":missing,"extra_roots":extra,"limits":["All saved frame_*.ppdmp roots were supplied to the rerun; runtime payloads are deduplicated by (type,SHA1,size), so a root can have no representative row.","A pack match identifies bytes, not FEP meaning, draw ownership, or material semantics.","No default M1 material was replaced."]}
 assert result["old_report_signature_set_equal"]
 a.out.parent.mkdir(parents=True,exist_ok=True); a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__": main()
