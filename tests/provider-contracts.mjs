import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createMeetupGroupResolver, createMeetupTopicProvider,
  normalizeMeetupTokenResponse } from '@mathist/meetup-integration';

const corpus = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
let count = 0;
for (const test of corpus.cases) {
  let calls = 0;
  const resolve = createMeetupGroupResolver({
    tokenSupplier: () => 'synthetic-token',
    fetchImpl: async (_url, options) => {
      calls++;
      const request = JSON.parse(options.body);
      assert.equal(request.variables.urlname, 'synthetic');
      assert.match(request.query, /groupByUrlname/);
      assert.doesNotMatch(request.query, /mutation/);
      if (test.throw) throw new Error('PRIVATE');
      return new Response(typeof test.body === 'string' ? test.body : JSON.stringify(test.body),
        { status: test.status });
    }
  });
  await assert.rejects(resolve('synthetic'), error => {
    assert.equal(error.code, test.code, test.id);
    assert.equal(error.cause, undefined);
    assert.doesNotMatch(String(error), /PRIVATE|synthetic-token/);
    return true;
  });
  assert.equal(calls, 1);
  count++;
}
// Pure rotating response normalization is not a refresh request/replay permit.
assert.throws(() => normalizeMeetupTokenResponse({ access_token: 'PRIVATE' }));
let calls = 0;
const provider = createMeetupTopicProvider({
  tokenSupplier: () => { throw new Error('PRIVATE before submission'); },
  fetchImpl: () => { calls++; throw new Error('must not submit'); }
});
await assert.rejects(provider.search('Python'), error => error.code === 'authentication_unavailable');
assert.equal(calls, 0);
console.log(`Shared provider faults: ${count}; pre-submit denial and pure OAuth validation passed.`);
const schema = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const probes = [];
const schemaProvider = () => createMeetupTopicProvider({
  tokenSupplier: () => 'synthetic-token',
  fetchImpl: async (_url, options) => {
    const request = JSON.parse(options.body);
    assert.match(request.query, /^query/);
    assert.doesNotMatch(request.query, /mutation\s*[({]/);
    probes.push(request.variables.name);
    return new Response(JSON.stringify({ data: { __type: schema.data.__schema.types
      .find(type => type.name === request.variables.name) } }), { status: 200 });
  }
});
assert.equal((await schemaProvider().probe()).searchSupported, true);
assert.equal(probes.length, 8);
schema.data.__schema.types.find(type => type.name === 'CreateEventInput')
  .inputFields.find(field => field.name === 'topics').type = { kind: 'SCALAR', name: 'ID' };
assert.equal((await schemaProvider().probe()).searchSupported, false);
console.log('Shared generated schema: real JS probe accepts supported subset and rejects list drift.');
