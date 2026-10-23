"""Measure grip and muzzle continuity against the recovered hand draw.

The PPSSPP dump has no explicit socket label, so the measurable reference is
the right-hand weighted draw bbox.  The report separates grip placement error
from frame-to-frame muzzle direction jitter.
"""
import json, math, csv
from pathlib import Path

def rot_y(p, pivot, a):
    s, c = math.sin(a), math.cos(a); x, z = p[0] - pivot[0], p[2] - pivot[2]
    return [pivot[0] + x*c + z*s, p[1], pivot[2] - z*c + x*s]

def rot_z(p, pivot, a):
    s, c = math.sin(a), math.cos(a); x, y = p[0] - pivot[0], p[1] - pivot[1]
    return [pivot[0] + x*c - y*s, pivot[1] + x*s + y*c, p[2]]

def norm(v):
    n = math.sqrt(sum(x*x for x in v)); return [x/n for x in v] if n > 1e-9 else [0, 0, 1]

def sub(a,b): return [a[i]-b[i] for i in range(3)]
def dot(a,b): return sum(a[i]*b[i] for i in range(3))

def mix_matrix(static, dynamic, alpha=.65):
    return [[(1-alpha)*static[r][c] + alpha*dynamic[r*4+c] for c in range(3)] for r in range(3)]

def apply_pose(p, m, pivot, blend=.35):
    q=sub(p,pivot); r=[sum(m[i][j]*q[j] for j in range(3)) for i in range(3)]
    return [pivot[i] + (1-blend)*q[i] + blend*r[i] for i in range(3)]

def main():
    root=Path(__file__).resolve().parents[1]
    timeline=json.loads((root/'out/aya_ge_hierarchy_timeline.json').read_text(encoding='utf8'))
    static=json.loads((root.parent/'t3b_hd/assets/models/aya_ge_matrices.json').read_text(encoding='utf8'))
    sm=static['bones']['bone4']['matrix']
    pivot=[.95,1.90,0.0]; grip=[.09,1.79,.13]; muzzle=[.30,1.795,.106]; muzzle2=[.30,1.795,.306]; correction=[.742355,.029960,-.252845]; weapon_yaw=math.radians(155.0)
    grip_ref=[]; rows=[]; prev=None
    for fr in timeline['frames']:
        ch=fr['channels']['arm_right_hand']; dyn=ch['matrix']; m=mix_matrix(sm,dyn)
        # weapon_calibrated_vertex: -90 degrees around the grip (grip itself is fixed).
        g=apply_pose(rot_y(grip,grip,weapon_yaw),m,pivot); g=[g[i]+correction[i] for i in range(3)]
        mz=apply_pose(rot_y(muzzle,grip,weapon_yaw),m,pivot); mz=[mz[i]+correction[i] for i in range(3)]
        mz2=apply_pose(rot_y(muzzle2,grip,weapon_yaw),m,pivot); mz2=[mz2[i]+correction[i] for i in range(3)]
        direction=norm(sub(mz2,mz)); ref=ch['bbox']; hand=[(ref[0][i]+ref[1][i])*.5 for i in range(3)]
        ge=math.sqrt(sum((g[i]-hand[i])**2 for i in range(3)))
        hand_axis=norm([m[0][2],m[1][2],m[2][2]])
        forward_angle=math.degrees(math.acos(max(-1,min(1,dot(direction,hand_axis)))))
        jitter=0.0 if prev is None else math.degrees(math.acos(max(-1,min(1,dot(direction,prev)))))
        rows.append({'frame':fr['frame'],'draw':ch['draw'],'grip_error':ge,'muzzle_forward_error_deg':forward_angle,'muzzle_jitter_deg':jitter,'direction':direction})
        prev=direction
    out=root/'out/AYA_SOCKET_ERROR.json'; out.write_text(json.dumps({'schema':'aya-socket-error/v1','reference':'right-hand weighted draw bbox','frames':rows},indent=2),encoding='utf8')
    md=root/'out/AYA_SOCKET_ERROR.md';
    mean=lambda k:sum(r[k] for r in rows)/len(rows)
    md.write_text('# Aya 武器挂点与枪口误差\n\n'+
      '参考：PPSSPP 逐帧恢复的 `arm_right_hand` weighted draw bbox；运行时使用右手通道、grip 和 muzzle 同一 posed transform。\n\n'+
      f'- 帧数：{len(rows)}\n- grip 到手部 draw 中心平均误差：{mean("grip_error"):.5f}，最大：{max(r["grip_error"] for r in rows):.5f}\n'+
      f'- 枪口相对右手 GE forward axis 平均方向误差：{mean("muzzle_forward_error_deg"):.3f}°，最大：{max(r["muzzle_forward_error_deg"] for r in rows):.3f}°\n'+
      f'- 连续帧枪口方向抖动平均：{mean("muzzle_jitter_deg"):.3f}°，最大：{max(r["muzzle_jitter_deg"] for r in rows):.3f}°\n\n'+
      '- 当前校准参数：weapon yaw correction=155°，mount correction=(+0.742355,+0.029960,-0.252845)。\n\n'+
      '误差是重制版 socket 对恢复 draw 参考的工程测量，不等同于原游戏内部骨骼名称或未公开 socket 元数据。\n',encoding='utf8')
    print(md.read_text(encoding='utf8'))

if __name__=='__main__': main()
