"""Independently audit retained selector stores and unwind their raw stacks.

No emulator connection. Older captures lack raw actor pointer dereferences;
new captures are checked through their retained identity/provenance windows.
"""
import argparse
import collections
import json
import struct
from pathlib import Path

from analyze_weapon_marker_output import BASE, GEOMETRY_SHA, MODULE_SHA, check, sha, sidecar
from analyze_weapon_marker_state_output import code_blocks

ENTRY, POST = 0x08B6513C, 0x08B65214
RECURSIVE_RA, ROOT_RA = 0x08B651AC, 0x08B5B9F4
RESOURCE_SHA = '04afeecb38df20d41a7c24da1686e31cf70a8e631aa51e48321c776ab21d89b6'
PRODUCER_SHAS = {'295300d081d950c6dca5342e871a35b2623ce08cf0ae7cf91fe1b8dc85b8ed86',
                 'ff8eaa7fbf3738266a83987986a49083df5c199ece9febb33f6d44709c7723bc',
                 '8383019e838baf4fa6eb1b31ff6bc4518382bf1257d1e4e1c045ed956a1f1bf8'}
REQUIRED = {(ENTRY, 0x118), (0x08B646B4, 0x11C), (0x08B5B990, 0xAC),
            (0x08B59A98, 0x5C), (0x08B26C6C, 0xE0), (0x08BBBFAC, 0x108),
            (0x08B3F140, 0x1C), (0x08B447CC, 0x3C), (0x08B65338, 8)}


def fields(data):
    u32 = lambda at: struct.unpack_from('<I', data, at)[0]
    return {'sourceState190': u32(0x190), 'sourceState194': u32(0x194),
            'sourceState198': u32(0x198), 'primary': u32(0x144),
            'selectorSigned': struct.unpack_from('<h', data, 0x14C)[0],
            'selectorU16': struct.unpack_from('<H', data, 0x14C)[0],
            'selectorWord14c': u32(0x14C), 'flags154': u32(0x154)}


def jal(module, pc, target):
    word = struct.unpack_from('<I', module, pc-BASE)[0]
    check(word >> 26 == 3, f'{pc:08x} is not JAL')
    check(((pc+4) & 0xF0000000) | ((word & 0x3FFFFFF) << 2) == target,
          f'{pc:08x} JAL target differs')


def raw_identity(row):
    weapon = row['weapon']
    raw = weapon.get('identityRaw')
    if raw is None:
        return False
    def window(name, address, size):
        item = raw[name]
        data = sidecar(item['raw'])
        check(item['address'] == address and len(data) == size, 'raw identity address/size differs')
        return data
    primary = window('primary', row['primary'], 4)
    actor = struct.unpack('<I', primary)[0]
    check(actor == weapon['actor'], 'raw primary handle does not resolve to reported actor')
    actor_fields = window('actorFields', actor+0x3C4, 40)
    check(struct.unpack_from('<I', actor_fields)[0] == weapon['sourceBase'] and
          struct.unpack_from('<I', actor_fields, 0x24)[0] == weapon['metadata'], 'raw actor pointers differ')
    metadata = window('metadata', weapon['metadata'], 64)
    draw = window('draw', weapon['drawTable'], 16)
    check(list(struct.unpack('<16I',metadata)) == weapon['metadataHeader'] and
          list(struct.unpack('<4I',draw)) == weapon['drawHeader'], 'raw metadata/draw words differ')
    return True


def binding_source(row, stack, module, verified_ranges):
    source = row.get('bindingProvenance')
    if source is None:
        return None
    check(source['schema'] == 'weapon-binding-source-provenance/v1' and source['status'] == 'read' and
          source['semanticName'] is None, 'binding source schema/status differs')
    check({(0x08976F1C,0xE90),(0x08B38DD0,0x58)} <= verified_ranges, 'full binding source code missing')
    for pc, target in ((0x08977CC0,0x08971EDC),(0x08977044,0x08B38DD0)):
        jal(module,pc,target)
    for pc, word in ((0x0897704C,0x8E670090),(0x08977058,0xAFA70378),(0x08977CBC,0x8FA80378)):
        check(struct.unpack_from('<I',module,pc-BASE)[0] == word, 'selector source opcode differs')
    s = row['entrySP']
    at = lambda address: struct.unpack_from('<I',stack,address-s)[0]
    r = row['callerChain']['rootSelectorEntrySP']
    g,q,u = r+0x30,r+0x50,r+0x70
    check(source['rootSelectorEntrySP'] == r and source['gameWrapperLocalSP'] == g and
          source['gameFunctionLocalSP'] == q and source['upperLocalSP'] == u, 'source frame addresses differ')
    check(row['callerChain']['gameCallsite'] == 0x08971FE0 and at(q+0x1C) == 0x08977CC8,
          'source upper caller differs')
    context,primary,selector,container,config,actor = (at(g),at(g+4),at(g+8),at(g+0x14),at(q+0xC),at(q+0x10))
    for name,value in [('context',context),('primary',primary),('selector',selector),
                       ('slotContainer',container),('config',config),('actor',actor)]:
        check(source[name] == value, f'source raw stack {name} differs')
    check(primary == row['primary'] and selector == row['newSelector'], 'source args not preserved')
    def window(name,address,size):
        item = source['windows'][name]
        data = sidecar(item['raw'])
        check(item['address'] == address and item['size'] == size == len(data), 'binding source window differs')
        check(0x08000000 <= address and address+size <= 0x0C000000, 'binding source outside guest RAM')
        return data
    locals_raw = window('upper_locals',u+0x370,0x10)
    cfg = window('config_8c',config+0x8C,0x10)
    actor80 = window('actor_80',actor+0x80,8)
    window('actor_148c',actor+0x148C,4)
    window('actor_1538',actor+0x1538,4)
    mode = window('actor_161c',actor+0x161C,4)
    slots = window('slot_container',container,8)
    slot_offset = row['entryGPR'][22]
    slots_base,count = struct.unpack('<2I',slots)
    check(slot_offset%4 == 0 and slot_offset//4 < count <= 4096, 'raw slot bounds differ')
    check(source['slotByteOffset'] == slot_offset and source['slotIndex'] == slot_offset//4, 'raw slot index differs')
    slot = window('selected_slot',slots_base+slot_offset,4)
    array_base,array_count = struct.unpack('<2I',actor80)
    index = int(mode[2] != 0)
    check(index == source['primaryIndex'] and index < array_count <= 4096, 'raw primary index differs')
    record = window('primary_record',array_base+24*index,24)
    read32 = lambda data,offset=0: struct.unpack_from('<I',data,offset)[0]
    check(read32(cfg,4) == read32(locals_raw,8) == selector, 'config90 -> upper378 -> selector differs')
    check(read32(record) == read32(locals_raw,12) == primary, 'actor array -> upper37c -> primary differs')
    check(source['requestedID'] == {'config94':read32(cfg,8),'upper374':read32(locals_raw,4)},
          'requested ID interpretation differs')
    return {'config':hex(config),'selector_field_address':hex(config+0x90),'source_selector':selector,
            'upper_saved_selector':read32(locals_raw,8),'primary_source_actor':hex(actor),
            'primary_index':index,'primary_record_address':hex(array_base+24*index),
            'slot_index':slot_offset//4,'cached_state_key':hex(read32(slot)),
            'requested_id':source['requestedID'],'semanticName':None}


def audit(path, producer_path=None):
    raw = path.read_bytes()
    capture = json.loads(raw)
    check(capture['schema'] == 'weapon-marker-selector-writer-capture/v1', 'wrong schema')
    check(capture['failure'] is None and capture['inFlight'] is None, 'failed/incomplete capture')
    check(capture['entryPC'] == ENTRY and capture['postWritePC'] == POST, 'wrong writer ABI')
    check(capture['semanticName'] is None and capture['ownedBP'] is None, 'semantic/BP contract differs')
    check(capture['expectedGeometrySHA256'] == GEOMETRY_SHA and
          capture['expectedResourcePrefix64SHA256'] == RESOURCE_SHA, 'wrong selected identities')
    cleanup = capture['cleanup']
    check(not cleanup['errors'] and cleanup['buttonsReleased'] and cleanup['ownedBreakpointRemoved'],
          'capture cleanup incomplete')
    module = Path(capture['module']['file']).read_bytes()
    check(sha(module) == capture['module']['sha256'] == MODULE_SHA, 'wrong original module')
    producer = Path(producer_path or capture['producer']['file']).read_bytes()
    check(sha(producer) == capture['producer']['sha256'] and sha(producer) in PRODUCER_SHAS, 'producer identity differs')
    map_bytes = Path(capture['map']['file']).read_bytes()
    check(sha(map_bytes) == capture['map']['sha256'], 'map identity differs')
    functions = set()
    for line in map_bytes.decode('utf-8-sig').splitlines():
        parts = line.split()
        if len(parts) >= 5:
            try:
                functions.add((BASE+int(parts[0], 16), int(parts[1], 16), parts[4]))
            except ValueError:
                pass
    names = code_blocks(capture, module, required_ranges=REQUIRED)
    verified_ranges = {(b['address'], b['size']) for b in capture['codeIdentity']['checks']}
    for pc, target in ((RECURSIVE_RA-8, ENTRY), (ROOT_RA-8, ENTRY),
                       (0x08B59AD0, 0x08B5B990), (0x08B26CFC, 0x08B59A98),
                       (0x08B65200, 0x08BBBFAC)):
        jal(module, pc, target)
    check(struct.unpack_from('<I', module, 0x08B65210-BASE)[0] == 0xA650014C,
          'actual nonzero-primary SH s0,state+14c differs')
    active = None
    for transition in capture['transitions']:
        operation, pc = transition['operation'], transition['address']
        if operation == 'add_requested':
            check(active is None and pc in (ENTRY, POST), 'simultaneous/foreign owned BP')
            active = pc
        elif operation == 'add_acknowledged':
            check(active == pc, 'BP acknowledgement differs')
        elif operation == 'remove':
            check(active == pc, 'removed unowned BP')
            active = None
        else:
            raise ValueError(f'unknown transition {operation}')
        check(transition['ownedActiveCount'] == int(active is not None), 'BP active count differs')
    check(active is None, 'owned BP remains')
    results, raw_links, sources = [], [], []
    noops = capture['noOpEntries']
    for row in [*capture['rows'], *noops]:
        g = row['entryGPR']
        check(len(g) == 32 and row['entryPC'] == ENTRY and row['semanticName'] is None, 'entry contract differs')
        p, s, ra = row['state'], row['entrySP'], row['entryRA']
        check(g[4] == row['context'] and g[5] == p and g[6] == row['newSelector'] and
              g[29] == s and g[31] == ra, 'entry args/SP/RA differ')
        check(row['entryArgs'] == {'a0':g[4], 'a1':g[5], 'a2':g[6]}, 'reported args differ')
        before = sidecar(row['stateBefore'])
        check(len(before) == 0x1A4 and before[0] == 0x65, 'wrong leaf snapshot')
        f = fields(before)
        check(f == row['beforeFields'] and f['primary'] == row['primary'] != 0, 'state fields differ')
        check(f['selectorSigned'] == row['oldSelectorSigned'] and f['selectorU16'] == row['oldSelectorU16'],
              'old selector differs')
        check(row['expectedStoredU16'] == (g[6] & 0xFFFF), 'store truncation differs')
        resource = sidecar(row['resourcePrefix'])
        check(len(resource) == 64 and sha(resource) == RESOURCE_SHA, 'selected resource differs')
        weapon = row['weapon']
        geometry = sidecar(weapon['geometry'])
        check(len(geometry) == 243*16 and sha(struct.pack('<I', 0x522)+geometry) ==
              weapon['geometrySHA256'] == GEOMETRY_SHA, 'retained gun geometry differs')
        # Metadata/draw words were JSON retained, without independently hashed
        # raw dereference windows. Check their internal consistency only.
        meta = struct.pack('<16I', *weapon['metadataHeader'])
        draw = struct.pack('<4I', *weapon['drawHeader'])
        check(struct.unpack_from('<h', meta, 6)[0] == 3 and
              struct.unpack_from('<I', meta, 0x34)[0] == weapon['drawTable'], 'metadata words differ')
        check(struct.unpack_from('<H', draw)[0] == 1 and struct.unpack_from('<H', draw, 4)[0] == 243 and
              draw[10]*2 == 16 and struct.unpack_from('<I', draw, 12)[0] == 0x522, 'draw words differ')
        stack = sidecar(row['entryStack'])
        check(len(stack) == 0x400, 'bounded entry stack missing')
        def at(address):
            offset = address-s
            check(0 <= offset <= len(stack)-4, 'stack unwind outside raw window')
            return struct.unpack_from('<I', stack, offset)[0]
        chain = row['callerChain']
        root_s, root_ra, recursion = s, ra, []
        while root_ra == RECURSIVE_RA:
            check(len(recursion) < capture['bounds']['maxGroupDepth'], 'recursive depth exceeds bound')
            saved = at(root_s+0x18)
            recursion.append({'depth':len(recursion), 'childEntrySP':root_s, 'childEntryRA':root_ra,
                              'parentLocalSP':root_s, 'savedRAAddress':root_s+0x18, 'savedRA':saved})
            root_s += 0x20
            root_ra = saved
        check(root_ra == ROOT_RA and chain['recursion'] == recursion and
              chain['recursionDepth'] == len(recursion), 'raw recursive unwind differs')
        check(chain['leafEntrySP'] == s and chain['leafEntryRA'] == ra and
              chain['rootSelectorEntrySP'] == root_s and chain['rootSelectorEntryRA'] == root_ra,
              'reported root/leaf differs')
        for label, offset, expected in [('bind',0x10,0x08B59AD8), ('global',0x20,0x08B26D04), ('game',0x48,None)]:
            actual = at(root_s+offset)
            check(chain['savedRA'][label] == {'address':root_s+offset, 'value':actual}, 'saved RA interpretation differs')
            check(expected is None or actual == expected, 'unexpected upper wrapper')
        game_ra = at(root_s+0x48)
        pc = game_ra-8
        check(chain['gameReturnPC'] == game_ra and chain['gameCallsite'] == pc, 'game callsite differs')
        jal(module, pc, 0x08B26C6C)
        function = chain['gameFunction']
        check((function['address'], function['size'], function['name']) in functions and
              function['address'] <= pc < function['address']+function['size'], 'game map boundary differs')
        check((function['address'], function['size']) in verified_ranges, 'actual game function code missing')
        raw_links.append(raw_identity(row))
        source = binding_source(row,stack,module,verified_ranges)
        sources.append(source)
        if capture['bounds'].get('bindingProbe'):
            check(raw_links[-1] and source is not None, 'requested raw binding provenance missing')
        is_noop = (f['selectorSigned'] & 0xFFFFFFFF) == g[6]
        if row['classification'] == 'no_op_entry':
            check(is_noop and row['actualWriteObserved'] is False and 'postWrite' not in row, 'incorrect no-op classification')
            continue
        check(not is_noop and row['classification'] == 'observed_selector_write' and row['actualWriteObserved'],
              'incorrect actual write classification')
        post = row['postWrite']
        pg = post['gpr']
        check(post['pc'] == POST and pg[29] == s-0x20 == row['expectedPostWriteSP'] and
              pg[31] == 0x08B65208 == row['expectedPostWriteRA'], 'post-write SP/validator RA differs')
        check(pg[16:19] == [g[6],g[4],g[5]] and all(pg[i] == g[i] for i in (19,20,21,22,23,30)),
              'post-write saved registers differ')
        local_stack = sidecar(post['postStack'])
        check(len(local_stack) == 0x20 and struct.unpack_from('<I',local_stack,0x18)[0] == ra,
              'post-write original saved RA differs')
        check(list(struct.unpack_from('<6I',local_stack)) == g[16:22], 'saved prologue register words differ')
        after = sidecar(post['stateAfter'])
        check(len(after) == len(before) and fields(after) == post['fields'], 'post-state fields differ')
        changed = [i for i,(a,b) in enumerate(zip(before,after)) if a != b]
        check(changed == row['changedByteOffsets'] and set(changed) <= {0x14C,0x14D}, 'unexpected changed bytes')
        check(fields(after)['selectorU16'] == (g[6] & 0xFFFF), 'actual selector store differs')
        check(row['entryTicks'] < post['ticks'], 'write time not after entry')
        check(f"post_write_{row['sample']:04d}" in names, 'post-write code check missing')
        results.append({'sample':row['sample'], 'state':hex(p), 'old_signed':f['selectorSigned'],
                        'new_u16':fields(after)['selectorU16'], 'changed_byte_offsets':changed,
                        'recursion_depth':len(recursion), 'game_function':hex(function['address']),
                        'game_callsite':hex(pc), 'ticks_to_post_write':post['ticks']-row['entryTicks'],
                        'flags_unchanged':f['flags154'] == fields(after)['flags154'],
                        'binding_source':source, 'semanticName':None})
    check(results, 'no actual selector stores observed')
    check(len(results) == capture['postWriteStopCount'] and len(results)+len(noops) == capture['targetEntryCount'],
          'writer observation counts differ')
    return {'schema':'weapon-marker-selector-writer-independent-audit/v1', 'passed':True,
            'capture':str(path.resolve()), 'capture_sha256':sha(raw), 'producer_sha256':sha(producer),
            'rows_checked':len(results), 'no_op_entries_checked':len(noops), 'code_blocks_checked':len(names),
            'game_callsites':dict(collections.Counter(r['game_callsite'] for r in results)), 'rows':results,
            'raw_stack_caller_chain_verified':True, 'raw_geometry_identity_verified':True,
            'primary_to_actor_raw_dereference_retained':all(raw_links),
            'binding_source_rows_verified':sum(s is not None for s in sources), 'semanticName':None,
            'limits':['Observed setter calls only; alias/copy writes and other modules remain outside this capture.',
                      'Raw pointer linkage is verified only for rows that retain identityRaw; older producer rows lack these windows.',
                      'Binding source provenance covers the captured original caller path, not all game states or resource selectors.',
                      'Selector index and FEP record identity do not identify the final muzzle/FX/ballistic consumer.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--producer', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.capture, args.producer)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('passed','rows_checked','game_callsites','primary_to_actor_raw_dereference_retained')}))


if __name__ == '__main__':
    main()
