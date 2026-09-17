# JJ Arena — Chat Handoff Template

Use this when a ChatGPT development chat is becoming long, switching domains or approaching its conversation limit.

The goal is **not** to summarize the full conversation. The goal is to let a new chat resume safely with minimal context.

Before creating the handoff:

1. Promote durable current-state changes into `docs/PROJECT_STATE.md`.
2. Promote durable design/product decisions into `docs/DECISION_LOG.md`.
3. Ensure code/tests/docs that were changed are committed or clearly identified as uncommitted.
4. Record the exact branch/PR/commit and production status below.

---

# JJ Arena Chat Handoff

## 1. Scope of the previous chat

Domain:

- [ ] Production / Render / release safety
- [ ] Ring poker engine
- [ ] Ring UI/UX
- [ ] Sit&Go
- [ ] Official points / ranking
- [ ] Admin
- [ ] Security / auth
- [ ] Performance
- [ ] Browser/PWA
- [ ] Other: `...`

Primary goal of the session:

`...`

## 2. Repository state

Repository: `sanoken0201-beep/jj-arena-live`

Branch: `...`

Latest relevant commit SHA: `...`

PR: `#...` / none

PR status: `open / merged / closed / none`

Required CI status: `passing / failing / pending / not checked`

Important changed files:

- `...`

## 3. Production state

Was production changed in this chat? `yes / no`

If yes:

- deployed commit: `...`
- Render deploy status: `...`
- production smoke verification performed: `yes / no`
- DB migration performed: `yes / no`
- rollback point: `...`

Do **not** place secrets, PINs, credentials or session material here.

## 4. Completed work

Only list work that is actually complete and reflected in code/docs/tests or verified production.

- `...`

## 5. Unfinished work

List exact remaining work. Distinguish implementation from investigation.

- `...`

## 6. Known problems / risks

Include only issues that remain relevant.

- `...`

## 7. Decisions made in this chat

For every durable decision, either point to the `DECISION_LOG.md` entry or state that it still needs promotion.

- `D-... — ...`

Unpromoted decision requiring follow-up:

- `...`

## 8. Tests and verification

Tests run:

- `...`

Tests not yet run but required before merge/release:

- `...`

Manual verification performed:

- `...`

## 9. Next-chat first actions

The next chat should:

1. Read `docs/PROJECT_STATE.md`.
2. Read `ARCHITECTURE_STATUS.md`.
3. Read `docs/DECISION_LOG.md`.
4. Read the domain-specific document relevant to this task.
5. Inspect current `main`, branch/PR and production state rather than assuming this handoff is still current.
6. Then continue with: `...`

## 10. Context that can be discarded

Record historical or exploratory material that does **not** need to move to the next chat.

- failed approaches already reverted: `...`
- obsolete implementation detail: `...`
- resolved debugging trail: `...`

---

## Minimal prompt for the new ChatGPT chat

Copy only this short prompt plus the handoff if needed:

> Continue JJ Arena development in `sanoken0201-beep/jj-arena-live`. First read `docs/PROJECT_STATE.md`, `ARCHITECTURE_STATUS.md`, `docs/DECISION_LOG.md`, and the relevant domain documentation. Then inspect the current branch/PR/main and production state as needed. Treat GitHub/current production as authoritative over old chat history. The previous-chat handoff is attached below.

After the new chat has verified the repository state, the old chat no longer needs to remain part of the active development workflow.