# Alternate render callback observer ABI

New independent producer: `tools/trace_weapon_marker_render_alt.js`.
Independent VM/Mock suite: `tools/trace_weapon_marker_render_alt_selftest.js`.
No previous producer, capture, auditor, checkpoint or UE file is changed.
This task does not connect PPSSPP, use UI/input, or alter saves.

The alternate route now has the parent's separate real routes observation
(`out/WEAPON_QUEUE_ROUTES_RUNTIME_20261020/queue_routes_fire6_independent_audit.json`):
controller2e=0/2f=1, alternate range/entry stops and advancing guest ticks.
That evidence supports selecting this new route. It does **not** establish a
completed handler invocation/return by this new producer, a GE draw, or an FX
semantic name. Successful new rows still require the full three-stage proof.

## Independent entry points and original machine code

One owned BP only, alternating:

```text
ENTRY 08b69b58 -> DISPATCH 08b69d64 -> RETURN 08b69d6c
```

Complete original functions verified before arming:

| Address | Bytes | Original boundary |
| --- | --- | --- |
| `08b69b58` | `258` | alternate render dispatcher |
| `08bbd828` | `3c` | per-entry alternate wrapper |

The fixed module SHA remains
`b5fc590366fc610f2cdd60104a4a28851bacd402c4600a4c296776e1dea0869f`.
Each full function and stage-transition8-byte window must match the original
through **both** replacements=false and disasm opcode/macro recovery. Actual
type152/155 full target code is checked again at DISPATCH. Producer self SHA
is computed at module load and retained in every report.

Independent original anchors, also checked by the offline suite:

```text
08b69b58 27bdffd0  addiu sp,sp,-30
08bbd850 0e2da6d6  jal 08b69b58
08bbd854 34070001  ori a3,zero,1       (wrapper delay slot)
08b69d64 0140f809  jalr t2
08b69d68 01003025  move a2,t0          (dispatch delay slot)
08b69d6c 92640015  lbu a0,15(s3)      (first callback-return instruction)
```

## Three-stage contract

All raw identity, exact weapon geometry/FEP192, descriptor relocation, registry,
stack/GPR, bounds, cleanup and external-pause guards from
`WEAPON_MARKER_RENDER_DISPATCH_ABI_20261020.md` are preserved. This document
specifies the different entry/caller PCs rather than pretending the routes are
one function.

ENTRY: a0=C, a1=P, a2=N, a3=pass1, Q=sp,
**caller RA=`08bbd858`**. Shared C8c/C90 can still name a previous item until the
original dispatcher updates them; actual C/P/N/D identity is enforced at
DISPATCH. C/P/N windows are a8/1ac/64; D candidates remain the four original
FEP offsets10ba0/10be8/10c30/10c78, with one render definition each. Original
weapon SHA, three bones, 243 vertices, VTYPE522 and exact FEP192 remain required.

DISPATCH at `08b69d64`, **before** JALR and delay slot:

| Register/field | Required meaning |
| --- | --- |
| sp | Q−30 |
| s0 / s1 / s2 / s3 | C / N / pass1 / D |
| s4 / s5 | render ordinal0 / actual D render-list address |
| s6 / s7 | original filter base08c3acc0 / registry base08c3a820 |
| `[sp+24]` | ENTRY caller RA08bbd858 |
| `[sp+4..20]` | original ENTRY s0..s7 saved words |
| a0 | adjusted actual handler object |
| a1 | C |
| **a2** | actual vtable method20 descriptor address |
| **t0** | actual parameter copied to a2 by delay slot |
| a3 | mutable node-data pointer, not assumed a 64-byte output matrix |
| t2 | actual target matching the original registry |
| C8c/C90/C94 | P / N / exact current render definition B |

Actual registry slot/object/vtable/method20/filter raw windows are saved
incrementally. Supported actual targets are type152=`08b9809c/3f0` and
type155=`08b9a514/808`. Actual t0 must come from `[N48]+4*index`; actual a3 must
be `N44+u16(B+2)`. Parameter windows are20/4c bytes; mutable-data windows are
**7/20** bytes for152/155 respectively. Unknown type/target/pointer fails with
preserved partial raw evidence. There is no blind data64 read.

RETURN=`08b69d6c`: same SP=Q−30, RA=RETURN, original dispatcher saved stack and
DISPATCH callee-saved s0..s7/fp preserved. Re-read C/P/N, exact weapon identity
and geometry, source190/194/198 and exact original resource192. Re-read only
the same bounded parameter/data windows. Data changes are recorded without
forcing equality. A missing/incorrect return keeps an incomplete `inFlight`;
it never produces a successful row.

## N+4c time branch and setup differences

The alternate function explicitly loads time base f20 from N+30 at69bf0. At
69d04 it loads N+4c, indexes the selected definition's time-slot pointer, reads
that pointer at69d1c, and tests it at69d20. If nonzero,69d28 reads signed16 at
record+4 and69d2c..34 convert/subtract it from f20 into f12. A null slot skips
that adjustment. The prior dispatcher has the corresponding conditional
operation at69494..c4; its PC differs, but neither route permits assuming that
f12 always equals the unadjusted node time.

This producer retains N+4c in its node64 window but does **not** dereference the
time-slot table/record or sample FPR/VFPU. Actual branch choice and f12 are
therefore **not observed**. GPR a3 at DISPATCH has already been repurposed as
mutable-data pointer, so it cannot be mislabeled as the prior time-record
pointer. The purpose is invocation/return identity; no animation equation is
validated from the absent FPR/time-slot data.

One additional concrete setup difference is retained as raw evidence:
the alternate69c54..84 path uses record`P198` flags+4 bit0200 to select the
`08bb9d34` argument, whereas the older693f0..414 path tests signed state+1a8
against2. No visual meaning is assigned to either flag or state setup.

## Interface, schema and validation

Use a new independent output directory with the parent's safe existing runner:

```powershell
$env:MARKER_RENDER_ALT_OUT_DIR = '<new independent alt capture directory>'
$env:PPSSPP_DEBUGGER_PORT = '9900'
$env:MARKER_MAX_ROWS = '6'
$env:MARKER_MAX_STOPS = '1200'
$env:MARKER_DURATION_MS = '15000'
$env:MARKER_STAGE_TIMEOUT_MS = '3000'
$env:MARKER_BUTTONS_JSON = '{"square":true}'
node tools/trace_weapon_marker_render_alt.js
```

Buttons default to{}; optional analog/limits use the same existing interface.
Finally releases requested inputs, removes only its own BP and preserves any
external pause, including queued stops during any stage's add-ACK timeout.
No report is overwritten. MARKER_RENDER_OUT_DIR is **not** used by this new
producer; MARKER_RENDER_ALT_OUT_DIR or explicit generic MARKER_OUT_DIR is required.

Output filename stays `marker_render_dispatch.json`, schema stays
`weapon-marker-render-dispatch-capture/v1`; additive report field
`route="alternate69b58"` and entry/dispatch/return PCs identify this producer.
All row raw-window fields are the same as the prior documented schema.
Successful classification remains `observed_handler_invocation_return`,
`geDrawObserved=false`, `semanticName=null`.

The independent Mock suite preserves all81 prior failure/success scenarios,
substitutes and explicitly checks the new PCs/RA/full-code ranges, and adds
the six original anchors above. It exercises both actual handler types, all
four D paths, stale ENTRY context, GPR35/36, strict FEP/live-pointer identity,
actual registry/target/data provenance, saved register/stack guards, target
code mismatch, return weapon/FEP identity, all three stage timeouts/read
failures/queued foreign stops, and owned-BP cleanup. Result:81 PASS; exact
producer/test/log hashes are in
`out/WEAPON_MARKER_RENDER_ALT_MOCK_20261020/verification.json`.

This suite uses only VM/MockWebSocket. It is not a real callback observation.
The parent must separately freeze this producer, run a hidden API capture and
audit raw evidence before asserting actual handler invocation/return.
