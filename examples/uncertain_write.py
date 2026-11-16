"""Deterministic public-package example. No HTTP client or real credentials."""
import json
from meetup_integration import EventCreateRequest, MeetupApiError, MeetupClient


def main():
    submitted = []
    token_calls = []

    def token_supplier():
        token_calls.append(1)
        return "synthetic-access-token"

    def transport(request, token):
        assert token == "synthetic-access-token"
        payload = json.loads(request.body)
        assert payload['query'].lstrip().startswith('mutation')
        assert payload['variables']['input']['groupUrlname'] == 'synthetic-group'
        # Simulate the remote side accepting a write, then losing its reply.
        submitted.append(payload['variables']['input'])
        raise TimeoutError('synthetic lost reply')

    client = MeetupClient(token_supplier=token_supplier, transport=transport)
    request = EventCreateRequest(
        group_url_name='synthetic-group', title='Offline example',
        description='Synthetic example only', start_date_time='2026-12-01T18:00:00Z',
        duration='PT1H', venue_id='synthetic-venue', how_to_find_us='',
        publish_status='DRAFT',
    )
    try:
        client.create_event(request)
    except MeetupApiError as error:
        assert error.code == 'mutation_uncertain'
        assert error.outcome_unknown is True
        assert len(submitted) == len(token_calls) == 1
        print(f'{error.code}: outcome_unknown={error.outcome_unknown}; attempts={len(submitted)}; no retry')
        # The caller must retain its claim and reconcile exact remote identity.
        # This example has no remote readback; leave the outcome unresolved.
        return
    raise AssertionError('Expected an uncertain write')


if __name__ == '__main__':
    main()
