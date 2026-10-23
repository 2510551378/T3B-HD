import datetime,json,shutil
from pathlib import Path
from analyze_fx_node_time import check,identity,read
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'out/FX_RANDOM_MODIFIERS_20261021';PROJECT=ROOT.parent/'t3b_unreal'
def main():
    proof=read(OUT/'vfpu_runtime_v5/verification.json');check(proof['passed']and not proof['game_node_seed_captured'],'Unexpected seed claim')
    base=read(OUT/'source_protection.json');write=OUT/'vfpu_runtime_v5/source_protection.json';protected=dict(checked_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),baseline=identity(OUT/'source_protection.json'))
    for group in('original_files','packages'):
        protected[group]=base[group];check(all(r['unchanged']for r in base[group]),group)
    write.write_text(json.dumps(protected,indent=2),encoding='utf-8')
    files=[ROOT/'tools/verify_vfpu_random_runtime.py',ROOT/'tools/finalize_vfpu_random.py',PROJECT/'Source/T3BRemake/Public/T3BGEVfpuRandom.h',PROJECT/'Source/T3BRemake/Private/T3BGEVfpuRandom.cpp',PROJECT/'Tools/ge_vfpu_random_probe.cpp']
    snap=OUT/'vfpu_runtime_v5/current_tool_snapshots';snap.mkdir();rows=[]
    for f in files:d=snap/f.name;shutil.copyfile(f,d);rows.append(dict(source=str(f.resolve()),**identity(d)))
    result=dict(passed=True,proof=identity(OUT/'vfpu_runtime_v5/verification.json'),source_protection=identity(write),snapshots=rows,algorithm_recovered=True,game_node_seed_captured=False,goal_status='active',formal_UE_built=False,default_M1_changed=False)
    (OUT/'vfpu_runtime_v5/checkpoint.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(dict(passed=True,snapshots=len(rows),game_node_seed_captured=False)))
if __name__=='__main__':main()
