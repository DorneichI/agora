# Architecture decisions

This file records *why* cross-cutting technical decisions were made, not just what they are.
For the operational rules Claude Code needs on every task, see the root [`CLAUDE.md`](../CLAUDE.md).

## Auth

Managed identity provider: [Clerk](https://clerk.com/), used across all three pieces, with
passkeys (Touch ID/Face ID/Windows Hello via WebAuthn) as a goal everywhere:

- **Backend**: verifies the JWT Clerk issues — no hand-rolled password storage/reset flows.
- **Web**: Clerk's official Next.js SDK directly. Passkeys are mature and documented here.
- **Mobile**: does **not** use `clerk_flutter` (Clerk's Flutter SDK is beta and
  community-maintained, not officially supported by Clerk, and has no documented passkey support).
  Instead, the app opens Clerk's hosted sign-in page in a **system-browser sheet**
  (`ASWebAuthenticationSession` on iOS, Chrome Custom Tabs on Android — via a package like
  `flutter_web_auth_2`), then receives the session back through a deep link. This works because a
  system-browser sheet is a real browser context with full WebAuthn support (unlike an embedded
  WebView, which doesn't support passkeys reliably) — so mobile gets the same passkey support as
  web without depending on Clerk's unsupported native mobile SDK. Exact redirect-URI/deep-link
  wiring (and possibly an iOS Associated Domains entitlement) is an implementation detail to work
  out and test when this is actually built.

## API contract between backend and clients

FastAPI auto-generates an OpenAPI schema. Both clients generate code from that schema rather than
hand-writing request/response types — the schema is the single source of truth:

- `web/` uses [openapi-typescript](https://openapi-ts.dev/) — types only, hand-written fetch calls.
- `mobile/` uses `openapi_generator` configured for **models only** (not its generated client) —
  same principle as web: generated types, hand-written calls (via `dio`/`http`).

See `backend/CLAUDE.md` for how the schema is exported, and `web/CLAUDE.md` / `mobile/CLAUDE.md`
for each side's codegen command.
