import test from 'node:test';
import assert from 'node:assert/strict';
const api = await import(process.env.MEETUP_JS_MODULE || '@mathist/meetup-integration');
if (!process.env.MEETUP_JS_MODULE) {
  assert.ok(import.meta.resolve('@mathist/meetup-integration').includes('/node_modules/@mathist/meetup-integration/'));
}
const { createMeetupGroupResolver, createMeetupTopicProvider, createMeetupTopicCatalog,
  normalizeMeetupUrlName, normalizeMeetupTokenResponse } = api;
const response = data => new Response(JSON.stringify({ data }));
const tokenSupplier = async () => 'synthetic-access';
const group = { id: '123', name: 'Synthetic', urlname: 'synthetic' };
const options = fetchImpl => ({ fetchImpl, tokenSupplier });
const safeError = code => error => {
  assert.equal(error.code, code);
  assert.equal(error.cause, undefined);
  assert.equal(error.context, undefined);
  assert.doesNotMatch(JSON.stringify(error) + error.stack, /SENSITIVE/);
  return true;
};
const capability = () => ({ provenance: 'authenticated_introspection',
  searchSupported: true, readbackSupported: true, createSupported: true,
  editSupported: true, expiresAt: new Date(100000).toISOString() });
test('reviewer regression: catalog redacts mutated provider exception codes', async () => {
  const error = new api.MeetupProviderError('response_invalid');
  error.code = 'SENSITIVE_SYNTHETIC_DIAGNOSTIC';
  const catalog = createMeetupTopicCatalog({ clock: () => 1000, probe: async () => capability(),
    search: async () => { throw error; } });
  const result = await catalog.search('support');
  assert.doesNotMatch(JSON.stringify(result), /SENSITIVE/);
  assert.equal(result.errorCode, 'response_invalid');
});
test('reviewer regression: transport redacts exceptional provider error code access', async () => {
  const error = new api.MeetupProviderError('response_invalid');
  Object.defineProperty(error, 'code', { get() { throw Error('SENSITIVE_SYNTHETIC_DIAGNOSTIC'); } });
  await assert.rejects(createMeetupGroupResolver(options(async () => { throw error; }))('synthetic'),
    safeError('transport_unavailable'));
});
test('callback errors are normalized across transport, probe, search and validation', async () => {
  const hostile = () => Error('SENSITIVE_SYNTHETIC_DIAGNOSTIC');
  const mutated = new api.MeetupProviderError('response_invalid');
  mutated.code = 'SENSITIVE_SYNTHETIC_DIAGNOSTIC';
  const accessor = new api.MeetupProviderError('response_invalid');
  Object.defineProperty(accessor, 'code', { get() { throw hostile(); } });
  const proxy = new Proxy({}, { getPrototypeOf() { throw hostile(); } });
  const getProxy = new Proxy(new api.MeetupProviderError('response_invalid'),
    { get() { throw hostile(); } });
  const revoked = Proxy.revocable({}, {}); revoked.revoke();
  const changing = new api.MeetupProviderError('response_invalid');
  let reads = 0;
  Object.defineProperty(changing, 'code', { get() { return ++reads % 2 ? 'permission_denied' : 'SENSITIVE'; } });
  const categories = ['invalid_request', 'authentication_unavailable', 'authentication_failed',
    'permission_denied', 'rate_limited', 'transport_unavailable', 'schema_unsupported',
    'response_invalid', 'deadline_exceeded', 'cancelled'];
  const contextual = new api.MeetupProviderError('permission_denied');
  contextual.message = 'SENSITIVE';
  for (const key of ['cause', 'context']) Object.defineProperty(contextual, key, { get() { throw hostile(); } });
  for (const [error, preserved] of [[mutated], [accessor], [proxy], [getProxy], [revoked.proxy], [null],
    [{ code: 'permission_denied' }], [contextual, 'permission_denied'],
    ...categories.map(code => [new api.MeetupProviderError(code), code])]) {
    const fail = async () => { throw error; };
    await assert.rejects(createMeetupGroupResolver(options(fail))('synthetic'), safeError(preserved || 'transport_unavailable'));
    await assert.rejects(createMeetupTopicProvider({ clock: () => { throw error; } }).probe(), safeError(preserved || 'schema_unsupported'));
    const catalog = createMeetupTopicCatalog({ clock: () => 1000, probe: async () => capability(), search: fail });
    const result = await catalog.search('support');
    assert.doesNotMatch(JSON.stringify(result), /SENSITIVE/);
    assert.equal(result.errorCode, preserved || 'response_invalid');
    await assert.rejects(catalog.validate([{ id: '1', name: 'Support' }]), safeError(preserved || 'response_invalid'));
    const probeCatalog = createMeetupTopicCatalog({ clock: () => 1000, probe: fail, search: fail });
    assert.equal((await probeCatalog.search('support')).errorCode, preserved || 'response_invalid');
  }
  const catalog = createMeetupTopicCatalog({ clock: () => 1000, probe: async () => capability(),
    search: async () => { throw changing; } });
  assert.equal((await catalog.search('support')).errorCode, 'permission_denied');
  assert.equal(reads, 1);
});
test('reviewer negatives: post-fetch clock expiry cancels once and credential links fall back', async () => {
  let now = 0, cancelled = 0;
  const resolve = createMeetupGroupResolver({ clock: () => now, timeoutMs: 10,
    tokenSupplier, fetchImpl: async () => {
      now = 11;
      return new Response(new ReadableStream({ cancel() { cancelled++; } }));
    } });
  await assert.rejects(resolve('synthetic'), safeError('deadline_exceeded'));
  assert.equal(cancelled, 1);
  assert.equal(api.normalizeMeetupGroupResult({ ...group,
    link: 'https://synthetic:synthetic@www.meetup.com/synthetic/' }).url,
  'https://www.meetup.com/synthetic/');
});
test('negative: public provider error rejects unknown codes without caller coercion', () => {
  for (const code of [null, undefined, {}, Symbol('unknown'), '__proto__',
    { toString() { throw Error('SENSITIVE'); } }]) {
    assert.ok(safeError('response_invalid')(new api.MeetupProviderError(code)));
  }
});
test('negative: missing fetch denies token acquisition; supplier failure denies fetch', async () => {
  await assert.rejects(createMeetupGroupResolver({ tokenSupplier: () => assert.fail() })('synthetic'), safeError('transport_unavailable'));
  await assert.rejects(createMeetupGroupResolver({ fetchImpl: () => assert.fail(), tokenSupplier: () => { throw Error('SENSITIVE'); } })('synthetic'), safeError('authentication_unavailable'));
});
test('negative: aborted calls, invalid controls and expired absolute deadline never acquire tokens', async () => {
  const resolve = createMeetupGroupResolver({ fetchImpl: () => assert.fail(), tokenSupplier: () => assert.fail(), clock: () => 100 });
  const controller = new AbortController(); controller.abort();
  await assert.rejects(resolve('synthetic', { signal: controller.signal }), safeError('cancelled'));
  await assert.rejects(resolve('synthetic', { deadline: 99 }), safeError('deadline_exceeded'));
  await assert.rejects(resolve('synthetic', { signal: {} }), safeError('invalid_request'));
  await assert.rejects(resolve('synthetic', { deadline: NaN }), safeError('invalid_request'));
  await assert.rejects(resolve({ toString() { throw Error('SENSITIVE'); } }), safeError('invalid_request'));
});
test('negative: late fetch response is cancelled after timeout without retry', async () => {
  let finish, cancellations = 0, calls = 0;
  const resolve = createMeetupGroupResolver({ ...options(() => { calls++; return new Promise(r => { finish = r; }); }), timeoutMs: 5 });
  await assert.rejects(resolve('synthetic'), safeError('deadline_exceeded'));
  finish(new Response(new ReadableStream({ cancel() { cancellations++; } })));
  await new Promise(r => setTimeout(r, 0));
  assert.equal(calls, 1); assert.equal(cancellations, 1);
});
test('negative: whole probe uses one deadline and stops subsequent introspection', async () => {
  let now = 0, calls = 0;
  const provider = createMeetupTopicProvider({ clock: () => now, timeoutMs: 10, ...options(async () => {
    calls++; now += 11;
    return response({ __type: { fields: [] } });
  }) });
  await assert.rejects(provider.probe(), safeError('deadline_exceeded'));
  assert.equal(calls, 1);
});
test('negative: catalog rejects stale-at-completion, substitutions, duplicate and too-many selections', async () => {
  let now = 1000, stale = false, probes = 0;
  const capability = () => ({ provenance: 'authenticated_introspection', searchSupported: true, readbackSupported: true, createSupported: true, editSupported: true, expiresAt: new Date(now + 10).toISOString() });
  const catalog = createMeetupTopicCatalog({ clock: () => now, probe: async () => { probes++; return capability(); },
    search: async () => { if (stale) now += 11; return [{ id: '1', name: 'Support' }]; }
  });
  const one = { id: '1', name: 'Support' };
  await assert.rejects(catalog.validate([one, one]), safeError('invalid_request'));
  await assert.rejects(catalog.validate(Array(6).fill(one)), safeError('invalid_request'));
  assert.equal(probes, 0);
  await assert.rejects(catalog.validate([{ id: '1', name: 'Substitute' }]), safeError('response_invalid'));
  stale = true;
  await assert.rejects(catalog.validate([one]), safeError('schema_unsupported'));
  assert.deepEqual((await catalog.search('support', { fresh: true })).topics, []);
  const failing = createMeetupTopicCatalog({ clock: () => now, probe: async () => capability(), search: async () => { throw Error('SENSITIVE'); } });
  await assert.rejects(failing.validate([one]), safeError('response_invalid'));
  assert.doesNotMatch(JSON.stringify(await failing.search('support')), /SENSITIVE/);
});
test('negative: provider query bounds and token validation deny transport', async () => {
  const provider = createMeetupTopicProvider({ fetchImpl: () => assert.fail(), tokenSupplier });
  for (const term of ['a'.repeat(101), {}, null]) await assert.rejects(provider.search(term), safeError('invalid_request'));
  for (const token of ['', 'contains space', 'control\n', undefined]) {
    await assert.rejects(createMeetupGroupResolver({ fetchImpl: () => assert.fail(), tokenSupplier: async () => token })('synthetic'), safeError('authentication_unavailable'));
  }
});
test('negative: auth permission rate and transport errors are fixed and never retried', async () => {
  for (const [status, code] of [[401, 'authentication_failed'], [403, 'permission_denied'], [429, 'rate_limited'], [500, 'transport_unavailable']]) {
    let calls = 0;
    await assert.rejects(createMeetupGroupResolver(options(async () => { calls++; return new Response('SENSITIVE', { status }); }))('synthetic'), safeError(code));
    assert.equal(calls, 1);
  }
  for (const [code, expected] of [['UNAUTHENTICATED', 'authentication_failed'], ['FORBIDDEN', 'permission_denied'], ['RATE_LIMITED', 'rate_limited'], ['OTHER', 'schema_unsupported']]) {
    await assert.rejects(createMeetupGroupResolver(options(async () => new Response(JSON.stringify({ data: { groupByUrlname: group }, errors: [{ message: 'SENSITIVE', extensions: { code } }] }))))('synthetic'), safeError(expected));
  }
});
test('negative: malformed partial mismatched and oversized replies do not become success', async () => {
  for (const body of ['SENSITIVE', 'null', '[]', '{}', '{"data":null}', '{"data":{}}',
    JSON.stringify({ data: { groupByUrlname: {} } }),
    JSON.stringify({ data: { groupByUrlname: { ...group, urlname: 'other' } } })]) {
    await assert.rejects(createMeetupGroupResolver(options(async () => new Response(body)))('synthetic'), safeError('response_invalid'));
  }
  await assert.rejects(createMeetupGroupResolver({ ...options(async () => response({ groupByUrlname: group })), maxResponseBytes: 2 })('synthetic'), safeError('response_invalid'));
});
test('negative: deadline includes supplier and cancels late work without a fetch', async () => {
  let finish, calls = 0;
  const resolve = createMeetupGroupResolver({ timeoutMs: 5, tokenSupplier: () => new Promise(r => { finish = r; }), fetchImpl: () => { calls++; } });
  await assert.rejects(resolve('synthetic'), safeError('deadline_exceeded'));
  finish('synthetic-access');
  await new Promise(r => setTimeout(r, 0));
  assert.equal(calls, 0);
});
test('negative: injected clock expiry during supplier denies provider fetch', async () => {
  let now = 0;
  const resolve = createMeetupGroupResolver({
    clock: () => now, timeoutMs: 10,
    tokenSupplier: async () => { now = 11; return 'synthetic-access'; },
    fetchImpl: () => assert.fail('expired supplier must not fetch')
  });
  await assert.rejects(resolve('synthetic'), safeError('deadline_exceeded'));
});
test('negative: stream cancellation and cleanup follow abort and byte limit', async () => {
  for (const abort of [true, false]) {
    let cancelled = 0, transportSignal;
    const controller = new AbortController();
    const resolve = createMeetupGroupResolver({ ...options(async (_url, init) => {
      transportSignal = init.signal;
      return new Response(new ReadableStream({
        start(stream) { if (!abort) stream.enqueue(new Uint8Array(100)); },
        cancel() { cancelled++; }
      }));
    }), maxResponseBytes: 10 });
    const promise = resolve('synthetic', { signal: controller.signal });
    if (abort) setTimeout(() => controller.abort(), 5);
    await assert.rejects(promise, safeError(abort ? 'cancelled' : 'response_invalid'));
    assert.equal(transportSignal.aborted, true);
    assert.equal(cancelled, 1);
  }
});
test('source group payload and URL normalization; explicit not-found remains null', async () => {
  const resolve = createMeetupGroupResolver(options(async (url, init) => {
    assert.equal(url, 'https://api.meetup.com/gql-ext');
    assert.equal(init.method, 'POST'); assert.equal(init.redirect, 'error');
    assert.deepEqual(JSON.parse(init.body), {
      query: 'query($urlname: String!) { groupByUrlname(urlname: $urlname) { id name urlname } }',
      variables: { urlname: 'synthetic' }
    });
    return response({ groupByUrlname: group });
  }));
  assert.equal((await resolve('https://www.meetup.com/Synthetic/')).id, '123');
  for (const name of ['events', 'https://example.com/group', 'https://user@meetup.com/group', 'bad space']) assert.equal(normalizeMeetupUrlName(name), '');
  assert.equal(await createMeetupGroupResolver(options(async () => response({ groupByUrlname: null })))('synthetic'), null);
});
const ref = name => ({ kind: 'SCALAR', name });
const list = name => ({ kind: 'LIST', ofType: ref(name) });
const field = (name, type, args = []) => ({ name, type, args });
const schema = {
  Query: [field('suggestTopics', ref('TopicsConnection'), [field('query', ref('String'))]), field('event', ref('Event'), [field('id', ref('ID'))])],
  Mutation: [field('createEvent', ref('CreateEventPayload'), [field('input', ref('CreateEventInput'))]), field('editEvent', ref('EditEventPayload'), [field('input', ref('EditEventInput'))])],
  Event: [field('topics', ref('TopicsConnection'))],
  Topic: [field('id', ref('ID')), field('name', ref('String'))],
  TopicsConnection: [field('edges', list('TopicEdge'))],
  TopicEdge: [field('node', ref('Topic'))],
  CreateEventInput: [field('topics', list('ID'))],
  EditEventInput: [field('topics', list('ID'))]
};
test('source topic queries and all eight capability types; schema drift disables capability', async () => {
  let calls = [], drift = false, active = 0, max = 0;
  const provider = createMeetupTopicProvider({ clock: () => 1000, ...options(async (_url, init) => {
    active++; max = Math.max(max, active);
    const { query, variables } = JSON.parse(init.body); calls.push(variables);
    let data;
    if (variables.name) {
      assert.match(query, /__type\(name: \$name\)/);
      data = { __type: { [variables.name.endsWith('Input') ? 'inputFields' : 'fields']: drift ? [] : schema[variables.name] } };
    } else {
      assert.equal(query, 'query($query: String!, $first: Int!) { suggestTopics(query: $query, first: $first, excludeMemberTopics: false) { edges { node { id name } } } }');
      assert.deepEqual(variables, { query: 'Support', first: 20 });
      data = { suggestTopics: { edges: [{ node: { id: '1', name: 'Support' } }] } };
    }
    active--; return response(data);
  }) });
  assert.equal((await provider.probe()).expiresAt, new Date(241000).toISOString());
  assert.deepEqual(calls.map(x => x.name), Object.keys(schema));
  assert.equal(max, 1);
  assert.deepEqual(await provider.search('Support'), [{ id: '1', name: 'Support' }]);
  drift = true;
  assert.equal((await provider.probe()).searchSupported, false);
});
test('negative: topic malformed connections and schema replies fail closed', async () => {
  for (const value of [{}, { edges: null }, { edges: [null] }, { edges: [{ node: { id: '1' } }] }, { edges: Array(21).fill({ node: { id: '1', name: 'Support' } }) }]) {
    await assert.rejects(createMeetupTopicProvider(options(async () => response({ suggestTopics: value }))).search('Support'), safeError('response_invalid'));
  }
  await assert.rejects(createMeetupTopicProvider(options(async () => response({ __type: null }))).probe(), safeError('schema_unsupported'));
  for (const fields of [[null], [{ name: 'SENSITIVE', args: 'SENSITIVE' }], [{ name: 'x', type: {}, args: [null] }]]) {
    await assert.rejects(createMeetupTopicProvider(options(async () => response({ __type: { fields } }))).probe(), safeError('schema_unsupported'));
  }
});
test('ported source stale capability and canonical search; fresh validation re-probes', async () => {
  let now = 1000, probes = 0;
  const catalog = createMeetupTopicCatalog({ clock: () => now, ttlMs: 100,
    probe: async () => { probes++; return { provenance: 'authenticated_introspection', searchSupported: true, readbackSupported: true, createSupported: true, editSupported: true, expiresAt: new Date(now + 50).toISOString() }; },
    search: async () => [{ id: ' 1 ', name: ' Support ' }, { id: '1', name: 'Duplicate' }, { id: '', name: 'Invalid' }]
  });
  assert.deepEqual((await catalog.search('support')).topics, [{ id: '1', name: 'Support' }]);
  now += 55;
  assert.equal((await catalog.search('support')).reason, 'event_topic_schema_unsupported_or_stale');
  assert.equal(probes, 1);
  assert.deepEqual(await catalog.validate([{ id: '1', name: 'Support' }]), [{ id: '1', name: 'Support' }]);
  assert.equal(probes, 2);
  await assert.rejects(catalog.validate([{ id: '2', name: 'Support' }]), safeError('response_invalid'));
  assert.equal((await createMeetupTopicCatalog().search('support')).supported, false);
});
test('pure OAuth normalization ports rotating-pair requirements without transport', () => {
  assert.throws(() => normalizeMeetupTokenResponse(Object.create({ access_token: 'SENSITIVE', refresh_token: 'SENSITIVE', expires_in: 3600 }), 1), safeError('authentication_unavailable'));
  assert.throws(() => normalizeMeetupTokenResponse({ get access_token() { throw Error('SENSITIVE'); }, refresh_token: 'synthetic', expires_in: 3600 }, 1), safeError('authentication_unavailable'));
  assert.throws(() => normalizeMeetupTokenResponse({ access_token: 'synthetic', refresh_token: 'synthetic', expires_in: 3600 }, Number.MAX_SAFE_INTEGER), safeError('authentication_unavailable'));
  assert.deepEqual(normalizeMeetupTokenResponse({ access_token: 'access', refresh_token: 'refresh', expires_in: '3600', token_type: 'Bearer' }, 100), { accessToken: 'access', refreshToken: 'refresh', expiresAt: 3600100 });
  for (const value of [null, [], {}, { access_token: 'SENSITIVE', expires_in: 3600 },
    { access_token: 'SENSITIVE', refresh_token: 'SENSITIVE', expires_in: 60 },
    { access_token: 'SENSITIVE', refresh_token: 'SENSITIVE', expires_in: Infinity }]) {
    assert.throws(() => normalizeMeetupTokenResponse(value, 1), safeError('authentication_unavailable'));
  }
});
test('concurrency seam retains caller broker single-flight; package has no second refresh owner', async () => {
  let brokerCalls = 0, rotations = 0, inFlight;
  const brokerSupplier = () => {
    brokerCalls++;
    return inFlight ||= Promise.resolve().then(() => { rotations++; return 'broker-access'; });
  };
  let fetchCalls = 0;
  const fetchImpl = async (url, init) => {
    assert.equal(url, 'https://api.meetup.com/gql-ext');
    assert.equal(init.headers.authorization, 'Bearer broker-access'); fetchCalls++;
    return response(JSON.parse(init.body).variables.urlname ? { groupByUrlname: group } : { suggestTopics: { edges: [] } });
  };
  const resolve = createMeetupGroupResolver({ fetchImpl, tokenSupplier: brokerSupplier });
  const provider = createMeetupTopicProvider({ fetchImpl, tokenSupplier: brokerSupplier });
  await Promise.all([resolve('synthetic'), provider.search('Support'), resolve('synthetic')]);
  assert.equal(brokerCalls, 3); assert.equal(rotations, 1); assert.equal(fetchCalls, 3);
  const failed = createMeetupGroupResolver({ fetchImpl: () => assert.fail('no fallback'), tokenSupplier: async () => { throw Error('SENSITIVE'); } });
  await assert.rejects(failed('synthetic'), safeError('authentication_unavailable'));
});
