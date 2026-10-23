# Exact weapon-associated render callback observer

This independent producer observes actual render-handler **invocation and
return**, using one active owned breakpoint. It does not capture a GE draw or
assign the visual a muzzle/FX semantic name. Previous enqueue fire6 evidence
establishes all four actual D paths; it does not itself prove these callbacks.
This task implements and VM/Mock-tests the producer only, without a PPSSPP/UI
connection, save-state change, or edits to previous producers/auditors/UE.

Files: `tools/trace_weapon_marker_render_dispatch.js`, independent
`tools/trace_weapon_marker_render_dispatch_selftest.js`; final producer/test/log
identities are in `out/WEAPON_MARKER_RENDER_MOCK_20261020/verification.json`.

## Parent runner interface

From `work/psp_parse`, against the parent's existing selected debugger only:

```powershell
$env:MARKER_RENDER_OUT_DIR = '<new independent output directory>'
$env:PPSSPP_DEBUGGER_PORT = '9900'
$env:MARKER_MAX_ROWS = '6'
$env:MARKER_MAX_STOPS = '1200'
$env:MARKER_DURATION_MS = '15000'
$env:MARKER_STAGE_TIMEOUT_MS = '3000'
$env:MARKER_BUTTONS_JSON = '{"square":true}'
node tools/trace_weapon_marker_render_dispatch.js
```

Default buttons are `{}`; analog is opt-in via `MARKER_ANALOG_JSON`. Input keys
are released explicitly in finally, with an opt-in analog reset. Reports refuse
overwrite. Existing enabled breakpoints, or a disabled breakpoint at any of
the three targets, cause refusal without modifying those breakpoints. Queued
stepping messages retain the owned BP at receipt. No setup message is dropped;
an external pause remains paused even when queued during an RPC/add-ACK timeout.

One owned BP alternates:

```text
ENTRY 08b692f4 -> DISPATCH 08b694f4 -> RETURN 08b694fc
```

Full original functions `08b692f4/24c` and wrapper `08b69540/24` are checked
before any BP. Every stage switch removes the old BP, verifies the next8 code
bytes, then adds only the next BP. The actual selected handler's complete range
is checked at DISPATCH before advancing to RETURN. Identity requires **both**
`memory.read(replacements=false)` and `memory.disasm` opcode/macro recovery to
equal the selected original module; a raw JIT emuhack prefix is never accepted
without those two exact recoveries. The module's SHA256 remains
`b5fc590366fc610f2cdd60104a4a28851bacd402c4600a4c296776e1dea0869f`.

## ENTRY contract

At `08b692f4`, record `Q=sp`, all32 u32 GPRs, ticks, a0=C, a1=P, a2=N,
a3=pass. Only pass1 is in scope. The wrapper caller RA is exactly `08b69558`.
Longer GPR categories (35/36 values) are diagnosed and the first32 validated.

**C+8c/C+90 may still refer to a previous queued state/node at ENTRY.** Original
`08b692f4` writes them later; therefore their identity is required at DISPATCH,
not speculatively at the function entry.

Selection repeats the enqueue producer's strict original weapon and resource
checks: P+144 handle4 → actual drawable `+3c4/40`, metadata64, draw16, three
bones, one draw, VTYPE522, stride16, 243 vertices, exact geometry-with-VTYPE SHA
`168578abca4c4f5d22d5994ebced6b93a25d5167428bfd47f1a1150a8d42e65a`.
Raw identity sidecars and geometry are retained.

P+198 prefix64 SHA is
`04afeecb38df20d41a7c24da1686e31cf70a8e631aa51e48321c776ab21d89b6`;
record192 must match the original FEP exactly. Source190/194/198 chain and
bounded header/table1 slot4/record4/nested-list windows follow the already
validated enqueue contract. Header offsets keep the established compatibility;
actual D/table1/list/definition pointers must be absolute `base+originalOffset`,
with original nulls remaining zero. All guest reads are aligned, bounded to
`[08000000,0c000000)`, and individually at most`0x20000` bytes.

Retain C`a8`, P`1ac`, N`64`, D=`[N+40]` prefix`48`, ENTRY stack`30`, exact
pre/post/render lists and definition prefixes. Only actual D offsets
`10ba0/10be8/10c30/10c78` are supported; their render lists contain exactly1
item. Unsupported candidates keep their original raw evidence in `inFlight`
before rejection. No heap/node/world/matrix address is hardcoded from a sample.

## DISPATCH is before JALR and its delay slot

At `08b694f4`, the actual JALR has **not** run, and the instruction at
`08b694f8` (`move a2,t0`) has **not** run. Actual callback RA will become
`08b694fc`. Save all GPRs, stack`30`, context/node raw windows and current B.

Required live registers:

| Register | Meaning/value |
| --- | --- |
| sp | Q−30 |
| s0 / s1 / s2 / s3 | C / N / pass1 / D |
| s4 / s5 | render ordinal0 / exact render-list address |
| s6 / s7 | `08c3acc0` type-filter base / `08c3a820` registry base |
| a0 | already adjusted handler object |
| a1 | C |
| **a2** | vtable method descriptor address `vtable+20` |
| **t0** | actual callback parameter, copied to a2 by delay slot |
| a3 | node mutable-data pointer; not assumed a matrix/output |
| t2 | actual callback target |

The dispatcher frame preserves original ENTRY s0..s7 at offsets
`4,8,c,10,14,18,1c,20`; caller RA at`24` equals ENTRY RA`08b69558`.
Those raw saved words must match ENTRY GPRs. `[C+8c]=P`, `[C+90]=N`,
`[N+40]=D`, and `[C+94]` must be the original current D render definition B.

For actual type152/155, retain actual runtime:

- registry slot4 at `08c3a820+4*type`;
- object4 containing its vtable pointer;
- vtable prefix`28`, method20 descriptor8 (signed16 this-adjust and target+4);
- actual filter byte at `08c3acc0+type`, saved as an aligned raw word plus its
  actual field address/byte index.

Registry evidence is added to the report incrementally so an invalid pointer
does not orphan already-read slot/object bytes. The runtime slot/object/vtable/
method must match the original registry, actual t2 must equal its target, a0
must equal object+signed adjustment, a1=C, a2=vtable+20, and filter bit0 must be
zero for pass1. Default supported targets are:

| Type | Full target/range | t0 parameter bytes | a3 data bytes |
| --- | --- | --- | --- |
| 152 | `08b9809c/3f0` | `20` | **7** |
| 155 | `08b9a514/808` | `4c` | **20** |

The actual parameter slot `[N+48]+4*definitionIndex` is read raw and must equal
t0. a3 must equal `[N+44]+u16(B+2)`. The producer does not substitute the earlier
a2 method-descriptor pointer for the actual parameter.

These snapshot extents follow the supported handler's required reads:
type152 parameter bytes through`+1f`, mutable data through`+6`; type155 parameter
through`+4b`, mutable data through`+1f`. **No blind a3 64-byte read occurs.**
Original D+2 u16 observations are `f7/97/140/130`, with data offsets
`f0/90/120/110`. Their remaining spans coincide with7/7/20/20, but D+2 is
reported as `sourceD2Observed`, not promoted here to a universal allocation-size
format. FPR/VFPU registers (including f12 time) are not sampled; this producer
establishes invocation identity, not exact matrix or animation equations.

## RETURN contract

At callback return `08b694fc`, require the same SP=Q−30 and RA=`08b694fc`.
All callee-saved GPRs s0..s7/fp must equal their DISPATCH values. Re-read stack30
and validate its original saved registers/RA against ENTRY again. Re-read C/P/N;
require current C8c/C90/C94 and N40 identities, source190/194/198 identity,
the exact original FEP192, and full exact weapon geometry identity. Retain the
raw return identity windows and geometry. Snapshot the same parameter/data
addresses and extents again; changes are recorded without forcing equality.

Success means `classification="observed_handler_invocation_return"`,
`geDrawObserved=false`, `semanticName=null`. A stage timeout preserves unknown
execution outcome in `inFlight`; it never produces a successful row. Unknown
caller/type/registry/target or wrong SP/saved-registers are fail-closed, with
already collected bytes retained. Both CODE recovery routes must pass for a
completed row. Nothing here names a muzzle socket, particle, or final FX.

## Report schema

`marker_render_dispatch.json`, schema
`weapon-marker-render-dispatch-capture/v1`. Top level includes identities,
codeIdentity, three stop counts, selected-target count, bounded guest ticks,
rejections, transitions/input ACKs, GPR category diagnostics, inFlight/rows,
cleanup/failure, semanticName/geDrawObserved and negativeScope. Every raw window
is `{address,size,raw:{file,bytes,sha256}}`; raw identity/geometry retain the
earlier byte-sidecar convention.

Successful row:

```text
sample,entryPC,entryTicks,entryGPR,entrySP,entryRA,entryArgs{C,P,N,pass},C,P,N,D,
entry{context,state,node,descriptor,stack},weapon{...,geometry,identityRaw},
resourcePrefix64,resource{source190,source194,source198,header,table1Slot4,
 table1Record4,record192,prefix64,nestedList},descriptorPath,renderList,
dispatch{pc,ticks,gpr,sp,stack,context,node,currentB,definition,definitionIndex,
 actualType,target,parameterPointer,mutableDataPointer,expectedDelaySlotA2,
 registry{slot,object,vtable,method20,filter{fieldAddress,byte,raw},
          thisAdjustment,target},
 parameterSlot,mutableDataBase,sourceD2Observed,parameterBefore,mutableDataBefore},
returned{pc,ticks,gpr,sp,ra,stack,context,state,node,weapon,resourceRecord192,
 parameterAfter,mutableDataAfter},classification,geDrawObserved,semanticName
```

Incomplete DISPATCH/RETURN data is retained under `inFlight.dispatchAttempt` or
`inFlight.returnAttempt`; completed rows use `dispatch`/`returned` only.

## Offline validation boundary

81 VM/Mock scenarios pass:8 successful shapes,9 bounded target-negative cases,
64 fail-closed/timeout/cleanup cases. They cover all four D paths and both real
target ABIs, stale ENTRY context, GPR35/36, exact raw parameter/data extents,
before-delay-slot arguments, registry object/vtable/method/filter/target changes,
full-target code failure, saved stack/GPR mismatches, return geometry/FEP
identity changes, entry/dispatch/return read failures, missing stages, external
pauses, and add-ACK timeouts at all three stages with owned/foreign queued stops.

Only a parent-controlled real capture and its independent auditor can establish
actual invocation/return. GE packet generation, exact geometry-to-PRIM binding,
matrix equations and the final visual semantic remain separate future evidence.
