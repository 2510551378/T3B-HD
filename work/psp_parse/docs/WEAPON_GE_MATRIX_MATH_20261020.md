# Original matrix modes0/1 and VIEW: independent opcode replay

This verifier is offline. It imports neither the sampler nor its predictions, and does not connect to PPSSPP, run UE, alter Content, or assign gun/muzzle semantics. Its inputs are the fixed original module and retained runtime raw windows. Original module base is `08804000`; SHA256 is `b5fc590366fc610f2cdd60104a4a28851bacd402c4600a4c296776e1dea0869f`.

## Static evidence and register interpretation

Full original `08b66bb4/3b4`, selected helper `08b6589c/104`, and `08bbb8d4/5c` are independently extracted and hashed in `out/WEAPON_GE_MATRIX_MATH_20261020`. The two previously frozen full functions are compared byte-for-byte against the fixed module. The verifier interprets individual original opcodes, branch delay slots, actual physical VFPU register indices, and original memory loads/stores. Unknown opcodes, unknown control flow, nonfinite float arithmetic, uninitialized registers, contradictory windows and unretained reads fail closed.

The pinned official v1.20.4 VFPU sources in `raw/ppsspp_v1.20.4_vfpu_reference` define ReadMatrix/ReadVector indexing, transposition and the non-fused interpreter arithmetic order. Three additional official register API sources and their hashes are retained under the new report's `reference` directory:

- [CPUCoreSubscriber.cpp](https://raw.githubusercontent.com/hrydgard/ppsspp/v1.20.4/Core/Debugger/WebSocket/CPUCoreSubscriber.cpp): full-register response schema and raw uintValues.
- [MIPSDebugInterface.h](https://raw.githubusercontent.com/hrydgard/ppsspp/v1.20.4/Core/MIPS/MIPSDebugInterface.h): GPR/FPU/VFPU category sizes and raw register access.
- [MIPSDebugInterface.cpp](https://raw.githubusercontent.com/hrydgard/ppsspp/v1.20.4/Core/MIPS/MIPSDebugInterface.cpp): register names.

The actual `cpu.getAllRegs` response is independently decoded by category names, IDs, registerNames and uintValues. It contains GPR35 (32 plus PC/HI/LO), FPU32 and VFPU128 **data** registers. These categories do not expose VFPU S/T/D prefix controls. The producer's `f12Decoded=false` is not evidence that f12 is missing: raw FPU uintValues contain it.

Full runtime original/decoded code sidecars must each match the fixed module. The physical memory view may contain PPSSPP `68xxxxxx` execution-cache replacements or BREAK; those are retained/checked as instrumentation bytes, never interpreted as original guest code. This verifier uses both restored original views; the parent capture auditor remains responsible for their acquisition/RPC lifecycle provenance.

## Equations recovered from instructions

Matrices are 16 little-endian float32 values in column-major storage; translation is the fourth column at byte `30`. Let I be the original input, L the effective parent (`P+60` when `node+1c==0`, otherwise `[nodeParent+54]`), G the matrix pointed to by global `08c3b58c`, and s the actual scalar f12. Let D be the three original P+30 components.

For mode1, original `08b6589c`:

1. It compares f12 with exactly 1 using COP1. If different, each of the first three input basis columns is multiplied by s using separate float32 rounding.
2. It multiplies each resulting column by its corresponding P+30 component, again rounding separately.
3. The output basis is G.basis multiplied by those columns. The `vmmul.t` VS register has the transpose bit set; reversing multiplication order is incorrect.
4. The output fourth column is independently computed by `vtfm4.q` as L times the full original I fourth column, including original w.
5. The first three output bottom-row elements are forced to +0 by three `vzero.s` operations. The fourth w comes from the preceding transformation.

This is not a generic L*I 4x4 multiply. G's translation is not used by the basis operation. Scale s must not be fitted from output or silently set to 1.

The wrapper subtracts one from original unsigned mode before dispatch. Original modes 1,2,3,4,5 select `6589c`, `659a0`, `6589c` plus translation handling, `6589c` plus two translation transforms, and `65ac4` respectively. Original mode6 uses `657f8` then subtracts global translation; other unsigned modes use `657f8`. The verifier supports observed modes0/1; dispatch knowledge is not validation of the other equations or branches. Mode0 separately scales all four components of each of the first three input columns when f12!=1, then computes the full4x4 L*I operation through `657f8/a4`. Translation is not scaled by f12.

For `08bbb8d4`, let V be global `08c3b588` and H the actual retained handler matrix. Original `F004A088` computes full 4x4 V*H and stores all16 values before passing kind1 to the matrix writer. No affine row is discarded here. Handler155 may alter translation between matrix return and VIEW, so the verifier uses actual retained H and separately records whether it still equals the matrix return.

For the supported mode1 handler152/155 path, final helper `vzero.s` consumes and resets prefixes, and the handler continuation before VIEW has no VFPU/prefix operations (155 may have scalar COP1 arithmetic). Default prefixes for the VIEW compose are therefore supported by that static path. Matrix-helper **entry** prefix controls remain unobserved.

## Precision and claim boundary

The replay rounds every multiplication and addition to float32 in pinned non-fused interpreter order. It reports raw output word/bit differences and maximum numeric error; zero numeric error with a signed-zero bit difference still fails bit equality. It never converts a tolerance to equivalence. PPSSPP JIT, MoreAccurateVMMUL, subnormal behavior or other prefix state may differ outside actually tested samples.

The first retained actual `slot0_weapon_ge_emit_fire6_component_v2` in-flight matrix stage has mode1, parent0 and **f12 raw bits 42000000 = 32.0**. Replaying its68 original instructions matches all16 returned float32 values with 0 differing bits and all32 returned GPR values exactly. That capture later failed its VIEW DL alias gate; this single valid retained stage is not a complete capture or CPU-emission success. `--include-inflight` is required to inspect it. No actual VIEW input was available in v2.

`matrix_math_verification.json` is authoritative for the current complete/partial input captures and per-stage coverage. `actual_sample_outputs_bit_exact` describes actual compared raw outputs under the stated arithmetic model. `actual_runtime_math_verified` and unconditional all-mode equivalence remain false because entry prefix controls are unobserved and other modes are unsupported. There is no exact-weapon, gun, muzzle, GE execution, or pixel-equivalence conclusion.

Thirteen synthetic checks exercise original opcodes with nonsymmetric/noncommuting matrices at scale1 and .625, full non-affine mode0 multiplication, VIEW multiplication order, malformed/unsupported input rejection, and signed-zero bit differences despite zero numeric error. They are labeled `runtime_evidence=false`; they do not substitute for actual captures.

The complete v3 capture is independently replayed in `out/WEAPON_GE_MATRIX_MATH_20261020/actual_v3` and again by root in `root_replay_v3`. Six matrix stages and six VIEW stages compare192 actualfloat32 values with0bit differences; all32 returned GPRs also match for each matrix stage. Fourtype152/mode1 samples have f12=32; twotype155/mode0 samples have f12=138.8235321044922/35.73048782348633. Same-capture full6589c identity is present for mode1; full657f8 runtime identity is absent for mode0, so those two computations use only the fixed original module's static helper. The report explicitly keeps `all_selected_helpers_full_runtime_code_identity_present=false` and unobserved-prefix limits. This does not reclassify the earlier failed v2 capture as complete.

## Reproduce

```powershell
python -X utf8 .\work\psp_parse\tools\verify_weapon_ge_matrix_math.py

python -X utf8 .\work\psp_parse\tools\verify_weapon_ge_matrix_math.py `
  --capture .\work\psp_parse\out\AYA_BONE_GE_ACTIONS\slot0_weapon_ge_emit_fire6_component_v2\marker_ge_emit.json `
  --include-inflight
```

Use repeated `--capture` arguments to put several explicitly selected captures in one report. `--out` chooses a new dedicated report directory. Complete rows must contain both actual matrix-return output and actual VIEW input. Partial captures retain their failure/inFlight status in the report rather than being relabeled complete. No game process is started by any command above.
