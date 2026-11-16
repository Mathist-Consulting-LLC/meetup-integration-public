// Supplemental provenance test, not a runtime dependency or installed-package prerequisite.
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
import { createMeetupGroupResolver, createMeetupTopicProvider } from '../javascript/src/index.js';
const root = process.argv[2];
assert.ok(root, 'Pass the retained read-only source checkout explicitly.');
const source = name => pathToFileURL(resolve(root, 'src', name)).href;
const { createMeetupOAuthTokenSupplier, createRemoteMeetupTokenSupplier } = await import(source('meetup-oauth.js'));
const { encryptLocationCredential, decryptLocationCredential } = await import(source('location-credentials.js'));
const key = 'synthetic-key-only';
let row = { encrypted: encryptLocationCredential(JSON.stringify({
  accessToken: 'expired', refreshToken: 'synthetic-old', expiresAt: 0
}), key) };
let tail = Promise.resolve(), refreshes = 0, releases = 0, brokerCalls = 0;
const pool = { async connect() {
  let unlock;
  return {
    async query(sql, args) {
      if (sql === 'begin') {
        const previous = tail;
        tail = new Promise(resolve => { unlock = resolve; });
        await previous;
      }
      if (sql.startsWith('select')) return { rows: [{ value_json: row }] };
      if (sql.startsWith('update')) row = JSON.parse(args[1]);
      if (sql === 'commit' || sql === 'rollback') { unlock?.(); unlock = null; }
      return { rows: [] };
    },
    release() { releases++; unlock?.(); }
  };
} };
const owner = createMeetupOAuthTokenSupplier({
  pool, clientId: 'synthetic-id', clientSecret: 'synthetic-secret', encryptionKey: key, now: () => 100,
  fetchImpl: async (url, init) => {
    assert.equal(url, 'https://secure.meetup.com/oauth2/access');
    assert.equal(init.body.get('refresh_token'), 'synthetic-old');
    refreshes++;
    return { ok: true, json: async () => ({ access_token: 'synthetic-new', refresh_token: 'synthetic-rotated', expires_in: 3600 }) };
  }
});
const broker = createRemoteMeetupTokenSupplier({
  url: 'https://broker.example.invalid/access', key: 'synthetic-broker-key',
  fetchImpl: async (url, init) => {
    assert.equal(url, 'https://broker.example.invalid/access');
    assert.equal(init.headers.authorization, 'Bearer synthetic-broker-key');
    brokerCalls++;
    return { ok: true, json: async () => ({ access_token: await owner() }) };
  }
});
const fetchImpl = async (url, init) => {
  assert.equal(url, 'https://api.meetup.com/gql-ext');
  assert.equal(init.headers.authorization, 'Bearer synthetic-new');
  return new Response(JSON.stringify({ data: JSON.parse(init.body).variables.urlname
    ? { groupByUrlname: { id: '1', urlname: 'synthetic' } }
    : { suggestTopics: { edges: [] } } }));
};
await Promise.all([
  createMeetupGroupResolver({ tokenSupplier: broker, fetchImpl })('synthetic'),
  createMeetupTopicProvider({ tokenSupplier: broker, fetchImpl }).search('Support')
]);
assert.equal(refreshes, 1);
assert.equal(brokerCalls, 2);
assert.equal(releases, 2);
assert.equal(JSON.parse(decryptLocationCredential(row.encrypted, key)).refreshToken, 'synthetic-rotated');
console.log('Actual source broker + single locked encrypted owner: concurrent extracted lookups passed.');
