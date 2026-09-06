# Review workflow API

Read endpoints require `X-Admin-Token`. Every review mutation also requires all four signed actor headers (`X-Admin-Actor`, `X-Admin-Timestamp`, `X-Admin-Signature`, and `X-Request-ID`), so an unsigned token holder cannot assign or decide reviews. Existing itemized batches contain at most 100 items; the stricter bulk-assignment endpoint contains at most 50 IDs. Responses include a result for every selected pattern.

- `POST /api/v1/admin/reviews/batch-assign` assigns or reassigns draft patterns.
- `POST /api/v1/admin/reviews/bulk-assign` assigns one caller-filtered list of pattern IDs to one reviewer. It rejects duplicate IDs and is limited to 50 IDs.
- `POST /api/v1/admin/reviews/batch-decide` records `approved`, `rejected`, or `needs_more` decisions.
- `GET /api/v1/admin/reviews/tasks?assignee=...&state=...` lists current tasks.

Each mutation item requires a caller-generated `requestId`. Reusing the same ID with the same body returns the original result with `replayed: true`; reusing it with another body returns `idempotency_conflict` for that item.

`bulk-assign` uses one request ID for the whole selection, so a retry cannot silently add or remove IDs. Its only state transition is creation/reset of a `review_tasks` row to `assigned`; it cannot approve, alter publication fields, or publish a pattern. Missing and non-draft patterns are reported per item, and every actual assignment or reassignment is attributed to the verified actor in `audit_logs`.

Only the assigned reviewer identity may record a decision. The request `decidedBy` value must exactly match the cryptographically verified actor; the verified actor is persisted in both the review task/pattern and audit log. An approval must have no issues; rejection and requests for more information require at least one issue. Decisions never modify rights facts and never publish content. Publishing remains a separate operation and now requires the persisted task state to be `approved`, in addition to rights and review-risk validation. A generic pattern PATCH cannot cross the publication boundary; use `/publish` and `/withdraw` so Catalog and AI stay coordinated.

Assignment, reassignment, and each decision are appended to the existing pattern audit log using the verified actor. The Web server signs these requests after authenticating the current administrator; production role-based user authentication remains a separate hardening step.
