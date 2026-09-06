type WindowEntry = { count: number; resetAt: number };

const windows = new Map<string, WindowEntry>();

export function studioClientKey(headers: Headers) {
  const forwarded = process.env.ADMIN_TRUST_PROXY === "true"
    ? headers.get("x-forwarded-for")?.split(",")[0]?.trim()
    : undefined;
  return forwarded || "direct";
}

export function checkStudioLimit(key: string, now = Date.now()) {
  const limit = Math.max(1, Number(process.env.STUDIO_REQUESTS_PER_MINUTE || 10));
  const current = windows.get(key);
  if (!current || current.resetAt <= now) {
    windows.set(key, { count: 1, resetAt: now + 60_000 });
    return { allowed: true, retryAfterSeconds: 0 };
  }
  if (current.count >= limit) {
    return { allowed: false, retryAfterSeconds: Math.max(1, Math.ceil((current.resetAt - now) / 1000)) };
  }
  current.count += 1;
  return { allowed: true, retryAfterSeconds: 0 };
}

export function resetStudioLimitsForTests() { windows.clear(); }
