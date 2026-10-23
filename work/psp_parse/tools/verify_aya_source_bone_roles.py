#!/usr/bin/env python3
"""Negative/consistency verifier for Aya source-bone role audit."""
from __future__ import annotations
import argparse,json
from pathlib import Path

def main():
 ap=argparse.ArgumentParser(); ap.add_argument("audit",type=Path); ap.add_argument("metadata",type=Path); ap.add_argument("mapping",type=Path); ap.add_argument("out",type=Path); a=ap.parse_args()
 d=json.loads(a.audit.read_text(encoding="utf-8")); m=json.loads(a.metadata.read_text(encoding="utf-8")); g=json.loads(a.mapping.read_text(encoding="utf-8"))
 rows=d.get("rows",[]); assert d.get("source_bone_count")==44 and len(rows)==44
 by={int(x["index"]):x for x in rows}; assert sorted(by)==list(range(44))
 assert d.get("semantic_names_inferred") is False
 for i,x in by.items():
  for c in x["children"]: assert by[c]["parent"]==i
  if x["parent"]!=-1: assert i in by[x["parent"]]["children"]
 covered={int(x["source_index"]) for x in g.get("mappings",[]) if x.get("source_index") is not None}
 mapped={i for i,x in by.items() if x["ge_mapped"]}; assert mapped==covered
 assert {x["role"] for x in rows}=={"directly_weighted","nonweighted_ancestor_of_weighted","other_nonweighted"}
 result={"schema":"t3b-aya-source-bone-role-verification/v1","status":"passed","rows":44,"mapped_indices":sorted(mapped),"unmapped_indices":sorted(set(range(44))-mapped),"checks":["44 indices unique","parent/child links symmetric","semantic names disabled","GE mapping set agrees with audit","role partition complete"],"scope":"hierarchy and mapping consistency only; no anatomy or gameplay semantics inferred"}
 a.out.parent.mkdir(parents=True,exist_ok=True); a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__": main()
