export const REQUEST_ID_HEADER = "X-Request-ID";

const safeRequestId = /^[A-Za-z0-9._:-]{1,100}$/;

export function requestIdFrom(headers: Headers): string {
  const supplied = headers.get(REQUEST_ID_HEADER);
  return supplied && safeRequestId.test(supplied) ? supplied : crypto.randomUUID();
}

export function accessLog(fields: Record<string, unknown>) {
  console.log(JSON.stringify({ level: "info", service: "web", ...fields }));
}

export function errorLog(fields: Record<string, unknown>) {
  console.error(JSON.stringify({ level: "error", service: "web", ...fields }));
}
