import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createBoundary, validateTopic, IntegrationError } from '@mathist/meetup-integration';
const fixtures = JSON.parse(readFileSync(process.argv[2]));
assert.deepEqual(Object.keys(fixtures).sort(), ['invalid', 'schema', 'valid']);
assert.equal(fixtures.schema, 'meetup-integration/offline-topic/1');
assert.ok(Array.isArray(fixtures.valid) && Array.isArray(fixtures.invalid));
assert.ok(import.meta.resolve('@mathist/meetup-integration').includes('/node_modules/@mathist/meetup-integration/'));
test('shared fixture and malformed identities', () => {
  for (const value of fixtures.valid) assert.deepEqual(validateTopic(value), value);
  for (const value of [...fixtures.invalid, {id:'x'.repeat(129),name:'Topic'}, Object.create({id:'x',name:'Topic'}), {get id(){throw Error('secret')},name:'Topic'}]) {
    assert.throws(() => validateTopic(value), error => error.code === 'invalid_contract');
  }
});
test('awaits caller tokens per call and preserves non-success status', async () => {
  const seen = [];
  let calls = 0;
  const boundary = createBoundary({tokenSupplier: async () => `token-${++calls}`, transport: async (request, token) => {
    seen.push([Array.from(request.body), token]); return {status:429,body:new Uint8Array([2])};
  }});
  for (let i=0;i<2;i++) assert.equal((await boundary.exchange({body:new Uint8Array([1])})).status,429);
  assert.deepEqual(seen, [[[1],'token-1'],[[1],'token-2']]);
});
test('denies absent/malformed callbacks and sanitizes failures', async () => {
  const request = {body:new Uint8Array()};
  await assert.rejects(createBoundary().exchange(request), error => error.code === 'transport_unavailable');
  await assert.rejects(createBoundary({tokenSupplier:()=>assert.fail('must not acquire token without transport')}).exchange(request), error=>error.code==='transport_unavailable');
  for (const tokenSupplier of [undefined, () => '', () => 'bad\r\ntoken', () => {throw Error('synthetic-secret')}]) {
    await assert.rejects(createBoundary({tokenSupplier,transport:()=>assert.fail('must deny')}).exchange(request), error => error.code === 'authentication_unavailable' && !error.stack.includes('synthetic-secret'));
  }
  await assert.rejects(createBoundary({tokenSupplier:()=> 'token',transport:()=>{throw Error('synthetic-secret')}}).exchange(request),error=>error.code==='transport_unavailable' && !error.stack.includes('synthetic-secret') && !error.cause);
  for (const result of [null, {}, {status:true,body:new Uint8Array()}, {status:600,body:new Uint8Array()}, {status:200,body:'bad'}]) {
    await assert.rejects(createBoundary({tokenSupplier:()=> 'token',transport:()=>result}).exchange(request), IntegrationError);
  }
  await assert.rejects(createBoundary().exchange({body:'bad'}), IntegrationError);
});

const safeInvalid = error => error instanceof IntegrationError
  && error.code === 'invalid_contract' && error.message === 'Invalid offline contract.'
  && !error.stack.includes('synthetic-proxy-secret') && error.cause === undefined;

test('proxy shape and property traps produce fixed contract errors', async () => {
  for (const trap of ['getPrototypeOf', 'ownKeys', 'getOwnPropertyDescriptor', 'get']) {
    const hostile = target => new Proxy(target, {
      [trap](target, key, receiver) {
        // Let await inspect thenability; fail when validators read contract fields.
        if (trap === 'get' && key === 'then') return Reflect.get(target, key, receiver);
        throw new Error('synthetic-proxy-secret');
      }
    });
    assert.throws(() => validateTopic(hostile({id:'x', name:'Topic'})), safeInvalid, trap);
    let acquired = 0;
    const boundary = createBoundary({
      tokenSupplier: () => { acquired++; return 'token'; },
      transport: () => assert.fail('invalid request must not reach transport')
    });
    await assert.rejects(boundary.exchange(hostile({body:new Uint8Array()})), safeInvalid, trap);
    assert.equal(acquired, 0);
    let calls = 0;
    const resultBoundary = createBoundary({tokenSupplier: () => 'token', transport: () => {
      calls++; return hostile({status:200, body:new Uint8Array()});
    }});
    await assert.rejects(resultBoundary.exchange({body:new Uint8Array()}), safeInvalid, trap);
    assert.equal(calls, 1, 'malformed result must never be retried');
  }
});

test('unknown error codes do not invoke caller coercion', () => {
  const hostile = new Proxy({}, {get() { throw new Error('synthetic-proxy-secret'); }});
  for (const code of [hostile, {}, [], null, undefined, Symbol('unknown'), 'unknown', '__proto__']) {
    assert.ok(safeInvalid(new IntegrationError(code)));
  }
  for (const code of ['invalid_contract', 'authentication_unavailable', 'transport_unavailable']) {
    assert.equal(new IntegrationError(code).code, code);
  }
});
