# Exact weapon-associated enqueue observer ABI

The new independent producer is `tools/trace_weapon_marker_enqueue.js`; the
independent offline VM/Mock test is `tools/trace_weapon_marker_enqueue_selftest.js`.
This task does **not** run PPSSPP, use UI/input, change saves, or edit any previous
capture producer/auditor. Mock input RPCs go only to the test's fake WebSocket.

Successful rows mean `classification="observed_enqueue"`,
`geDrawObserved=false`, `semanticName=null`. An enqueue observation is not a
geometry draw or a verified muzzle/FX interpretation. The prior bounded static
consumer document remains the source of the downstream render hypotheses.

## Invocation contract for the parent-controlled existing debugger

Only the parent should run this against its already selected safe runner.
From `work/psp_parse`, the observer command is:

```powershell
$env:MARKER_ENQUEUE_OUT_DIR = '<new independent capture directory>'
$env:PPSSPP_DEBUGGER_PORT = '9900'
$env:MARKER_MAX_ROWS = '6'
$env:MARKER_MAX_STOPS = '1200'
$env:MARKER_DURATION_MS = '15000'
$env:MARKER_STAGE_TIMEOUT_MS = '3000'
$env:MARKER_BUTTONS_JSON = '{"square":true}'
node tools/trace_weapon_marker_enqueue.js
```

Default buttons are `{}`: no held input. Optional `MARKER_ANALOG_JSON` uses the
same existing `{stick,x,y}` API shape, with finite x/y in `[-1,1]`. The finally
block explicitly releases every requested button plus the standard action keys,
and zeros an explicitly requested analog stick. It removes only the producer's
owned BP. Any pre-existing enabled BP, or even disabled BP at one of the two
target addresses, is rejected without changing it. Reports are never overwritten.

The two targets are **ENTRY `08bbdce8` → RETURN `08b935f0`**, with only one
owned BP active at any time. The attempted add is recorded before its ACK so a
timeout still triggers its removal. Stepping events are queued at receipt with
their owned-BP identity; no setup event is silently discarded. External stops,
including ones queued during RPC/ACK failure, stay paused. Cleanup resumes only
a positively identified owned stop and never after an external pause was seen.

Each capture reports the producer file's self SHA256 computed once at module
load. The final offline-tested producer/test/log identities are retained in
`out/WEAPON_MARKER_ENQUEUE_MOCK_20261020/verification.json`. An earlier parent
freeze `.../trace_weapon_marker_enqueue_sampled.js` was **not runtime sampled**;
use a distinct `trace_weapon_marker_enqueue_strict_sampled.js` freeze for this
stricter live-pointer producer.

## Original-code and target selection guards

Selected module SHA256:
`b5fc590366fc610f2cdd60104a4a28851bacd402c4600a4c296776e1dea0869f`.
Before arming any BP, verify all six complete original function ranges through
both `memory.read(replacements=false)` and `memory.disasm` opcode/macro recovery:

| Address | Bytes | Role |
| --- | --- | --- |
| `08bbdce8` | `19c` | enqueue |
| `08b92fcc` | `63c` | type14 post handler, includes RETURN |
| `08b68f14` | `118` | post dispatcher |
| `08b6902c` | `78` | bank post walk |
| `08b69994` | `c0` | selected bank1 path |
| `08b69dbc` | `c8c` | update caller |

Raw JIT-visible, recovered-original and disassembly bytes are all saved. A `68`
prefix alone is never accepted. The return-point `18` bytes are freshly checked
after ENTRY BP removal and before RETURN BP add. The expected metadata geometry
is one draw, VTYPE`522`, 243 vertices, stride16, three source bones, full geometry
SHA256 with VTYPE prefix:
`168578abca4c4f5d22d5994ebced6b93a25d5167428bfd47f1a1150a8d42e65a`.

ENTRY a0=E, a1=C, a2/a3 are original byte-derived bucket options. Read
`P=[C+8c]`, `N=[C+90]`. The selected resource's actual prefix64 must have SHA256
`04afeecb38df20d41a7c24da1686e31cf70a8e631aa51e48321c776ab21d89b6`.
P+144 is a handle pointer; the producer reads its original four bytes, follows
the drawable, reads raw drawable `+3c4/40` bytes, metadata64, draw16 and exact
geometry. A mere actor pointer or old hardcoded RAM address is insufficient.

Only the first32 GPR values are used, all strictly u32. Longer categories such
as 35/36 values retain their actual category length/name diagnostics.

## ENTRY caller and data ABI

At the enqueue function's first instruction, `Q=sp`, `ra=08b935f0`. Save the
entire original stack `[Q,Q+d0)` before checking:

| Raw saved-return word | Required value |
| --- | --- |
| `Q+74` | `08b68ff0` |
| `Q+a0` | `08b69080` |
| `Q+b8` | `08b69a40` |
| `Q+c8` | `08b6a9e8` |

This is the exact previously derived type14/post/bank1 chain; an alternate
caller is rejected, not unwound using speculative offsets. Selected candidates
retain context/state/weapon/stack raw evidence in `inFlight` before rejection.

All reads require aligned addresses in guest RAM `[08000000,0c000000)`, with
each read no larger than `0x20000`. Raw window schema is consistently:

```text
{address, size, raw:{file,bytes,sha256}}
```

Entry windows: C`a8`, P`1ac`, N`64`, E`18`, D=`[N+40]` prefix`48`; require
`[N+3c]=E`. The unsupported actual D prefix is saved before failing closed.
Only these selected original FEP offsets are supported:
`10ba0/10be8/10c30/10c78`. Their pre/post/render lists use the exact original
counts and indices, at most32 elements/list, index<96. List raw windows are
rounded to4 bytes; count remains explicit. Definition pointer words and every
definition's first12 bytes are saved, with first8-byte original equality and
the `+8` pointer relocation verified.

**Live consumer pointers are strict:** D list/table pointers, table1 slot4,
table1 nested-list pointer, all four nested D pointers, definition-table slots,
and definition `+8` pointers must equal absolute `sourceBase+originalOffset`
(or zero only for an original null). Raw source offsets are not silently rebased
into valid consumer pointers. The existing bounded **header** compatibility
contract stays unchanged: `+8/+28/+2c` may be their exact original offsets or
base-relocated forms. This compatibility does not relax D/list live pointers.

Source190 is read from P, with a guest-RAM bound over the known original
section size `be240`. Read header50, table1 slot4, table1 record4`34`, nested
list16, resource record`c0`; check magic/version/size/counts and selected
P194=`base+fb4`, P198=`base+48f0`. The record192 must remain byte-identical to
the original retained section. No other FEP ranges are dumped.

Read N's nonzero transform pointers +50/+54 as finite matrix64. At most two
immediate parent pointers (N+18 and N+1c) are read, each prefix64 and optional
matrix64 at its +50/+54. A self-parent is rejected. There is no recursive parent
traversal and no guessed parent/transform naming beyond the field offsets.

## RETURN and bucket-link evidence

At RETURN require sp=Q, ra=`08b935f0`, and all original callee-saved GPRs
s0..s7/fp unchanged. Preserve actual return GPRs and E/C/P/N windows before
checking output. The successful E must have:

```text
E8=1; E+c=C; E+10=P; E+14=N
bucket=u16(E+a), 0<=bucket<320, v0=bucket
E.next=0; E.prev=oldTail
```

The original bucket head/tail arrays are **runtime words** captured at ENTRY:
`08cb1460/500` and `08cb1960/500`. After RETURN, read the selected bucket's
actual head4/tail4 words, then the prior tail's first8 bytes when nonzero.
An empty bucket requires oldHead=oldTail=0 and newHead=newTail=E. A nonempty
bucket requires unchanged head, newTail=E, E.prev=oldTail and oldTail.next=E.
The producer does not merely calculate a bucket and assert it was used.

The source mode tables are also saved as runtime raw bytes at `08c2de70/220`.
This address is important: original `lui 08c3` plus **signed** `de72/de8a`
addresses `08c2de72/08c2de8a`, not `08c3de72/08c3de8a`. The window covers the
u16 table and byte table for original byte modes0..255. Original table1 record4
raw data includes its `+a/+b` selector bytes. Depth-dependent modes remain
auditable through the raw matrices, metadata and actual returned bucket;
no unsupported producer-side depth equation is asserted.

P must remain byte-identical through enqueue; C's current P/N and N's queue
pointer must remain unchanged. An enqueue failure, a wrong chain, timeout,
unknown D, or partial return retains its `inFlight`/`returnAttempt` raw evidence
and reports failure. It never emits a successful row for an incomplete return.

## Report schema for the independent auditor

Report: `marker_enqueue.json`, schema`weapon-marker-enqueue-capture/v1`.
Top-level includes producer/module/originalFep identities, codeIdentity,
first/last guest ticks, stop/target counts, rejections, transitions, input ACKs,
initialBreakpoints, GPR category diagnostics, inFlight, rows, cleanup/failure,
negativeScope, `semanticName:null`, `geDrawObserved:false`.

Successful row keys:

```text
sample, entryPC, entryTicks, entryGPR, entrySP, entryRA, entryArgs{a0,a1,a2,a3},
E,C,P,N, entryStack, callerChain,
entry{context,state,node,queueEntry,descriptor,matrices,parents},
weapon{actor,sourceBase,metadata,drawTable,geometrySHA256,geometry,identityRaw},
resourcePrefix64,
resource{source190,source194,source198,header,table1Slot4,table1Record4,
         record192,prefix64,nestedList},
descriptorPath{offset,lists:[{role,count,list,definitions:[
  {ordinal,index,offset,type,mutableDataOffset,pointer,raw}]}]},
bucketSources{beforeHeads,beforeTails,staticModeTables,selectedTable1ByteA,rawTable1},
returned{pc,ticks,gpr,sp,ra,queueEntry,context,state,node,bucket,head,tail,
         oldHeadBefore,oldTailBefore,oldTailAfter,linkValidation},
classification, geDrawObserved, semanticName
```

`oldHeadBefore` and `oldTailBefore` are pointer values from the original arrays,
not raw-window objects. `oldTailAfter` is the actual 8-byte raw window (or null
for empty). `entryStack` is a raw-window object: its filename is
`entryStack.raw.file`. `weapon.geometry` and `identityRaw.*.raw` are byte sidecar
objects, preserving the established raw-identity shape. An unfinished row uses
top-level `inFlight.returnAttempt`, never `rows[].returned`.

## Offline validation and limits

The final VM/Mock suite contains86 scenarios: ten successful shapes (empty,
append, four descriptor routes, two parents, GPR35/36 and default no-input/
header compatibility variants with shared cases), nine bounded target-negative
cases, and67 fail-closed/code/ABI/relocation/queue/timeout/cleanup cases.
Coverage includes unrelocated D/list/definition pointers, all saved-return
words, mutable state checks, both new head/tail outcomes, actual oldTail.next,
queued external setup/return stops, BP add ACK timeout at either stage with
owned or foreign queued events, and stage timeout preserving incomplete output.

These are producer tests with a fake transport, not runtime observations.
Actual PPSSPP validation remains the parent's next step, followed by its
independent raw-byte auditor. Even a real successful capture will establish
enqueue identity and link writes only; type152/155 execution, matrix-mode
equations, geometry identity at GE PRIM, and the visual semantic remain open.
