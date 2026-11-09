import { afterEach, describe, expect, it, vi } from 'vitest';
import { operatorLogin, operatorLogout } from '../../src/lib/operator';

afterEach(() => {
  vi.unstubAllGlobals();
});

function stubFetch(res: Response | Error): ReturnType<typeof vi.fn> {
  const fn = vi.fn(() => (res instanceof Error ? Promise.reject(res) : Promise.resolve(res)));
  vi.stubGlobal('fetch', fn);
  return fn;
}

describe('operatorLogin', () => {
  it('posts the password same-origin and reports success', async () => {
    const fn = stubFetch(new Response('{}', { status: 200 }));
    expect(await operatorLogin('hunter2 hunter2')).toEqual({ ok: true });
    const [url, init] = fn.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/api/operator/login');
    expect(init.method).toBe('POST');
    expect(init.credentials).toBe('same-origin');
    expect(init.body).toBe('{"password":"hunter2 hunter2"}');
  });

  it('explains a wrong password, a lockout and a dead bridge', async () => {
    stubFetch(new Response('{}', { status: 401 }));
    expect(await operatorLogin('x')).toEqual({ ok: false, message: 'Wrong password.' });
    stubFetch(new Response('{}', { status: 429, headers: { 'retry-after': '600' } }));
    const locked = await operatorLogin('x');
    expect(locked.ok).toBe(false);
    if (!locked.ok) expect(locked.message).toContain('10 min');
    stubFetch(new Error('offline'));
    expect(await operatorLogin('x')).toEqual({ ok: false, message: 'Could not reach the bridge.' });
  });

  it('never throws on logout', async () => {
    stubFetch(new Error('offline'));
    await expect(operatorLogout()).resolves.toBeUndefined();
  });
});
