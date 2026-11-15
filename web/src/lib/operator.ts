/**
 * Operator login. The password goes to the bridge over HTTPS and comes back as an HttpOnly
 * cookie the page never sees; the bridge decides who may control the station (hello.operator).
 */

export type LoginResult = { ok: true } | { ok: false; message: string };

async function post(path: string, body?: unknown): Promise<Response> {
  return fetch(path, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'content-type': 'application/json' },
    body: body === undefined ? null : JSON.stringify(body),
  });
}

export async function operatorLogin(password: string): Promise<LoginResult> {
  try {
    const res = await post('/api/operator/login', { password });
    if (res.ok) return { ok: true };
    if (res.status === 401) return { ok: false, message: 'Wrong password.' };
    if (res.status === 429) {
      const wait = Number(res.headers.get('retry-after'));
      const mins = Number.isFinite(wait) && wait > 0 ? Math.ceil(wait / 60) : null;
      return {
        ok: false,
        message: `Too many attempts.${mins ? ` Try again in about ${String(mins)} min.` : ''}`,
      };
    }
    return { ok: false, message: `Login failed (${String(res.status)}).` };
  } catch {
    return { ok: false, message: 'Could not reach the bridge.' };
  }
}

export async function operatorLogout(): Promise<void> {
  try {
    await post('/api/operator/logout');
  } catch {
    /* the cookie expires on its own */
  }
}
