// Offline provider read with a standard streamed Response, no network.
import assert from 'node:assert/strict';
import {createMeetupGroupResolver} from '@mathist/meetup-integration';
let calls = 0;
const resolve = createMeetupGroupResolver({
  tokenSupplier: async () => 'synthetic-token',
  fetchImpl: async (url, options) => {
    calls++;
    assert.equal(url, 'https://api.meetup.com/gql-ext');
    assert.equal(options.method, 'POST');
    return new Response(JSON.stringify({data: {groupByUrlname:
      {id: 'group-one', name: 'Example group', urlname: 'example-group'}}}), {status: 200});
  }
});
const group = await resolve('example-group');
assert.equal(group.id, 'group-one');
console.log(`group=${group.id}; calls=${calls}`);
try { await resolve('events'); } catch (error) {
  assert.equal(error.code, 'invalid_request');
  console.log(`read failure=${error.code}; calls=${calls}`);
}
assert.equal(calls, 1);
