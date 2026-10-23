#!/usr/bin/env python3
"""Classify Aya source indices by weighted usage and hierarchy, without naming anatomy."""
from __future__ import annotations
import argparse,json
from pathlib import Path

def read(p): return json.loads(Path(p).read_text(encoding="utf-8"))

def main():
 ap=argparse.ArgumentParser(); ap.add_argument("metadata",type=Path); ap.add_argument("mapping",type=Path); ap.add_argument("out_json",type=Path); ap.add_argument("out_md",type=Path); a=ap.parse_args()
 meta=read(a.metadata); mapping=read(a.mapping)
 bones={int(b["index"]):b for b in meta["bones"]}
 mapped={}
 for row in mapping.get("mappings",[]):
  idx=row.get("source_index")
  if idx is not None: mapped.setdefault(int(idx),[]).append(row)
 weighted=set(meta["summary"].get("active_source_indices",[]))
 ancestor=set(meta["summary"].get("nonweighted_ancestors_of_weighted_bones",[]))
 other=set(meta["summary"].get("other_nonweighted_indices",[]))
 def desc(i):
  seen=set(); stack=list(bones[i].get("children",[]))
  while stack:
   j=stack.pop()
   if j in seen: continue
   seen.add(j); stack.extend(bones[j].get("children",[]))
  return seen
 rows=[]
 for i in range(meta["summary"]["bone_count"]):
  b=bones[i]; d=desc(i); wd=sorted(d & weighted)
  if i in weighted: role="directly_weighted"
  elif i in ancestor: role="nonweighted_ancestor_of_weighted"
  elif i in other: role="other_nonweighted"
  else: role="unclassified"
  rows.append({"index":i,"parent":b.get("parent"),"children":b.get("children",[]),"role":role,"root":b.get("parent")==-1,"descendant_count":len(d),"weighted_descendants":wd,"ge_mapping_count":len(mapped.get(i,[])),"ge_mapped":bool(mapped.get(i))})
 result={"schema":"t3b-aya-source-bone-role-audit/v1","status":"passed_with_limits","source_bone_count":44,"semantic_names_inferred":False,"rows":rows,"role_counts":{r:sum(x["role"]==r for x in rows) for r in sorted({x["role"] for x in rows})},"limits":["Role is derived from source draw/palette metadata and parent hierarchy; it does not name anatomy.","Nonweighted indices have no direct GE draw mapping in the current same-frame captures.","Other_nonweighted does not prove dormant, hidden, or unused gameplay state."]}
 a.out_json.parent.mkdir(parents=True,exist_ok=True); a.out_json.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 lines=["# Aya source-bone role audit", "", "- 44 source records classified from the frozen skeleton metadata and same-frame GE mapping.", "- Anatomy names are intentionally not inferred.", "", "| index | parent | role | children | weighted descendants | GE mappings |", "|---:|---:|---|---|---|---:|"]
 for x in rows: lines.append(f"| {x['index']} | {x['parent']} | {x['role']} | {','.join(map(str,x['children'])) or '-'} | {','.join(map(str,x['weighted_descendants'])) or '-'} | {x['ge_mapping_count']} |")
 a.out_md.parent.mkdir(parents=True,exist_ok=True); a.out_md.write_text("\n".join(lines)+"\n",encoding="utf-8")
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__": main()
