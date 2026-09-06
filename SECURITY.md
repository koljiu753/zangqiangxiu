# Security baseline

This repository is configured for a single-host deployment behind a trusted reverse proxy.

## Container controls

- `catalog`, `ai`, and `web` run as unprivileged users defined by their Dockerfiles.
- Their root filesystems are read-only, all Linux capabilities are dropped, privilege escalation is disabled, and PID counts are limited.
- A small `noexec,nosuid` temporary filesystem is mounted at `/tmp`; the AI cache is the only persistent application write path.
- Host ports bind to `127.0.0.1`. Put TLS and any public exposure at a reverse proxy; do not change bindings to `0.0.0.0` without firewall and authentication controls.
- Docker JSON logs are size-limited by Compose to prevent unbounded disk consumption.

PostgreSQL and MinIO retain their upstream entrypoints because they need to initialize and repair volume ownership. Keep their images updated and restrict access to trusted operators.

## Credentials

Run `scripts/init-compose-env.ps1` to generate a local `.env`. Never commit `.env` or copy example placeholder values into production.

The AI service uses `AI_S3_ACCESS_KEY` and `AI_S3_SECRET_KEY`. Catalog uses a separate `CATALOG_S3_ACCESS_KEY` identity restricted to its evidence prefix; neither service receives MinIO root credentials. Evidence uploads accept only PDF/JPEG/PNG after extension, declared MIME, magic-byte and size validation, and Catalog computes the stored SHA-256 itself. Evidence downloads remain behind admin authorization and are never exposed by the public API. Rotate service identities separately after suspected exposure.

Environment variables are visible to Docker administrators. For shared or production infrastructure, inject credentials from the platform secret manager and restrict Docker daemon access.

The self-hosted admin boundary rejects passwords shorter than 12 characters, session secrets shorter than 32 characters, placeholder secrets, and unknown roles. Roles fail closed to `reviewer`; only `publisher` may publish. Signed sessions last eight hours, use HttpOnly/SameSite=Strict cookies, and every state-changing Server Action requires a session-bound CSRF token. Reviewer and rights-verifier identities are derived from the signed session and never accepted from submitted form fields.

The login endpoint blocks after five failed attempts for 15 minutes and rejects cross-site browser submissions. This in-process limiter is suitable for the provided single-web-container deployment. Keep `ADMIN_TRUST_PROXY=false` unless a trusted reverse proxy overwrites `X-Forwarded-For`; for multiple web replicas, enforce a shared limiter at that proxy as well.

Set `AUTH_COOKIE_SECURE=true` whenever the public site is served over HTTPS. Keep `ADMIN_ALLOW_BASIC_AUTH=false`. For multi-user production, replace the single local account with an enterprise identity provider while preserving the reviewer/publisher authorization boundary.

`CATALOG_ADMIN_TOKEN` must be a random value of at least 32 characters in production and is compared in constant time. It is server-to-server only and must never use a `NEXT_PUBLIC_` name or be sent to the browser.

Authenticated Web mutations also carry `X-Admin-Actor`, a Unix timestamp, and `X-Request-ID`, protected by an HMAC-SHA256 signature using the separate `CATALOG_ACTOR_SIGNING_SECRET`. Catalog accepts only complete signatures within a five-minute window and records the verified actor in audit logs. Requests that intentionally use only `CATALOG_ADMIN_TOKEN` (maintenance scripts) remain compatible and are attributed to `service-admin`; arbitrary actor headers without a valid signature are rejected.

## Release checks

Before a release:

1. Run application tests and `npm audit --omit=dev`.
2. Build images with `docker compose build --pull` to receive patched base-image layers.
3. Run `docker compose config` and confirm no host port uses a wildcard address.
4. Scan built images with the registry or deployment platform's vulnerability scanner.
5. Verify backups and restore procedures before changing database or object-storage versions.

The image tags are intentionally version-specific but not digest-pinned so routine security updates can be pulled. For reproducible regulated releases, record and deploy reviewed image digests.
