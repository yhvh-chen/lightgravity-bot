# LG-032 CLOSE-AUDIT — STATUS

- phase: FINAL CLOSE (round ~20); PASS; see CLOSE-REPORT.md
- owner: agent:pi-lg032-close-audit (independent read-only close-audit owner; NOT product/driver/entry/formal author)
- worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-close-audit
- branch: qa/lg032-close-audit
- HEAD: 271fefb448a77fcd0f419acba7d26e024d3aa658 (base fix/lg032-cohort3-entry@271fefb)
- tracked diff: clean (only this CLOSE-AUDIT/** to be added)
- real provider this package: 0 (no SDK/tests/POST/runner executed)
- private originals: read-only, parsed necessary keys only; no raw content/headers/credential printed
- 032 status: NOT touched (not written); PM to decide done

## Verified so far (independent, read-only)

| fact | result |
|---|---|
| product tree HEAD:backend/lightgravity | 55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f == frozen == base == main |
| entry run_formal.py sha256 | e8340f90…90e2 == report |
| overlay mode_config.py sha256 | df565291…88bf == report |
| driver run_attempt.py sha256 | 503a807f…6208 == report |
| driver final_cohort_config.py sha256 | a04a8f30…a117 == report |
| cohort3 ledger count / lines / sha | {"count":84} / 84 / fef0bd52… (+ a266e2fd… jsonl) == report |
| per-attempt gen requests | 20+20+17+27 = 84 ≤ 192 |
| attempt order (timestamps) | s1A→s1B→s2A→s2B, each once |
| result.json shas (4) | match report §7.1 exactly; evidence==result bytes |
| delivered/ok/machine | 4/4 delivered; machine 5/5,5/5,7/7,7/7 exit0 |
| mode A off / B on | dispatcher congruent; lease_granted 0/3/0/3; s2A(after B)=off, 3 refs no selector |
| restored_off | true x4; final SETTINGS decentralized_claim_enabled=false |
| review | reviewer_kind=model, outcome=passed, unsubstantiated=0 x4; connection deepseek-v4-flash cred=True |
| reviewer teardown | status=done agent_closed proxy_stopped confirmed x4 |
| repair_rounds_spent | 0 x4; no recheck |
| accept binding | plan_hash present, evidence-present passed, idempotent confirmed, wrong target 409 |
| native sessions | 18 *.db @600 (3/6/3/6) |
| resource stop | members ready→released reason "run scheduling finished"; reviewer cleanup confirmed |
| old ledgers | cohort1 {"count":87} 609946be…; cohort2 {"count":19} be90a0f9… — preserved, not washed |
| COHORT3 branch product/driver/entry bytes | zero (only 2 report files added vs b634238) |
| old cohort2 entry sha | a7477753… unchanged |
| cost metadata (shared snapshot 21:24:34Z) | LG032 26 logs/1574 calls/in 1,678,454/out 517,978/cacheRead 124,136,832/est 9.728773; NOT bill |

## Arithmetic
- 032 real total = 106 (87+19) + 84 = 190 (cohort3 cap 192; known upper 298 not exceeded)
- A arm = 37 (20+17); B arm = 47 (20+27)
- SDK token/actual money: unknown (usage {"unknown":["usage"]}), not 0

## Additional verified
- native-sessions 18 db: real SDK trajectory tables; gen_metadata rows total 80 (content not printed)
- members ready->released; reviewer cleanup confirmed; secrets stored 700, no secret value in repo reports
- COHORT3 branch added only 2 report files vs b634238; old FAIL entry audit superseded by b634238 + R1 PASS
- cohort2 STOP report confirms 19 = single failed attempt; cohort2 remaining corrected to 173 (192-19) in addendum

## Next
- DONE: see CLOSE-REPORT.md. 032 status not written; PM to decide done.
