# Person 1 — Sepehr

Baseline: `b0861164feae11ba7caaf1ce93bba61b45e94eb6`, clean main; branch `work/widget-person1-recovery`. No AGENTS.md found in repository/ancestors. Only frontend, JS tests and task documentation may change. Local commits only; no push, PR, merge or deployment.

| Stage | Acceptance | Status |
| --- | --- | --- |
| 1 | Audit actual session/options/review/confirm/status contract | Complete locally |
| 2 | Refresh reads authoritative state; never automatically confirms; storage failures safe | Complete locally with opt-in; unknown-operation reconciliation dependent |
| 3 | Offline/reconnect and duplicate activation never automatically mutate | Complete controlled-browser scope; server guarantees external |
| 4 | Existing questions/options stay separate from confirmation; stale results ignored | Complete controlled local UI; production choices/questions dependent |
| 5 | Preserve documented dimensions; check desktop/portrait/landscape/short viewport | Complete emulated scope; approved reference and physical devices dependent |
| 6 | Idempotent loader, authenticated messages, sample host and installation | Complete local sample; actual Launcho installation external |
| 7 | Real browser fixtures, request identity/count assertions, visual evidence | Pending |
| 8 | Final regression, dependencies and handoff | Pending |

Each stage receives source/diff self-review, a fresh independent reviewer, actual relevant tests and a scoped nonempty local commit. Existing work is retained. Controlled fixtures do not establish production compatibility.
