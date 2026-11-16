const messages = Object.freeze({
  invalid_request: 'Invalid provider request.',
  authentication_unavailable: 'Access token unavailable.',
  authentication_failed: 'Provider authentication failed.',
  permission_denied: 'Provider permission denied.',
  rate_limited: 'Provider rate limit reached.',
  transport_unavailable: 'Caller transport unavailable.',
  schema_unsupported: 'Provider schema unsupported.',
  response_invalid: 'Invalid provider response.',
  deadline_exceeded: 'Provider deadline exceeded.',
  cancelled: 'Provider request cancelled.'
});

export class MeetupProviderError extends Error {
  constructor(code) {
    const safe = typeof code === 'string' && Object.hasOwn(messages, code) ? code : 'response_invalid';
    super(messages[safe]);
    this.name = 'MeetupProviderError';
    this.code = safe;
  }
}
export function providerErrorCode(error, fallback) {
  try {
    if (error instanceof MeetupProviderError) {
      const code = error.code;
      if (typeof code === 'string' && Object.hasOwn(messages, code)) return code;
    }
  } catch {
    // Callback exceptions may be proxies or have throwing accessors.
  }
  return fallback;
}

export function createGraphql({
  fetchImpl, tokenSupplier, clock = Date.now, timeoutMs = 15000, maxResponseBytes = 1024 * 1024
} = {}) {
  if (!Number.isInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 15000
    || !Number.isInteger(maxResponseBytes) || maxResponseBytes < 1
    || maxResponseBytes > 16 * 1024 * 1024) throw new MeetupProviderError('invalid_request');
  return async (query, variables = {}, { signal, deadline } = {}) => {
    if (typeof fetchImpl !== 'function') throw new MeetupProviderError('transport_unavailable');
    if (signal !== undefined && !(signal instanceof AbortSignal)) throw new MeetupProviderError('invalid_request');
    if (deadline !== undefined && !Number.isFinite(deadline)) throw new MeetupProviderError('invalid_request');
    if (signal?.aborted) throw new MeetupProviderError('cancelled');
    let remaining, endsAt;
    try {
      const now = clock();
      if (!Number.isFinite(now)) throw new MeetupProviderError('invalid_request');
      remaining = deadline === undefined ? timeoutMs : Math.min(timeoutMs, deadline - now);
      endsAt = now + remaining;
    } catch { throw new MeetupProviderError('invalid_request'); }
    if (remaining <= 0) throw new MeetupProviderError('deadline_exceeded');
    const controller = new AbortController();
    let timer, reader, response, failure;
    let rejectStop;
    const stopped = new Promise((_, reject) => { rejectStop = reject; });
    const stop = code => {
      failure = code;
      controller.abort();
      rejectStop(new MeetupProviderError(code));
    };
    const cancel = () => stop('cancelled');
    signal?.addEventListener('abort', cancel, { once: true });
    timer = setTimeout(() => stop('deadline_exceeded'), remaining);
    const work = async () => {
      let token;
      try { token = await tokenSupplier?.({ signal: controller.signal }); }
      catch { throw new MeetupProviderError('authentication_unavailable'); }
      if (controller.signal.aborted) throw new MeetupProviderError(failure);
      if (clock() >= endsAt) throw new MeetupProviderError('deadline_exceeded');
      if (typeof token !== 'string' || !/^[\x21-\x7e]+$/.test(token)) {
        throw new MeetupProviderError('authentication_unavailable');
      }
      response = await fetchImpl('https://api.meetup.com/gql-ext', {
        method: 'POST', redirect: 'error', signal: controller.signal,
        headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json', accept: 'application/json' },
        body: JSON.stringify({ query, variables })
      });
      if (controller.signal.aborted) {
        try { await response?.body?.cancel(); } catch {}
        throw new MeetupProviderError(failure);
      }
      if (!Number.isInteger(response?.status)) throw new MeetupProviderError('response_invalid');
      if (clock() >= endsAt) throw new MeetupProviderError('deadline_exceeded');
      const code = { 401: 'authentication_failed', 403: 'permission_denied', 429: 'rate_limited' }[response.status];
      if (code) throw new MeetupProviderError(code);
      if (response.status < 200 || response.status >= 300) throw new MeetupProviderError('transport_unavailable');
      if (response.redirected || !response.body?.getReader) throw new MeetupProviderError('response_invalid');
      reader = response.body.getReader();
      const chunks = [];
      let size = 0;
      while (true) {
        const { done, value } = await reader.read();
        if (clock() >= endsAt) throw new MeetupProviderError('deadline_exceeded');
        if (done) break;
        if (!(value instanceof Uint8Array)) throw new MeetupProviderError('response_invalid');
        size += value.byteLength;
        if (size > maxResponseBytes) throw new MeetupProviderError('response_invalid');
        chunks.push(value);
      }
      const bytes = new Uint8Array(size);
      let offset = 0;
      for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
      let body;
      try { body = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes)); }
      catch { throw new MeetupProviderError('response_invalid'); }
      if (!body || typeof body !== 'object' || Array.isArray(body)) throw new MeetupProviderError('response_invalid');
      if (body.errors !== undefined) {
        if (!Array.isArray(body.errors)) throw new MeetupProviderError('response_invalid');
        if (body.errors.length) {
          const codes = body.errors.map(error => error?.extensions?.code);
          throw new MeetupProviderError(codes.includes('UNAUTHENTICATED') ? 'authentication_failed'
            : codes.includes('FORBIDDEN') ? 'permission_denied'
              : codes.includes('RATE_LIMITED') ? 'rate_limited' : 'schema_unsupported');
        }
      }
      if (!body.data || typeof body.data !== 'object' || Array.isArray(body.data)) throw new MeetupProviderError('response_invalid');
      return body.data;
    };
    try {
      return await Promise.race([work(), stopped]);
    } catch (error) {
      throw new MeetupProviderError(failure || providerErrorCode(error, 'transport_unavailable'));
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener('abort', cancel);
      controller.abort();
      // Do not let a noncompliant caller stream hold the deadline open.
      try {
        const cleanup = reader ? reader.cancel() : response?.body?.cancel();
        Promise.resolve(cleanup).catch(() => {});
      } catch {}
      try { reader?.releaseLock(); } catch {}
    }
  };
}
