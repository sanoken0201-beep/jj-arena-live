# JJ Arena Documentation Ownership

This directory exists to keep long-running development independent from any single ChatGPT conversation.

## Canonical documents

### `PROJECT_STATE.md`
Compact current project state for cross-chat continuity.

Use it to answer: **What is true now?**

Keep it current when durable architecture, production topology, invariants, or product direction changes.

### `DECISION_LOG.md`
Durable architectural/product reasoning.

Use it to answer: **Why was this decision made?**

Do not turn it into a release changelog.

### `CHAT_HANDOFF_TEMPLATE.md`
Template for transferring unfinished work from one long ChatGPT conversation to the next.

Use it to answer: **What does the next chat need to continue safely?**

Handoffs are temporary operational context. Once work is completed and durable facts/decisions are incorporated into canonical docs, old handoffs and old chats are no longer required as the primary source of truth.

## Existing root documents

These remain authoritative for their own domains:

- `../OPERATIONS.md` — production operations, release procedure, recovery, security and integrity rules.
- `../ARCHITECTURE_STATUS.md` — active / compatibility-only / retired surface classification and current architectural ownership.

`PROJECT_STATE.md` intentionally summarizes but does not replace those detailed documents.

## Source precedence

When sources disagree, verify rather than averaging old and new information.

1. current verified production behavior and current code/configuration
2. `OPERATIONS.md`
3. `ARCHITECTURE_STATUS.md`
4. `docs/PROJECT_STATE.md`
5. `docs/DECISION_LOG.md`
6. latest relevant handoff
7. historical chat messages

## ChatGPT development protocol

For a new JJ Arena development chat:

1. Read `docs/PROJECT_STATE.md` first.
2. Read the latest relevant handoff if unfinished work was transferred.
3. Read `OPERATIONS.md` / `ARCHITECTURE_STATUS.md` when relevant.
4. Verify current branch/PR/main/Render state before making assumptions.
5. Work in a focused branch/PR rather than using chat history as a substitute for repository state.
6. Update canonical documentation whenever a durable fact or decision changes.
7. Before a chat reaches its limit, produce a compact handoff using the template.

This protocol deliberately allows old development chats to be archived or deleted later without making the project unrecoverable.