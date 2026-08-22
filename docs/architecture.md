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

## Soft delete

Every backend table soft-deletes: rows are never physically removed, only marked with a
`deleted_at` timestamp (`NULL` = active, non-null = deleted). This is built once, generically, in
`backend/app/db/soft_delete.py`, so every model gets the behavior for free instead of every
developer remembering to filter manually.

- **`SoftDeleteMixin`** (a `SQLModel` mixin) provides `id`, `created_at`, `updated_at`, and
  `deleted_at`. A model opts in with `class Widget(SoftDeleteMixin, table=True): ...`.
- **Read filtering** — a global SQLAlchemy `do_orm_execute` event listener (registered on
  `sqlalchemy.orm.Session`, which also covers `AsyncSession` since the asyncio extension executes
  ORM-level work through the sync `Session` it wraps internally) adds a `deleted_at IS NULL` filter
  to every SELECT against a `SoftDeleteMixin` model, via `with_loader_criteria`. It's applied per
  concrete mapped class (not by passing the mixin directly to `with_loader_criteria`) because a
  `table=False` mixin has no real SQLAlchemy-comparable `deleted_at` attribute of its own — only
  its `table=True` subclasses do. A query opts out of the filter with
  `.execution_options(include_deleted=True)`.
- **Delete rewriting** — a global `before_flush` event listener intercepts any pending
  `session.delete(obj)` on a `SoftDeleteMixin` instance: it removes the object from the session's
  pending-delete set and sets `obj.deleted_at = now()` instead, so the flush emits an `UPDATE`
  rather than a `DELETE`. Callers never need a separate "soft delete" method — `session.delete()`
  is always safe to call.
- **Partial unique indexes, not plain unique constraints** — any uniqueness rule on a
  soft-deletable table must be a **partial unique index** scoped to active rows:

  ```python
  __table_args__ = (
      Index(
          "ix_widget_name_active_unique",
          "name",
          unique=True,
          postgresql_where=text("deleted_at IS NULL"),
      ),
  )
  ```

  A plain unique constraint would keep counting soft-deleted rows, permanently blocking reuse of
  that value (e.g. re-registering an email, rejoining a league after leaving it). Scoping the index
  to `WHERE deleted_at IS NULL` lets a new active row reuse a value that only a deleted row holds.

  **Hand-check this on every migration**: Alembic's `--autogenerate` doesn't reliably detect
  `postgresql_where`, so a generated migration for a soft-deletable table's unique index needs a
  manual review to confirm the partial-index clause made it into the migration script.

## API contract between backend and clients

FastAPI auto-generates an OpenAPI schema. Both clients generate code from that schema rather than
hand-writing request/response types — the schema is the single source of truth:

- `web/` uses [openapi-typescript](https://openapi-ts.dev/) — types only, hand-written fetch calls.
- `mobile/` uses `openapi_generator` configured for **models only** (not its generated client) —
  same principle as web: generated types, hand-written calls (via `dio`/`http`).

See `backend/CLAUDE.md` for how the schema is exported, and `web/CLAUDE.md` / `mobile/CLAUDE.md`
for each side's codegen command.
