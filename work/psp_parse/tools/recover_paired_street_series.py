"""Export each observed street instance set without invented object trajectories."""
import argparse,hashlib,json
from pathlib import Path
from recover_paired_street_snapshot import recover


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True,type=Path);a=p.parse_args()
    if a.out.exists():raise ValueError('Never overwrite scene series')
    a.out.mkdir(parents=True);frames=[]
    for i in range(12):
        folder=a.out/f'sample_{i:02d}';result=recover(folder,i);manifest=folder/'snapshot.json'
        frames.append(dict(sample=i,snapshot=dict(file=str(manifest.resolve()),sha256=sha(manifest)),
            draws=result['draw_count'],vertices=result['vertices'],textures=result['texture_count'],
            changed_reference_WORLD=sum(not d['WORLD_matches_old_reference']for d in result['draws']),original_time_seconds=None))
    result=dict(schema='t3b-paired-original-street-series/v1',passed=True,frames=frames,
        temporal_object_identity_verified=False,original_timing_verified=False,interpolation_allowed=False,
        subset_scope='Observed instances of the previously verified street resource bank; unmatched draws remain excluded.',
        producer_sha256=sha(Path(__file__)),snapshot_producer_sha256=sha(Path(__file__).with_name('recover_paired_street_snapshot.py')))
    (a.out/'series.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=True,frames=12,draws=sum(f['draws']for f in frames),vertices=sum(f['vertices']for f in frames),
        per_sample_draws=[f['draws']for f in frames],per_sample_changed_WORLD=[f['changed_reference_WORLD']for f in frames])))


if __name__=='__main__':main()
