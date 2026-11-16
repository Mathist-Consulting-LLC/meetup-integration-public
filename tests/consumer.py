import json
from pathlib import Path
import sys
import traceback
import unittest
from meetup_integration import Boundary, Request, Result, IntegrationError, validate_topic

FIXTURES = json.loads(Path(sys.argv.pop()).read_text())
assert set(FIXTURES) == {'schema', 'valid', 'invalid'}
assert FIXTURES['schema'] == 'meetup-integration/offline-topic/1'
assert type(FIXTURES['valid']) is list and type(FIXTURES['invalid']) is list

class Consumer(unittest.TestCase):
    def test_fixtures(self):
        for value in FIXTURES['valid']:
            self.assertEqual(validate_topic(value), value)
        for value in FIXTURES['invalid'] + [{'id': 'a' * 129, 'name': 'Topic'}]:
            with self.assertRaises(IntegrationError): validate_topic(value)

    def test_unknown_error_codes(self):
        class Hostile:
            def __hash__(self):
                raise ValueError('synthetic-code-secret')

        class HostileString(str):
            def __hash__(self):
                raise ValueError('synthetic-code-secret')

        for code in [[], {}, None, Hostile(), HostileString('invalid_contract'), 'unknown']:
            error = IntegrationError(code)
            self.assertEqual(error.code, 'invalid_contract')
            self.assertEqual(str(error), 'Invalid offline contract.')
            self.assertIsNone(error.__context__)
        for code in ['invalid_contract', 'authentication_unavailable', 'transport_unavailable']:
            self.assertEqual(IntegrationError(code).code, code)

    def test_injection(self):
        tokens = iter(['first', 'second'])
        seen = []
        def send(request, token):
            seen.append((request.body, token))
            return Result(429, b'opaque response')
        boundary = Boundary(token_supplier=lambda: next(tokens), transport=send)
        for _ in range(2): self.assertEqual(boundary.exchange(Request(b'opaque')).status, 429)
        self.assertEqual(seen, [(b'opaque', 'first'), (b'opaque', 'second')])

    def test_denial_and_errors(self):
        with self.assertRaises(IntegrationError) as ctx: Boundary().exchange(Request(b''))
        self.assertEqual(ctx.exception.code, 'transport_unavailable')
        with self.assertRaises(IntegrationError):
            Boundary(token_supplier=lambda: self.fail('must not acquire token without transport')).exchange(Request(b''))
        def fail(*args): raise ValueError('synthetic-secret')
        for supplier in [None, lambda: '', lambda: 'bad\r\ntoken', fail]:
            with self.assertRaises(IntegrationError) as ctx:
                Boundary(token_supplier=supplier, transport=lambda *a: self.fail('must deny')).exchange(Request(b''))
            self.assertEqual(ctx.exception.code, 'authentication_unavailable')
            self.assertNotIn('synthetic-secret', ''.join(traceback.format_exception(ctx.exception)))
        with self.assertRaises(IntegrationError) as ctx:
            Boundary(token_supplier=lambda: 'token', transport=fail).exchange(Request(b''))
        self.assertEqual(ctx.exception.code, 'transport_unavailable')
        self.assertNotIn('synthetic-secret', repr(ctx.exception))
        for result in [Result(True, b''), Result(600, b''), Result(200, 'bad'), {}, None]:
            with self.assertRaises(IntegrationError):
                Boundary(token_supplier=lambda: 'token', transport=lambda *a: result).exchange(Request(b''))
        for request in [{}, Request('bad')]:
            with self.assertRaises(IntegrationError): Boundary().exchange(request)

if __name__ == '__main__': unittest.main()
