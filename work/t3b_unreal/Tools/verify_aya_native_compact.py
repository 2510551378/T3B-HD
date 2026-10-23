"""Independent byte/topology/semantic verification of isolated compact glTF."""
import argparse,hashlib,json,struct
from pathlib import Path

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def must(v,msg):
    if not v:raise ValueError(msg)
def load(p):
    g=json.loads(p.read_text(encoding='utf-8'));b=(p.parent/g['buffers'][0]['uri']).read_bytes()
    def data(i):
        a=g['accessors'][i];v=g['bufferViews'][a['bufferView']];size={5121:1,5123:2,5125:4,5126:4}[a['componentType']];width={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}[a['type']];start=v.get('byteOffset',0)+a.get('byteOffset',0);stride=v.get('byteStride',size*width)
        return [b[start+j*stride:start+j*stride+size*width]for j in range(a['count'])]
    def indices(i):return [struct.unpack('<'+{5121:'B',5123:'H',5125:'I'}[g['accessors'][i]['componentType']],r)[0]for r in data(i)]
    return g,data,indices

def main():
    a=argparse.ArgumentParser();a.add_argument('--candidate',required=True,type=Path);a.add_argument('--output',required=True,type=Path);a=a.parse_args();must(not a.output.exists(),'Refuse overwrite')
    original=Path(__file__).resolve().parents[2]/'psp_parse/out/AYA_NATIVE_GLTF_20261020/aya_native.gltf'
    old,od,oi=load(original);new,nd,ni=load(a.candidate);checks=0;vertices=0;refs=set()
    for key in ['asset','extensionsUsed','scene','scenes','nodes','skins','animations','materials','images','samplers','textures']:must(old[key]==new[key],'Semantic change: '+key);checks+=1
    geometry=set(old['meshes'][0]['primitives'][0]['attributes'].values());idxs={p['indices']for p in old['meshes'][0]['primitives']}
    for i in range(len(old['accessors'])):
        if i not in geometry|idxs:must(od(i)==nd(i),'Skin/animation accessor bytes changed');checks+=1
    for pi,(p,q)in enumerate(zip(old['meshes'][0]['primitives'],new['meshes'][0]['primitives'])):
        source=oi(p['indices']);local=ni(q['indices']);used=q['extras']['compact_source_vertices'];must([used[i]for i in local]==source,'Reconstructed source topology changed')
        must(q['mode']==p['mode']and q['material']==p['material'],'Primitive render semantics changed')
        must(set(p['attributes'])==set(q['attributes']),'Attribute semantics changed');refs.update(q['attributes'].values());refs.add(q['indices']);vertices+=len(used)
        for semantic,i in p['attributes'].items():
            j=q['attributes'][semantic];a0=old['accessors'][i];a1=new['accessors'][j]
            must(all(a0.get(k)==a1.get(k)for k in ['componentType','type','normalized']),'Attribute component semantics changed')
            must(nd(j)==[od(i)[v]for v in used],'Vertex attribute raw bytes changed');must(len(nd(j))==len(set(local)),'Unreferenced compact primitive attribute');checks+=1
        must(all(q['extras'][k]==v for k,v in p['extras'].items()),'Source provenance changed');checks+=3
    for image in old['images']:must(digest(original.parent/image['uri'])==digest(a.candidate.parent/image['uri']),'Texture image changed');checks+=1
    must(vertices==3456 and len(new['meshes'][0]['primitives'])==106,'Compact dimensions wrong')
    result={'schema':'t3b-compact-independent-byte-verification/v1','passed':True,'checks':checks,'primitives':106,'sum_attribute_vertices':vertices,'all_original_attribute_rows_bit_exact':True,'topology_skin_animation_material_semantics_unchanged':True,'source_gltf_sha256':digest(original),'candidate_gltf_sha256':digest(a.candidate),'candidate_bin_sha256':digest(a.candidate.parent/'aya_native.bin'),'actual_UE_import_verified':False}
    a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,indent=2))
if __name__=='__main__':main()