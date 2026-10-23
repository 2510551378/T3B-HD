# Selected FEP07 table0/table1 offline graph

This inventory covers the two 93-entry tables of the already identified section.
It does not assign FX, muzzle, action, or other asset names to unnamed records.
No emulator connection, UI action, original-asset edit, or UE/runtime change is
performed by this tool.

## Inputs and reproduction

Run from `work/psp_parse`, using Python 3 with the standard library only:

```powershell
python -X utf8 tools/parse_selected_fep_graph.py --section out/WEAPON_MARKER_STATE_20261020/original_source_match_section.bin --module raw/ULJM05798_module_08804000.bin --live-verification out/WEAPON_MARKER_STATE_20261020/fep6_v2_source_verification.json --out-dir out/SELECTED_FEP_GRAPH_20261020
```

The tool binds these full original-file identities:

- Section: 778816 bytes, SHA256 `97443c71b1c1d644f323c6ff611afb740329cfe11a47a711f39dc59de06ec802`.
- Module base `0x08804000`, SHA256 `b5fc590366fc610f2cdd60104a4a28851bacd402c4600a4c296776e1dea0869f`.

It validates 14 literal MIPS instruction anchors from the constructor
`0x08b639f0` and reader/selector `0x08b6416c`. It does not analyze or modify the
separately investigated `0x08b651fc` writer. Complete words and explanations are
retained in `graph.json/code_evidence`, with the module digest.

## Direct observations and candidates

All offsets below are little-endian and relative to the beginning of the section.

| Source location | Observation | Interpretation boundary |
| --- | --- | --- |
| Header `+0x14` | `778816` | Exact original section length |
| Header `+0x1c/+0x1e` | `93/93` | Counts fit table0/table1; selector directly reads table0 count |
| Header `+0x28/+0x2c` | `0x50/0x1c4` | Offset-table starts; constructor directly reads table1 pointer |
| table0 targets | `0xa88..0xed8`, all increments 12 | All 93 bounded descriptors read as three original u32 words |
| Descriptor `+4` | u16 in `0..92` | Selector passes it to constructor as table1 index |
| Descriptor `+6` | u16 in `1..5` | Selector loop count, direct 4-byte pointer-list stepping |
| Descriptor `+8` | in-section offset | Selector dereferences it as pointer list |
| table1 targets | `0xee4..0x2194`, all increments 52 | Observed 52-byte record stride in this section |
| table1 `+0x1c..+0x30` | six aligned in-section offsets | All six relocated in retained live index4 window; other 92 entries offline only |

Header `+8 = 0x48` is **not** treated as a header length: the retained runtime
evidence shows that word being relocated. The parser preserves a raw 0x50-byte
observation window and does not rename the remaining header fields.

The 93 descriptor lists contain 133 references to 133 distinct record starts.
List-count histogram is `{1:65, 2:20, 3:5, 4:2, 5:1}`. There are 40 pairs of
consecutive records within lists, and all 40 differences are 192 bytes. Every
192-byte candidate range is bounded and does not consume the following known
object start. A universal 192-byte format is still a candidate: only record
`0x48f0` has the supplied live 192-byte equality evidence.

The original selected chain is retained unchanged:

```text
header.table0[4] -> descriptor 0xab8
  raw u32 = [0x00286800, 0x00010004, 0x000048e0]
  table1 index=4, list count=1
  list 0x48e0 -> record 0x48f0, candidate bytes=192
header.table1[4] -> record 0xfb4, observed stride=52
```

For each table1 record, let the six offsets at `+0x1c..+0x30` be `p0..p5`.
Across **all 93** entries the following exact relations hold:

```text
p1-p0 = 4 * u16(+0x10)
p2-p1 = 4 * u16(+0x12)
p3-p2 = align4(2 * u16(+0x14))
p4-p3 = 4 * u16(+0x16)
p5-p4 = 4 * u32(+0x18)
```

These are count/width candidates constrained by original byte layout. The
constructor independently proves the `u16(+0x14)` count, `+0x24` list pointer,
and 2-byte element stepping. The other count/width relations are not promoted
to general format rules. Alignment bytes remain separately recorded, never
silently included as another element.

The five array count totals are `[107,391,1003,1116,93]`. Arrays 0, 1, 3, and 4
produce 1707 distinct in-section offset candidates. Array 2 retains its actual
u16 values. The tool stops at opaque lower-level targets instead of guessing
that arbitrary later words are pointers. Some opaque targets have next-start
windows of 8 or 72 bytes; this is an observed boundary pattern, not recovered
type meaning or declared object length.

## Shared references

The graph reports 186 addresses with multiple incoming references:

- 93 table1 records are referenced both by their table slot and a descriptor's
  `+4` index.
- At every table1 entry, the first target in array0 is the same original address
  as the sixth direct offset `p5`.

There are no shared table0 descriptor/list/192-byte-record addresses and no
duplicate addresses among the 1707 nested offset candidates. These findings
apply to this section and the explicitly enumerated edge levels.

## Output contract for downstream PC readers

Files in `out/SELECTED_FEP_GRAPH_20261020/`:

- `source.bin`: all original 778816 bytes, byte-identical SHA256; relative graph
  offsets refer to this blob. It retains every unknown byte.
- `graph.json`: original header words; all table0/table1 rows; raw u32/u16
  fields; range-checked lists; candidate fields labeled as candidates; raw
  prefix hex and SHA per node; incoming edges, shared references, and the
  lossless byte partition.
- `table0.csv`, `table1.csv`: compact, complete 93-row inventories.
- `verification.json`: input and produced-graph digests, summary, reproduction
  command, read-back/roundtrip validation, and all negative-test results.

`nodes[].minimum_bytes` is the parsed or explicitly candidate prefix length.
`next_observed_start_span` is a bounded window up to the next known graph start,
**not** the object's asserted length. It can include uninterpreted children,
other unparsed tables, padding, and unrelated bytes. Reading these bytes is
safe; assigning them to one recovered object would require more evidence.

For any node, downstream readers can slice
`source[node.offset : node.offset + node.minimum_bytes]` and verify its
`raw_sha256`. Each node also retains the exact `raw_hex`. The parser's
`lossless_partition` covers every source byte exactly once; it is read back
from the published JSON/blob and reconstructed to confirm exact equality.

The graph contains 2587 nodes and 2770 edges. Parsed or candidate prefixes cover
48506 bytes; the remaining 730310 bytes are explicitly opaque and preserved.
Prefix coverage is **not** a percentage of recovered semantics.

## Verification and remaining limits

All range/overlap/known-pointer checks and published raw-byte checks pass.
Seventeen malformed-input cases are rejected, covering truncation, magic,
declared length, empty count, table alignment/range, descriptor index/list
count/range, record range/overlap, table1 count/span inconsistency, and a nested
target outside the section. These test malformed source data, not gameplay.

The supplied `fep6_v2_source_verification.json` is bound by digest and schema.
It proves the previously retained index4 bounded live chain/record comparison;
this new offline inventory does not independently re-run that live audit or
claim a full-section runtime-byte comparison. Original constructor execution,
unknown lower-level formats, other header-table formats, resource semantics,
and PC playback of this graph remain outside this artifact's evidence.
