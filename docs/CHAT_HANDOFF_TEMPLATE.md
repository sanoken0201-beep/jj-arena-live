# JJ Arena Chat Handoff Template

Use this when a ChatGPT development chat is nearing its limit or work is intentionally moved to a new chat.

The handoff should be short enough that the next chat can read it quickly. Do not copy the full conversation.

---

# JJ Arena Handoff — <topic> — <YYYY-MM-DD>

## Scope of this chat

What this chat was responsible for.

## Current repository state

- Repository: `sanoken0201-beep/jj-arena-live`
- Working branch / PR:
- Relevant latest commit SHA:
- Production `main` SHA if verified:
- Render deployed SHA if verified:

Do not guess unknown SHAs; mark them `not verified`.

## Completed in this chat

Only list changes that are actually completed/verified.

## Current verified behavior

Record the important behavior that the next chat must preserve.

## Unfinished work

List remaining tasks in execution order. Distinguish:
- not started
- partially implemented
- implemented but not verified
- blocked

## Important constraints

Include only constraints relevant to the next work, such as:
- do not directly edit `materialized_v1244/`;
- preserve production DB/data;
- preserve poker timing/privacy/point semantics;
- avoid reviving retired product surfaces.

## Tests / CI

- Tests added or changed:
- Latest CI status:
- Known failures:
- Production smoke checks performed:

## Production / database impact

State explicitly whether the work changed:
- database schema/data;
- points/rankings;
- authentication/session behavior;
- Render settings/environment;
- online poker rules/timing;
- browser/PWA behavior.

If none, say `None`.

## Durable decisions made

List only new decisions that should be added to `docs/DECISION_LOG.md`. If already recorded there, reference the decision ID instead of repeating the reasoning.

## Documentation updates required

Identify whether the completed work requires updates to:
- `docs/PROJECT_STATE.md`
- `docs/DECISION_LOG.md`
- `ARCHITECTURE_STATUS.md`
- `OPERATIONS.md`

## First action for the next chat

Give one concrete first verification/action. Example:

`Read docs/PROJECT_STATE.md, inspect PR #XX and current main/Render SHA, then continue the unfinished Sit&Go point settlement work.`

---

## Rules for the next chat

Before continuing work, the next chat should:
1. read `docs/PROJECT_STATE.md`;
2. read this handoff;
3. verify current repository/runtime state instead of assuming the old chat is still accurate;
4. consult `OPERATIONS.md` / `ARCHITECTURE_STATUS.md` when the task touches those domains;
5. update canonical documentation when a durable project fact or decision changes.