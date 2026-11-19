"""Offline paged importer using only the installed public package."""
import json
from meetup_integration import MeetupClient, MeetupApiError, Result

seen = []
def transport(request, token):
    assert token == 'synthetic-token'
    payload = json.loads(request.body)
    cursor = payload['variables']['after']
    seen.append(cursor)
    assert len(seen) <= 2
    identity = 'event-one' if cursor is None else 'event-two'
    node = {'id': identity, 'title': 'Example session',
            'dateTime': '2026-12-01T18:00:00Z', 'endTime': '2026-12-01T19:00:00Z',
            'group': {'urlname': 'example-group'}}
    connection = {'edges': [{'node': node}],
                  'pageInfo': {'hasNextPage': cursor is None, 'endCursor': 'page-two'}}
    return Result(200, json.dumps({'data': {'groupByUrlname': {'events': connection}}}).encode())

client = MeetupClient(token_supplier=lambda: 'synthetic-token', transport=transport, max_pages=2)
events = client.list_group_events('example-group', after_date_time='2026-12-01T00:00:00Z',
                                  before_date_time='2026-12-02T00:00:00Z')
assert [e.id for e in events] == ['event-one', 'event-two']
assert seen == [None, 'page-two']
# This list represents caller import records; production persistence belongs to the caller.
print('imported=' + ','.join(e.id for e in events) + '; pages=' + str(len(seen)))
denied = MeetupClient(token_supplier=lambda: 'synthetic-token',
                      transport=lambda request, token: Result(403, b'{}'))
try:
    denied.verify_auth()
except MeetupApiError as error:
    assert error.code == 'permission_denied' and not error.outcome_unknown
    print('read failure=' + error.code + '; no retry')
else:
    raise AssertionError('Expected safe read failure')
