# JJ Arena Frontend Architecture

## Canonical production path

Production browser assets are compiled during the build. Runtime request handling must never execute UI transforms.

1. `materialized_v1244/static/*` — immutable v1.24.4 source/rollback oracle.
2. `served_assets.build_all()` — frozen compatibility compiler. It applies the historical UX layers needed to reproduce the current UI.
3. `frontend_build_pipeline.py` — the only supported production compiler entrypoint. It orders all active post-build safety/governance stages and records them in `.jj_build/manifest.json`.
4. `.jj_build/*` — validated deployable browser bundle.
5. `app.py` — reads the validated bundle only; no request-time transform is allowed.

`build_served_assets.py` is deliberately a tiny command wrapper around `frontend_build_pipeline.main()`.

## Historical transforms

The phase-named modules (`player_ux_*`, hand-history visibility, clear-copy, subtractive redesign, etc.) are **compatibility compiler implementation details**, not independent production entrypoints. New features must not add another request-time/runtime patch layer. Prefer one of:

- edit the active product transform responsible for that surface;
- add a narrowly scoped post-build safety/governance stage to `frontend_build_pipeline.POST_BUILD_STAGES`;
- when enough historical transforms can be collapsed safely, replace compatibility stages only after final-bundle/browser parity tests pass.

## Golden-master rule

The final compiled bundle is the behavior contract. Refactors of the compiler must prove:

- deterministic output for identical source;
- final JavaScript syntax validity;
- required UI/browser regressions pass on PC and mobile;
- no runtime transform is introduced;
- route/API lifecycle assertions continue to pass.

The goal of consolidation is not to rewrite the UI. It is to make one build path authoritative while preserving the currently proven behavior.
