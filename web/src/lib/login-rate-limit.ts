type Entry = { failures: number; resetAt: number };

const attempts = new Map<string, Entry>();
const WINDOW_MS = 15 * 60 * 1000;
const MAX_FAILURES = 5;

export function loginClientKey(headers: Headers, username: string) {
  const trustProxy = process.env.ADMIN_TRUST_PROXY === "true";
  const forwarded = trustProxy ? headers.get("x-forwarded-for")?.split(",")[0]?.trim() : null;
  return `${forwarded || "direct"}:${username.trim().toLowerCase().slice(0, 128)}`;
}

export function checkLoginLimit(key: string, now = Date.now()) {
  const entry = attempts.get(key);
  if (!entry || entry.resetAt <= now) { if (entry) attempts.delete(key); return { allowed: true, retryAfterSeconds: 0 }; }
  return { allowed: entry.failures < MAX_FAILURES, retryAfterSeconds: Math.max(1, Math.ceil((entry.resetAt - now) / 1000)) };
}

export function recordLoginFailure(key: string, now = Date.now()) {
  const current = attempts.get(key);
  const entry = !current || current.resetAt <= now ? { failures: 1, resetAt: now + WINDOW_MS } : { ...current, failures: current.failures + 1 };
  attempts.set(key, entry);
  return checkLoginLimit(key, now);
}

export function clearLoginFailures(key: string) { attempts.delete(key); }
export function resetLoginLimitsForTests() { attempts.clear(); }
