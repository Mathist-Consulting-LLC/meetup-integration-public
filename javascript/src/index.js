// Offline interfaces retained alongside caller-injected provider mechanics.
const messages = Object.freeze({
  invalid_contract: 'Invalid offline contract.',
  authentication_unavailable: 'Access token unavailable.',
  transport_unavailable: 'Caller transport unavailable.'
});
export class IntegrationError extends Error {
  constructor(code) {
    const safe = typeof code === 'string' && Object.hasOwn(messages, code) ? code : 'invalid_contract';
    super(messages[safe]);
    this.name = 'IntegrationError';
    this.code = safe;
  }
}
const record = value => value !== null && typeof value === 'object'
  && Object.getPrototypeOf(value) === Object.prototype;
const keys = (value, expected) => record(value)
  && Reflect.ownKeys(value).length === expected.length
  && expected.every(key => Object.hasOwn(value, key)
    && Object.getOwnPropertyDescriptor(value, key)?.get === undefined
    && Object.getOwnPropertyDescriptor(value, key)?.set === undefined);
export function validateTopic(value) {
  try {
    if (!keys(value, ['id', 'name']) || ![['id', 128], ['name', 160]].every(([key, limit]) =>
      typeof value[key] === 'string' && value[key].trim() && value[key] === value[key].trim()
      && Array.from(value[key]).length <= limit)) throw new IntegrationError('invalid_contract');
    return { ...value };
  } catch {
    throw new IntegrationError('invalid_contract');
  }
}
/** tokenSupplier: () => string|Promise<string>
 * transport: ({body: Uint8Array}, token: string) => {status:number, body:Uint8Array}|Promise<...>
 * Caller owns cancellation, timeout and resource cleanup. No automatic retry.
 */
export function createBoundary({ tokenSupplier, transport } = {}) {
  return Object.freeze({
    async exchange(request) {
      try {
        if (!keys(request, ['body']) || !(request.body instanceof Uint8Array)) throw new IntegrationError('invalid_contract');
      } catch {
        throw new IntegrationError('invalid_contract');
      }
      if (typeof transport !== 'function') throw new IntegrationError('transport_unavailable');
      let token;
      try { token = typeof tokenSupplier === 'function' ? await tokenSupplier() : undefined; } catch {}
      if (typeof token !== 'string' || !/^[\x21-\x7e]+$/.test(token)) throw new IntegrationError('authentication_unavailable');
      let result;
      try { result = await transport(request, token); } catch { throw new IntegrationError('transport_unavailable'); }
      try {
        if (!keys(result, ['status', 'body']) || !Number.isInteger(result.status)
          || result.status < 100 || result.status > 599 || !(result.body instanceof Uint8Array)) throw new IntegrationError('invalid_contract');
        return result;
      } catch {
        throw new IntegrationError('invalid_contract');
      }
    }
  });
}

export { MeetupProviderError } from './provider-transport.js';
export { createMeetupGroupResolver, normalizeMeetupGroupResult, normalizeMeetupUrlName } from './meetup-group-resolver.js';
export { createMeetupTopicProvider } from './meetup-topic-provider.js';
export { createMeetupTopicCatalog } from './meetup-topic-catalog.js';
export { normalizeMeetupTokenResponse } from './meetup-oauth.js';
