import datetime,json,shutil
from pathlib import Path
from analyze_fx_node_time import check,identity,read
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'out/FX_RANDOM_MODIFIERS_20261021';PROJECT=ROOT.parent/'t3b_unreal'
def main():
    proof=read(OUT/'vfpu_modifier_bridge_v2/verification.json');check(proof['passed']and not proof['game_node_seed_captured'],'Unexpected game seed claim')
    files=[ROOT/'tools/verify_vfpu_modifier_bridge.py',ROOT/'tools/finalize_vfpu_bridge.py',PROJECT/'Tools/ge_effect_rcx_modifier_probe.cpp',PROJECT/'Source/T3BRemake/Public/T3BGEEffectModifiers.h',PROJECT/'Source/T3BRemake/Private/T3BGEEffectModifiers.cpp',PROJECT/'Source/T3BRemake/Public/T3BGEVfpuRandom.h',PROJECT/'Source/T3BRemake/Private/T3BGEVfpuRandom.cpp'];snap=OUT/'vfpu_modifier_bridge_v2/current_tool_snapshots';snap.mkdir();rows=[]
    for f in files:d=snap/f.name;shutil.copyfile(f,d);rows.append(dict(source=str(f.resolve()),**identity(d)))
    result=dict(passed=True,proof=identity(OUT/'vfpu_modifier_bridge_v2/verification.json'),snapshots=rows,optional_rcx_type23_path=True,game_node_seed_captured=False,goal_status='active',formal_UE_built=False,default_M1_changed=False)
    (OUT/'vfpu_modifier_bridge_v2/checkpoint.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(dict(passed=True,snapshots=len(rows),game_node_seed_captured=False)))
if __name__=='__main__':main()
