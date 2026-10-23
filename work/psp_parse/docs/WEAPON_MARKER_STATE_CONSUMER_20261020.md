# Weapon-associated final-state downstream consumers, bounded static analysis

Later runtime evidence: [actual enqueue](WEAPON_ENQUEUE_RUNTIME_20261020.md)
verifies six exact-resource/exact-weapon insertions and all four D paths.
[The first render-entry capture](WEAPON_RENDER_DISPATCH_RUNTIME_20261020.md)
has zero stops. Later [alternate-path runtime evidence](WEAPON_RENDER_ALT_RUNTIME_20261020.md)
verifies six exact-weapon-associated handler invocations/returns; GE execution
remains unverified. The analysis below retains its original static scope.

`semanticName = null`. This analysis extends the **observed** final matrix
`P+0x60` to a concrete, conditionally reachable queue/render/GE chain. It does
not establish that the retained gun-associated state executed that chain, or
identify the visual as a muzzle flash, particle, projectile, or other effect.
No emulator connection, UI, input, or save-state operation was performed.

## Identity and reproduction

From `work/psp_parse`:

```powershell
python -X utf8 tools/analyze_weapon_marker_state_consumer.py
python -X utf8 -m unittest discover -s tools -p test_analyze_weapon_marker_state_consumer.py -v
```

Inputs are the exact selected module (base `0x08804000`, SHA256
`b5fc590366fc610f2cdd60104a4a28851bacd402c4600a4c296776e1dea0869f`),
its existing map, the already extracted FEP07 section (778816 bytes, SHA256
`97443c71b1c1d644f323c6ff611afb740329cfe11a47a711f39dc59de06ec802`),
and `slot0_weapon_marker_state_fep6_v2/marker_state_output.json`.

`out/WEAPON_MARKER_STATE_CONSUMER_20261020/state_consumer.json` retains the
identities, 15 literal instruction anchors, **39 explicitly enumerated** map
functions with full original bytes and word-addressed disassembly, static
registry entries, four FEP descriptor windows, and six saved-state rows. The
analysis never performs a module-wide search for `+0x60`. Generic Capstone
spellings such as `ldc2`/`sdc2` are not accepted as exact Allegrex VFPU mnemonics;
the original words remain authoritative. Nine offline tests pass, including
module/section/map identity, sidecar hashes, actual output equality, caller RA,
and original-byte range rejection. These tests do not execute the game.

## Observed boundary

All six saved rows independently reread by this tool have:

- actual helper output = generic output = full final-state bytes `[0x60:0xa0]`.
- updater outer RA `0x08b69f00`, from `0x08b69dbc` (map size **0xc8c**).
- the selected record first64 SHA256
  `04afeecb38df20d41a7c24da1686e31cf70a8e631aa51e48321c776ab21d89b6`.
- record byte `+6=0`, nonzero state list-bank1 pointer `P+0x184`.

For saved row0: `P=0x097d2540`, `P+0x184=0x097d2340`, source pointers
`+190=0x08d4d280`, `+194=0x08d4e234`, `+198=0x08d51b70`.
These are observations from a saved capture, **not constants for a new probe**.
No retained raw window yet covers that node's `+0x40` descriptor or a rendered
queue entry. The earlier live FEP audit proves bounded relocation/byte equality;
it does not fill this missing node-to-render identity.

## Static object-to-queue chain

```text
08b69dbc updater
  08b69ef8 -> 08b634ec(P), return 08b69f00 [observed update boundary]
  record P+198 byte+6 == 0 -> conditional 08b6a9e0 -> 08b69994(C,P)
    C+8c = P
    bank1 list head = P+184
    08b68924(C,P,1) -> per-node pre callbacks
    08b68e6c(C,P,1) -> per-node frame/event callbacks
    08b6902c(C,P,1) -> 08b68f14(C,node,node+40)
      per-definition post callback, registry vtable method+18
      type14 -> 08b92fcc
        node+50 matrix work; 08b65cb0 parent transformation
        08b935e8 -> 08bbdce8(E,C,bucketMode,bucketOption)
```

Earlier updater gates, state category masking, node flag8, empty lists, and
`u16(P+0xe)` can prevent this path. A nonzero `P+184` alone is insufficient.
`08b69994` checks category mask/state+0xa before the list walks. In the type14
callback, `node+0x3c` must hold a queue-entry pointer and `u16(P+0xe)` must be zero
to call enqueue. `08b65cb0` uses node parent transforms; it must not be renamed a
direct `P+60` reader.

At `08bbdce8`, `P=[C+8c]`, `N=[C+90]`; the successful path writes:

| Entry field | Original write | Meaning established by consumers |
| --- | --- | --- |
| `E+0/+4` | list links | previous/next entry |
| `E+8` | byte 1 | entry eligible for processing |
| `E+0xa` | u16 bucket | selected bucket index |
| `E+0xc` | C | context pointer |
| `E+0x10` | P, `08bbde70` | same final-state object |
| `E+0x14` | N, `08bbde74` | same child node |

The heads/tails are `0x08cb1460[320]` / `0x08cb1960[320]`. This is a queue
submission, not itself a GE draw. The function also directly passes `P+0x90`
(translation of the final `P+60` matrix) to its depth/bucket helper for one mode.
Separately, `08bbd864` reads all four vectors of `[E+10]+60`, combines them with
the node transform's translation, and calls a supplied callback with a computed
depth. That is an anchored matrix consumer in the same queue, not proof that a
particular rendering mode ran.

## Queue-to-render dispatch and original FEP candidates

`08bbda68` walks bucket entries and calls `08bbd7f0(E)`; `08bbdb20` similarly
calls `08bbd828(E)`. Their effective entry test is `byte(E+8)==1`.

```text
08bbd7f0 -> 08b69540(C,P,N) -> 08b692f4(C,P,N,1)
08bbd828 -> 08b69b58(C,P,N,1)
  D=[N+40]
  count=byte(D+15); u16 indices at [D+2c]
  B = *([D+1c] + 4*index)
  type = u16(B+0)
  object = registry08c3a820[type]
  dispatch vtable descriptor+20 (signed16 this-adjust, pointer+4)
```

Both render dispatchers filter state/node flags and a per-type bit at
`0x08c3acc0[type]`. Original type152/155 filter bytes are both zero, so they are
eligible for the `a3=1` pass if other gates pass. Capture the actual byte before
assuming the static registry and filter table remain unchanged at runtime.

The already verified table1[4] record at FEP offset `0xfb4` has a nested list at
`0x10b38` with four definitions. Extending **only that list** yields:

| Candidate `D` offset | Pre list | Post list | Render list `D+15/D+2c` |
| --- | --- | --- | --- |
| `10ba0` | 1,14 | 16,61,62,14,152 | index7, type152, B=`10ef0`, data offset`f0` |
| `10be8` | 1,14 | 16,14,152 | index5, type152, B=`11164`, data offset`90` |
| `10c30` | 3,14 | 3,5,16,61,62,14 | index7, type155, B=`11460`, data offset`120` |
| `10c78` | 1,14 | 6,16,61,62,14 | index9, type155, B=`118a0`, data offset`110` |

These are byte-accurate **original-resource candidates**, not an observed
`N+40` match. D byte`+0x19=2` is the pre-list count; do not mistake it for
`+0x1a` or for the render count at `+0x15=1`.

Original registry resolutions:

| Type | Object / vtable | Post method+18 | Render method+20 |
| --- | --- | --- | --- |
| 14 | `08c3ab14 / 08c51634` | `08b92fcc` | stub`08c15e4c` |
| 152 | `08c3ac08 / 08c51d14` | `08b97f08` | **`08b9809c`**, size`3f0` |
| 155 | `08c3ac14 / 08c51f44` | stub`08c15e44` | **`08b9a514`**, size`808` |

The type14 post method enqueues; type152/155 render methods consume the queued
node. Assigning a visual meaning from these numeric types would be speculation.

## Concrete matrix and GE paths

Both renderer candidates call `08b66bb4(C,N,inputMatrix,mode,outputMatrix)`;
the fifth integer argument is register **t0**, and f12 is also used.
At `08b66bd8/6be0`, if `N+0x1c==0`, it selects `P+0x60`, where `P=[C+8c]`.
Otherwise it selects `[[N+1c]+54]`. Subsequent mode branches choose matrix
operations. Recording the selected mode and parent is necessary before asserting
an exact equation or that every branch uses every selected matrix.

For type152 the matrix-helper return PCs are `08b98274` / `08b982b4`;
type155's corresponding return is `08b9a76c`. Each candidate then calls
`08bbb8d4` with a 64-byte matrix, returns `08b982bc` / `08b9a840`.

**Important:** `08bbb8d4` composes its input with the matrix at
`[0x08c3b588]`, then calls `08bfff6c(kind=1)` → `08c01088`. The kind1 branch
explicitly writes GE **VIEW cursor/data `0x3c/0x3d`**, twelve high24 float words.
It is not a WORLD upload; kind2 in the same writer writes `0x3a/0x3b`.
The global matrix's semantic name and VFPU multiplication order are not
promoted by this report. Capture its actual 64 bytes and writer input/output.

Type152 geometry path:

```text
08b9809c
  -> 08b62674 or 08b6270c (context+0xa0 resource container)
  -> 08b5dd50 or 08b5ddb0 (selected resource index)
  -> 08b5cb90 or 08b5d258
  -> 08bba1fc -> 08bfff98
```

Type155 resolves a resource from FEP header`+34`, uses context`+a4`, then:

```text
08b9a514 -> 08b60374 or 08b6050c
  -> 08b5e7d0 or 08b5ecac
  -> 08b5e368
  -> 08b5e3a8 -> 08bfff98
```

`08bfff98` visibly constructs GE commands: optional VTYPE`0x12`, optional
IADDR`0x02`, optional VADDR`0x01` with BASE`0x10`, and **PRIM`0x04`** written at
`08c0004c`. This establishes actual display-list generation in the static call
chain; it is not merely a math helper or a named-symbol inference. Runtime
geometry identity and the rendered appearance remain unobserved here.

## Minimal next observation contract

No new sampler is implemented in this task. Recommended first capture is the
smallest missing identity bridge: **one active BP at enqueue entry `08bbdce8`**.
Filter with source record SHA and independently recover the primary drawable
geometry identity as in the already validated writer/state captures. Do not
hardcode row0 P, node, FEP, or resource pointer addresses.

At entry, preserve `Q=sp`, `ra`, a0=E, a1=C, a2/a3 bucket options, all 32 GPRs
and guest ticks. Require return RA `08b935f0`, `[C+8c]=P`, `[C+90]=N`,
`[N+3c]=E`; read bounded guest-RAM windows:

- C `+0..0xa8`, P `+0..0x1ac`, N `+0..0x64`, E `+0..0x18`.
- `[N+40]` D `0x48` bytes; B and list bytes only after validating counts and
  pointer ranges against the selected relocated section. Capture definition
  list/index raw bytes; do not classify a pointer by numerical proximity alone.
- `[N+50]` and `[N+54]` 64 bytes each only if nonzero/in-range; selected parent
  node `N+1c` prefix through`+54` only if present.
- source record`P+198` at least first64 (or existing validated192), original
  FEP header identity, and primary handle/drawable metadata/geometry SHA.
- stack `Q..Q+0xd0`, whose type14-only expected saved returns are:
  `Q+74=08b68ff0`, `Q+a0=08b69080`, `Q+b8=08b69a40`,
  `Q+c8=08b6a9e8`. These offsets follow frames`80/30/10/10`; reject an
  alternate chain rather than applying these offsets to it.

Then remove entry BP, install **only** return BP`08b935f0`, require the same
SP=Q, read E again, and record v0. Accept enqueue only if E8=1,
`E+c=C,E+10=P,E+14=N` and bucket/link bytes agree. A rejected enqueue or timeout
is not an observed render submission.

Once an E/N/D is verified, a separate bounded render probe can use a single BP
at `08b692f4` entry (a0=C,a1=P,a2=N,a3=1), filtered to that identity. The selected
target is observable at `08b694f4` **before its delay slot**:

| Register/field at `08b694f4` | Value |
| --- | --- |
| sp | render dispatcher's frame, entrySP−`0x30` |
| s0 / s1 / s3 | C / N / D |
| `[sp+24]` | saved caller RA (normally`08b69558`) |
| a0 | already adjusted handler object |
| a1 | C |
| a2 | vtable method descriptor pointer, **not yet actual parameter** |
| t0 | actual parameter (delay slot copies it to a2) |
| a3 | mutable output data pointer |
| t2 | actual callback target |
| `[C+94]` | current B definition |
| future callback RA | `08b694fc` |

The alternate dispatcher uses `08b69d64`, future RA`08b69d6c`, saved caller
RA`08bbd858`. Capture the complete original function/handler bytes with both
validated JIT recovery routes; only switch to an actual target BP after its
registry/table identity is verified. No two simultaneous BPs are necessary.

The next conditional stages are helper `08b66bb4` entry/its selected return,
then `08bbb8d4` entry, then matrix writer`08c01088` entry/return. Preserve C/P/N
identity from callee-saved frames, mode, input/output64, actual global64, guest
SP/RA and caller raw stack. At matrix-writer entry a0=display-list context,
a1=kind(1), a2=matrix64, `[a0+8]`=command cursor; return should advance that
cursor by`0x34` and the raw words should be `3c000000` followed by twelve `3d`
payloads. Pointers must be independently guest-RAM bounded and cursor reads
limited to this expected packet size. A later PRIM observation must retain its
own caller ancestry and resource pointer/geometry bytes; temporal adjacency
alone must not associate an unrelated game draw with P.

Unresolved: actual node descriptor, executed handler, node-parent/mode equation,
GE packet identity for this state, and specific visual meaning. Until these
runtime links exist, the result is a concrete testable static route with a
known missing identity bridge, not confirmed muzzle/FX output.
