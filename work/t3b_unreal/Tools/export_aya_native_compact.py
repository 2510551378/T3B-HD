"""Create an isolated glTF candidate with per-primitive referenced attribute slices.
Source glTF/bin are immutable. Accessor indices for skin/animation are retained.
"""
import argparse,copy,hashlib,json,struct,shutil
from pathlib import Path

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check(v,msg):
    if not v:raise ValueError(msg)
DT={5121:('B',1),5123:('H',2),5125:('I',4),5126:('f',4)};WIDTH={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}
def main():
    a=argparse.ArgumentParser();a.add_argument('--output-dir',type=Path,required=True);a=a.parse_args()
    root=Path(__file__).resolve().parents[2];source=root/'psp_parse/out/AYA_NATIVE_GLTF_20261020/aya_native.gltf'
    check(sha(source)=='93c78d4014a2255b15915f8150868d1654718b256a72995f25966581a578a4f7','Frozen source glTF changed')
    original=json.loads(source.read_text(encoding='utf-8'));oldbin=source.parent/original['buffers'][0]['uri'];check(sha(oldbin)=='8ce1805dcaf6cdb8f73c0d2d2784a8d20f0e611fbb2d144d0a2d025d839d8454','Frozen source bin changed')
    raw=oldbin.read_bytes();g=copy.deepcopy(original);g['bufferViews']=[];g['accessors']=[None]*len(original['accessors']);newbin=bytearray();mapping=[]
    def unpack_access(index):
        ac=original['accessors'][index];v=original['bufferViews'][ac['bufferView']];fmt,size=DT[ac['componentType']];width=WIDTH[ac['type']];stride=v.get('byteStride',size*width);start=v.get('byteOffset',0)+ac.get('byteOffset',0)
        return [raw[start+i*stride:start+i*stride+width*size]for i in range(ac['count'])]
    def write_accessor(index,old_index,rows,recompute_bounds=False):
        ac=copy.deepcopy(original['accessors'][old_index]);view=original['bufferViews'][ac['bufferView']]
        while len(newbin)%4:newbin.append(0)
        start=len(newbin);data=b''.join(rows);newbin.extend(data);nv={'buffer':0,'byteOffset':start,'byteLength':len(data)}
        if 'target'in view:nv['target']=view['target']
        ac['bufferView']=len(g['bufferViews']);g['bufferViews'].append(nv);ac['byteOffset']=0;ac['count']=len(rows)
        if recompute_bounds:
            fmt,_=DT[ac['componentType']];width=WIDTH[ac['type']];values=[struct.unpack('<'+fmt*width,row)for row in rows]
            if 'min'in ac:ac['min']=[min(v[i]for v in values)for i in range(width)]
            if 'max'in ac:ac['max']=[max(v[i]for v in values)for i in range(width)]
        if index is None:index=len(g['accessors']);g['accessors'].append(ac)
        else:g['accessors'][index]=ac
        return index
    attrs=original['meshes'][0]['primitives'][0]['attributes'];geometry=set(attrs.values());indices={p['indices']for p in original['meshes'][0]['primitives']}
    for i in range(len(original['accessors'])):
        if i not in geometry|indices:write_accessor(i,i,unpack_access(i))
    for pi,(old,p)in enumerate(zip(original['meshes'][0]['primitives'],g['meshes'][0]['primitives'])):
        ic=original['accessors'][old['indices']];fmt,size=DT[ic['componentType']];src=[struct.unpack('<'+fmt,row)[0]for row in unpack_access(old['indices'])]
        used=list(dict.fromkeys(src));lookup={v:i for i,v in enumerate(used)}
        for semantic,ai in old['attributes'].items():
            rows=unpack_access(ai);p['attributes'][semantic]=write_accessor(ai if pi==0 else None,ai,[rows[v]for v in used],True)
        local=[lookup[v]for v in src];write_accessor(old['indices'],old['indices'],[struct.pack('<'+fmt,v)for v in local],True)
        p['extras']['compact_source_vertices']=used;p['extras']['compact_policy']='per-primitive original attribute bytes, local indices; source draw/material/skin semantics unchanged'
        mapping.append({'primitive':pi,'source_draw':old['extras']['source_draw'],'source_indices':src,'local_indices':local,'original_vertices':used,'attribute_count':len(used)})
    check(all(x is not None for x in g['accessors']),'Unwritten accessor');g['buffers']=[{'uri':'aya_native.bin','byteLength':len(newbin)}]
    check(not a.output_dir.exists(),'Refuse existing output directory');a.output_dir.mkdir(parents=True)
    (a.output_dir/'aya_native.bin').write_bytes(newbin);(a.output_dir/'aya_native.gltf').write_text(json.dumps(g,indent=2)+'\n',encoding='utf-8')
    shutil.copyfile(source.parent/'provenance.json',a.output_dir/'provenance.json');shutil.copytree(source.parent/'textures',a.output_dir/'textures')
    report={'schema':'t3b-native-compact-candidate/v1','source_gltf':str(source),'source_gltf_sha256':sha(source),'source_bin_sha256':sha(oldbin),
        'gltf_sha256':sha(a.output_dir/'aya_native.gltf'),'bin_sha256':sha(a.output_dir/'aya_native.bin'),'primitives':106,'referenced_attribute_vertices':sum(m['attribute_count']for m in mapping),
        'original_UE_source_description_expected_vertices':106*3456,'compact_UE_source_description_expected_vertices':sum(m['attribute_count']for m in mapping),
        'original_bin_bytes':len(raw),'compact_bin_bytes':len(newbin),'source_mapping':mapping,'nodes_skins_animations_materials_unchanged':all(g[k]==original[k]for k in ['nodes','skins','animations','materials','images','samplers','textures']),
        'limits':['Actual UE import and numeric tests are separate; this exporter alone does not establish importer result.']}
    (a.output_dir/'compact_manifest.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:v for k,v in report.items()if k not in ['source_mapping','limits']},indent=2))
if __name__=='__main__':main()