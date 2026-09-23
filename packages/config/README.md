# @mhvp/config

Shared tooling configuration for all JavaScript packages (section 17).

## Contents

| File | Purpose |
| --- | --- |
| `eslint.base.mjs` | shared ESLint 9 flat config |
| `tsconfig.base.json` | shared strict TypeScript settings |

## Contract

Apps and packages extend these files instead of duplicating settings. The package has no build
or test scripts; changes are verified by `make lint` and `make typecheck` across the workspace.
