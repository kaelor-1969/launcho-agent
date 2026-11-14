# Handoff

Goal: eight widget UX stages; modify frontend/ and JS/browser tests only. Docs only here; no Python/backend/content changes or push/PR/deploy.
Repository: C:/Users/smous/OneDrive/Desktop/LAUNCHO/launchy/launcho-agent/launcho-agent.
Branch: work/widget-person3-quality. Baseline 6ff86df9ab5c4f4f23556147f4f330cf7cfd07a3; stage 1 a72b5ea; read git log for current HEAD.
Stages 1, 2 and 3 locally checked. Production options/adapter and missing catalog previews remain external dependencies (dependencies.md).
Latest tests: session VM PASS; signup Chrome six form scenarios+all 23 previews/all recommendations PASS; HTTP 23/23; public Chrome render smoke23/23 PASS.
Reviewers approved source/excerpts only; no independent execution.
Stage3 complete and reviewed; next: stage4 browser-level offline and lost-response retry identity tests. Stage2 commit ce48fd7; current HEAD via git log.
Commands: node tests/widget_signup_browser.cjs; node tests/widget_sessions_browser.cjs; node --experimental-vm-modules tests/widget_session_test.cjs.
Main has filesystem/terminal/Git; reviewers receive concrete code/results and disclose own checks. No reliable cumulative token counter or root-session migration tool.
