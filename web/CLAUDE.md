# web/CLAUDE.md

Next.js-specific guidance for Claude Code. See the root [`CLAUDE.md`](../CLAUDE.md) for
cross-cutting conventions (git, environments, secrets) and [`docs/architecture.md`](../docs/architecture.md)
for the _why_ behind auth and the API contract.

## Stack

- Next.js, **App Router** (not Pages Router).
- TypeScript.
- ESLint (`eslint-config-next`) + Prettier (`eslint-config-prettier` disables ESLint's
  stylistic rules so the two tools don't fight).
- Styling approach not decided yet — deliberately left as plain CSS Modules from the default
  scaffold. Don't add Tailwind or a component library without that being an explicit decision.
- Vitest + React Testing Library for unit/component tests.
- Playwright for e2e tests (`e2e/` directory).
- npm for package management.

## Running locally

Via Docker Compose from the repo root (bind-mounts this directory, `next dev` picks up edits
immediately — no rebuild needed unless `package.json`/`package-lock.json` changes):

```bash
docker compose up web
```

Serves at `http://localhost:3000`.

## Commands

Run from inside `web/` (locally with `npm`, or via `docker compose exec web <cmd>`):

```bash
npm run lint          # ESLint
npm run typecheck     # next typegen && tsc --noEmit (regenerates Next.js route types first)
npm run format:check  # Prettier check (drop --check / use `npm run format` to auto-fix)
npm run test          # Vitest (unit/component)
npm run test:e2e      # Playwright (e2e) — starts its own dev server automatically
```

## Docker uses Webpack, not Turbopack

`next dev`'s default bundler (Turbopack) has no native binding for `linux/arm64` yet — only a
WASM fallback, which doesn't support Turbopack at all (hard error, dev server won't start). This
only bites inside the Docker container; native Apple Silicon (macOS `darwin/arm64`) has Turbopack
support, so running `npm run dev` directly on the host is unaffected. The container's `Dockerfile`
CMD passes `--webpack` to work around this — don't change that back to plain `next dev` for the
Docker path. You may still see harmless `swc-linux-arm64-*, but it was not installed` warnings
from Next.js in the container logs; those are about SWC's native minifier falling back to WASM,
not the same issue, and don't stop the server from serving pages.

## A quirk worth knowing: `next dev` rewrites this file

This Next.js version auto-regenerates an AI-agent instruction block (pointing at
`node_modules/next/dist/docs/`) every time `next dev` runs — normally into a separate
`AGENTS.md`, imported from the top of this file via `@AGENTS.md`. That import line has been
deliberately removed, which means `next dev` now appends the block directly into _this_ file
instead. If you see a `<!-- BEGIN:nextjs-agent-rules -->` block appended below after running
`next dev` (including indirectly, e.g. via `npm run test:e2e`), that's expected — just delete
it. There's no way found so far to suppress it without reinstating the `@AGENTS.md` import.
