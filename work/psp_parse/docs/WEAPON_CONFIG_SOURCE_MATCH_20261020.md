# Binding config+0x8c fragment: original ISO candidates

Later evidence: [full-record runtime comparison](WEAPON_CONFIG_FULL_RUNTIME_20261020.md)
retains four complete 228-byte records and uniquely matches original record18.
The 34 matches below remain the historical result for the 16-byte fragment only.

The four retained `slot0_weapon_selector_binding_fire6` rows contain exactly the
same 16 original bytes:

```text
010000000100000016022800ef030000
u32 little-endian: [1, 1, 0x00280216, 0x000003ef]
SHA256: 35597676188bdff34218f0faaacc31ee7b2c73adf9914f4cae758879d2658165
```

Every sidecar's size and digest are checked. All four original observations have
`config = 0x09c9a368`, `config_8c.address = 0x09c9a3f4 = config+0x8c`.
The selector at config+0x90 is 1. The retained independent audit is bound to the
capture by SHA256; this tool does not re-execute that audit.

The **entire 1466406912-byte ISO** was searched without alignment restrictions,
including possible overlapping matches. ISO SHA256:
`448a90acdc7698270344ec14dd943da293084446ca5793acb0e2e8b1b68a15bc`.
There are **34 exact matches**, all in one original section:

| Field | Observed value |
| --- | --- |
| Pack ISO offset | `0x07571000` |
| Original pack type | `34` |
| Actual directory slot | `0` |
| Section offset within pack | `0x11c` |
| Section ISO offset | `0x0757111c` |
| Section size | `24632` bytes |
| Section SHA256 | `7411909bb4e848af75628d4c305bccc1d25361cdf91e79831984900f12e866f3` |
| Original first 8 section bytes | `6c00e40008000000` |
| Pack header size / SHA256 | `284` / `049cb065f893158e25f2ea10a4d0e63db175cc5ccadb4c16e59cf85b08ae390d` |

All 34 locations, actual raw pack header/directory bytes, section header bytes,
source section hashes, and coordinate equations are in `source_match.json`.
The 24632-byte `iso_section_0757111c.bin` is extracted from the **original ISO**,
not from runtime memory. Its digest and every matched 16-byte window were
verified after writing.

## Coordinate and layout boundaries

`raw/packs/pack_sections.csv` is the legacy schema
`pack,type,section,sec_off,size,kind`. Its `pack` field is relative to **3rd.pkg**,
unlike the separate `out/pack_sections.csv` schema's absolute ISO coordinates.
The tool resolves the original ISO9660 path `PSP_GAME/USRDIR/3rd.pkg` from raw
directory records, obtaining LBA `59600`, ISO offset `122060800`, and size
`1344292864`. Both endian copies of extent/size fields must agree.

It checks all **1663 CSV rows and 435 actual pack headers**. A CSV section number
is treated as the ordinal among nonempty original directory entries; the actual
raw slot is recorded separately. Conversions are explicitly:

```text
packISO = originalISO9660(3rd.pkg).offset + csv.pack
sectionISO = packISO + originalDirectory.sectionOffset
fragmentInSection = matchISO - sectionISO
candidateConfigOriginInSection = fragmentInSection - 0x8c
```

The raw first 8 bytes can be viewed numerically as `u16(108), u16(228), u32(8)`.
The arithmetic `8+108*228 == 24632` holds. All 34 candidate config origins align
with `8+i*228`, for indices:

```text
18..29, 51..53, 87..98, 101..107
```

This is a **candidate regular layout** inferred from raw fields and arithmetic.
It does not recover the complete config record format. The same fragment at 34
positions leaves 34 candidate source origins and candidate runtime bases.
Neither one full record nor a live section base is confirmed. The script keeps
`complete_config_record_verified=false` and `live_section_base_confirmed=false`.
It assigns no resource/FX/muzzle/action semantic name.

## Reproduction and outputs

From `work/psp_parse`, Python standard library only:

```powershell
python -X utf8 tools/match_weapon_config_fragment_iso.py --capture out/AYA_BONE_GE_ACTIONS/slot0_weapon_selector_binding_fire6/marker_selector_writer.json --audit out/WEAPON_MARKER_SELECTOR_20261020/binding_fire_independent_audit.json --iso ../../PSP/The_3rd_birthday_cn_full_v101.iso --sections raw/packs/pack_sections.csv --out-dir out/WEAPON_CONFIG_SOURCE_MATCH_20261020
```

Outputs are `source_match.json`, `config_8c_fragment.bin`, and the original ISO
section blob in `out/WEAPON_CONFIG_SOURCE_MATCH_20261020/`. The JSON binds the
capture, audit, inventory, original ISO, and parser script by digest and retains
the exact reproduction command.

Search scope is original ISO bytes only. No separate decrypted module/data
search, decompression, PPSSPP connection, UI, save modification, or RAM dump was
performed. Exact byte equality is source-candidate evidence, not loader identity.
