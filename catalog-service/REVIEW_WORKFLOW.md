# Review workflow API

All endpoints require `X-Admin-Token`. Existing itemized batches contain at most 100 items; the stricter bulk-assignment endpoint contains at most 50 IDs. Responses include a result for every selected pattern.

- `POST /api/v1/admin/reviews/batch-assign` assigns or reassigns draft patterns.
- `POST /api/v1/admin/reviews/bulk-assign` assigns one caller-filtered list of pattern IDs to one reviewer. It requires the admin token plus all four signed actor headers, rejects duplicate IDs, and is limited to 50 IDs.
- `POST /api/v1/admin/reviews/batch-decide` records `approved`, `rejected`, or `needs_more` decisions.
- `GET /api/v1/admin/reviews/tasks?assignee=...&state=...` lists current tasks.

Each mutation item requires a caller-generated `requestId`. Reusing the same ID with the same body returns the original result with `replayed: true`; reusing it with another body returns `idempotency_conflict` for that item.

`bulk-assign` uses one request ID for the whole selection, so a retry cannot silently add or remove IDs. Its only state transition is creation/reset of a `review_tasks` row to `assigned`; it cannot approve, alter publication fields, or publish a pattern. Missing and non-draft patterns are reported per item, and every actual assignment or reassignment is attributed to the verified actor in `audit_logs`.

Only the assigned reviewer identity may record a decision. An approval must have no issues; rejection and requests for more information require at least one issue. Decisions never modify rights facts and never publish content. Publishing remains a separate operation and now requires the persisted task state to be `approved`, in addition to rights and review-risk validation. A generic pattern PATCH cannot cross the publication boundary; use `/publish` and `/withdraw` so Catalog and AI stay coordinated.

Assignment, reassignment, and each decision are appended to the existing pattern audit log. Reviewer names are workflow attribution, while API authorization is still enforced by the current admin-token boundary; production role-based user authentication is a separate hardening step.
