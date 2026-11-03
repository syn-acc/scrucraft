# Comprehensive API completion plan

The [original 40-item checklist](api-completion-checklist.md) remains the governing
scope: **10 checked, 30 open**, plus 13 separately open pack/mod/survival
requirements. Experimental deployment is progress, not comprehensive completion.
The [coverage matrix](api-coverage-matrix.md) records exact gaps and evidence.

## Current release boundary

Release 04 pairs SDK/gateway **0.3.0.dev2** with adapter **0.5.0-dev2**. It includes
bounded transport and recovery, the delayed-dig correction, reviewed mod ports,
fractional-ground/airborne navigation fixes and native dimension-completion
handling. The latter clears the transition latch that otherwise suppresses native
damage. Runs 10 and 11 verify the named navigation/damage regressions. MOD-08 train/contraption
drafts are excluded. The packaged release suite passes 190 tests; no complete
native or ten-body performance pass follows from that count.

Runs 07/08 supply specific native evidence, including delayed-dig guards,
container contention/reconciliation, reviewed powered workstations and clean SDK
examples. They also contain retained failures. Real enrollment and idle human
chat-stop delivery are separate evidence; neither proves an active full gameplay
journey. See [verification](verification.md) for build boundaries and results.

## Ordered remaining acceptance

1. **ACT-07; EXEC-02/03/04/06; SURV-02:** retain corrected delayed-dig regressions
   and finish independent stop/revoke/disconnect/dimension/death cases. Wait beyond
   original completion deadlines, account for every block/stack, and preserve
   explicit uncertain outcomes. Verify native damage after dimension completion;
   do not count the source fix as a survival pass.
2. **VERIFY-01; ACT-04/05/06; OBS-02/07:** verify release 04 physical navigation
   through fractional terrain and airborne starts, then all remaining terrain,
   held-input, entity and execution-state criteria. Preserve run 07's Enemy-marker
   classification proof and distinguish requested inputs from actual movement.
3. **ACT-08/10/13/14/15; OBS-05/06; MOD-01–10:** finish the documented installed-pack
   matrix: placement, native menus/item/fluid ports, power, processing metadata,
   probabilities, remainders, ownership and contention. Passing depot/press/mixer
   fixtures with supplied power do not prove an agent-built factory. Excluded
   train control remains open rather than being removed from scope.
4. **SDK-02/05; OBS-04; VERIFY-03/04:** finish uncertain-mutation recovery,
   stale-container/epoch handling, subscriber resync, private-message exclusion
   and real human stop during active work. Keep all 25-operation HTTP/WSS parity,
   no-replay and priority-stop regressions. SDK-01/04 remain checked on their
   linked onboarding and clean-install evidence; re-run relevant checks when
   source changes without adding unrelated performance gates to those items.
5. **VERIFY-02; SURV-01/02:** complete a finite end-to-end food, shelter, threat,
   damage/death/recovery and industrial journey on the installed pack. Identify
   all supplied infrastructure and measure native consumption, output and losses.
   The agent supplies task composition; no transport or SDK patches may be needed.
6. **VERIFY-05:** meet the original five-minute ten-body workload, fairness,
   tick-cost, latency/cadence and slow-consumer targets. Retain failed runs and
   outliers. The separate SDK-driver process shares the same 150% aggregate CPU
   cgroup; it corrects shared-interpreter measurement contention and does not
   change thresholds or itself establish a performance pass.
7. **VERIFY-06; SDK-05:** record final native results, exact artifact hashes,
   private-credential scans, paired deployment/rollback and post-deployment smoke
   checks. Publish truthful capabilities and remaining limits. Keep the release
   experimental until the complete checklist and additional requirements pass.

Every result must identify its source build and checklist criteria. Compilation,
a method existing or gateway acceptance cannot replace actual game outcomes.
Preserve historical measurements and failed fixtures; correct test assumptions
explicitly and rerun them rather than relabeling failures as passes.
