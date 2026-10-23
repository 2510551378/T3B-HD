import datetime,json,shutil
from pathlib import Path
from analyze_fx_node_time import check,identity,read
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'out/FX_MATRIX_CONSUMER_MAP_20261021'
PROJECT=ROOT.parent/'t3b_unreal'

def main():
    p=read(OUT/'verification.json');check(p['passed'] and p['realtime_probe']['rows']>0,'Matrix map proof missing')
    baseline=ROOT/'out/FX_VECTOR_CURVE_20261021/source_protection.json';old=read(baseline)
    protected=dict(checked_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),baseline=identity(baseline))
    for group in ('original_files','packages'):
        protected[group]=[]
        for row in old[group]:
            item=identity(Path(row['file']));item.update(expected_sha256=row['sha256'],unchanged=item['sha256']==row['sha256']);protected[group].append(item)
        check(all(x['unchanged'] for x in protected[group]),group)
    (OUT/'source_protection.json').write_text(json.dumps(protected,indent=2),encoding='utf-8')
    files=[ROOT/'tools/audit_fx_matrix_consumer_map.py',ROOT/'tools/finalize_fx_matrix_map.py',ROOT/'tools/trace_fx_property_callbacks.js',PROJECT/'Tools/run_scene_color_bridge.py',PROJECT/'Source/T3BRemake/Private/T3BGEScene.cpp']
    snap=OUT/'current_tool_snapshots';snap.mkdir();rows=[]
    for f in files:
        d=snap/f.name;shutil.copyfile(f,d);rows.append(dict(source=str(f.resolve()),**identity(d)))
    result=dict(passed=True,verification=identity(OUT/'verification.json'),source_protection=identity(OUT/'source_protection.json'),snapshots=rows,goal_status='active',
                previous_goal_turn='progress: type6 vector continuous chain verified',current_goal_turn='progress: type6/type23 shared target separated from proven P+60 matrix input; direct join deliberately unproven',
                formal_UE_built=False,default_M1_changed=False,original_files_unchanged=3,existing_UE_packages_unchanged=185)
    (OUT/'checkpoint.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(dict(passed=True,snapshots=len(rows),original_files_unchanged=3,existing_UE_packages_unchanged=185)))

if __name__=='__main__':main()
