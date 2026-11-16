"""Provider-only ports of source test_meetup_api.py at 5da23e5 (synthetic data)."""
import unittest
from unittest.mock import patch
from meetup_integration import MeetupClient, MeetupEvent, MeetupVenue, MeetupApiError, EventCreateRequest
DEFAULT_RSVP_QUESTION = 'Synthetic question?'
class PortedProviderTests(unittest.TestCase):
    def test_cancel_event_sends_attendee_reason(self) -> None:
        client = MeetupClient(token_supplier=lambda: "synthetic", transport=lambda *args: None)
        calls = []

        def fake_graphql(query, *, variables=None):
            calls.append({'query': query, 'variables': variables})
            if 'deleteEvent' in query:
                return {'data': {'deleteEvent': {'errors': []}}}
            return {}

        with patch.object(client, '_graphql', side_effect=fake_graphql):
            client.cancel_event('event-123', 'Host is ill.')

        self.assertIn('deleteEvent', calls[0]['query'])
        self.assertEqual(calls[0]['variables']['input'], {
            'eventId': 'event-123', 'removeFromCalendar': False, 'updateSeries': False,
        })

    def test_group_event_listing_paginates_with_supported_horizon_filter(self) -> None:
        client = MeetupClient(token_supplier=lambda: "synthetic", transport=lambda *args: None)
        calls = []

        def fake_graphql(query, *, variables=None):
            calls.append({"query": query, "variables": variables})
            cursor = variables["after"]
            node = {
                "id": "event-1" if cursor is None else "event-2",
                "title": "Photo walk",
                "eventUrl": "https://www.meetup.com/queer-photography/events/event/",
                "dateTime": "2026-08-05T18:00:00-06:00",
                "endTime": "2026-08-05T20:00:00-06:00",
                "duration": "PT2H",
                "status": "ACTIVE",
                "createdTime": "2026-07-01T00:00:00Z",
                "group": {
                    "id": "group-id",
                    "name": "Queer Photography",
                    "urlname": "queer-photography",
                },
                "venue": None,
                "howToFindUs": "",
                "description": "Bring a camera",
                "rsvpQuestions": [{"questionId": "q-1", "text": "Legacy form question"}],
                "rsvpSurveySettings": {"requiresProQuestionnaire": True},
            }
            return {
                "data": {
                    "groupByUrlname": {
                        "events": {
                            "pageInfo": {
                                "hasNextPage": cursor is None,
                                "endCursor": "next" if cursor is None else None,
                            },
                            "edges": [{"node": node}],
                        }
                    }
                }
            }

        with patch.object(client, "_graphql", side_effect=fake_graphql):
            events = client.list_group_events(
                "queer-photography",
                after_date_time="2026-07-29T00:00:00Z",
                before_date_time="2026-09-09T00:00:00Z",
            )

        self.assertEqual([event.id for event in events], ["event-1", "event-2"])
        self.assertEqual([call["variables"]["after"] for call in calls], [None, "next"])
        self.assertIn("afterDateTime", calls[0]["query"])
        self.assertIn("CANCELLED", calls[0]["query"])
        self.assertIn("maxTickets", calls[0]["query"])
        self.assertIn("rsvpQuestions { questionId text }", calls[0]["query"])
        self.assertNotIn("rsvpSettings { rsvpLimit", calls[0]["query"])
        self.assertNotIn("rsvpSurvey {", calls[0]["query"])
        self.assertEqual(events[0].group_name, "Queer Photography")
        self.assertEqual(events[0].rsvp_question, "Legacy form question")
        self.assertTrue(events[0].registration_form_enabled)

    def test_venue_search_combines_group_venues_and_nearby_event_results(self) -> None:
        client = MeetupClient(token_supplier=lambda: "synthetic", transport=lambda *args: None)
        calls = []

        def fake_graphql(query, *, variables=None):
            calls.append({'query': query, 'variables': variables})
            if 'groupByUrlname' in query:
                return {'data': {'groupByUrlname': {
                    'lat': 39.72, 'lon': -104.90,
                    'venues': {'pageInfo': {'hasNextPage': False, 'endCursor': None}, 'edges': [
                        {'node': {'id': 'group-venue', 'name': 'Saved Place', 'address': '1 Main St', 'city': 'Denver', 'state': 'CO', 'postalCode': '80202'}},
                    ]},
                }}}
            return {'data': {'eventSearch': {'edges': [
                {'node': {'venue': {'id': 'museum-venue', 'name': 'Example Aviation Museum', 'address': '10 Fixture Avenue', 'city': 'Denver', 'state': 'CO', 'postalCode': '80230'}}},
                {'node': {'venue': {'id': 'museum-venue', 'name': 'Example Aviation Museum', 'address': '10 Fixture Avenue'}}},
            ]}}}

        with patch.object(client, '_graphql', side_effect=fake_graphql):
            venues = client.search_venues('example-group', 'Example Aviation Museum')

        self.assertEqual([venue.id for venue in venues], ['group-venue', 'museum-venue'])
        self.assertEqual(venues[1].postal_code, '80230')
        self.assertIn('venues(first:', calls[0]['query'])
        self.assertIn('eventSearch', calls[1]['query'])
        self.assertEqual(calls[1]['variables']['query'], 'Example Aviation Museum')
        self.assertEqual(calls[1]['variables']['lat'], 39.72)
        self.assertEqual(calls[1]['variables']['lon'], -104.90)

    def test_network_contract_check_uses_introspection_without_provider_writes(self) -> None:
        client = MeetupClient(token_supplier=lambda: "synthetic", transport=lambda *args: None)
        calls = []

        def fake_graphql(query, *, variables=None):
            calls.append({'query': query, 'variables': variables})
            fields = {
                'Mutation': ['createEvent', 'editEvent'],
                'CreateEventInput': ['groupUrlname', 'proNetworkEvents', 'rsvpSettings', 'rsvpSurvey'],
                'RsvpSettings': ['rsvpLimit', 'rsvpOpenTime'],
                'RsvpSurvey': ['questions', 'rsvpQuestions'],
                'QuestionInput': ['name', 'order', 'required', 'type'],
                'ProNetworkEventsInput': ['fromEventId', 'timezone'],
            }[variables['typeName']]
            field_name = 'fields' if variables['typeName'] == 'Mutation' else 'inputFields'
            return {'data': {'__type': {field_name: [{'name': name} for name in fields]}}}

        with patch.object(client, '_graphql', side_effect=fake_graphql):
            result = client.inspect_network_creation_contract()

        self.assertTrue(result['supported'])
        self.assertEqual(len(calls), 6)
        self.assertTrue(all('mutation' not in call['query'].lower() for call in calls))

    def test_network_contract_check_rejects_obsolete_or_missing_schema(self) -> None:
        client = MeetupClient(token_supplier=lambda: "synthetic", transport=lambda *args: None)

        def fake_graphql(_query, *, variables=None):
            fields = {
                'Mutation': ['createEvent', 'createNetworkEventFilter'],
                'CreateEventInput': ['groupUrlname'],
                'RsvpSettings': ['rsvpLimit'],
                'RsvpSurvey': [],
                'QuestionInput': ['name'],
                'ProNetworkEventsInput': ['filterId', 'timezone'],
            }[variables['typeName']]
            field_name = 'fields' if variables['typeName'] == 'Mutation' else 'inputFields'
            return {'data': {'__type': {field_name: [{'name': name} for name in fields]}}}

        with patch.object(client, '_graphql', side_effect=fake_graphql):
            result = client.inspect_network_creation_contract()

        self.assertFalse(result['supported'])
        self.assertFalse(result['checks']['removed createNetworkEventFilter mutation is absent'])
        self.assertFalse(result['checks']['ProNetworkEventsInput accepts fromEventId'])

    def test_create_event_sends_rsvp_limit_and_open_time_inside_rsvp_settings(self) -> None:
        client = RecordingMeetupClient()

        client.create_event(EventCreateRequest(publish_status="DRAFT",
            group_url_name='one',
            title='Event',
            description='Description',
            start_date_time='2026-07-02T14:00:00-06:00',
            duration='PT1H30M',
            venue_id='venue',
            how_to_find_us='Room',
            attendee_limit=8,
            rsvp_open_time='2026-06-25T14:00:00-06:00',
            rsvp_question=DEFAULT_RSVP_QUESTION,
        ))

        payload = client.calls[0]['variables']['input']
        self.assertEqual(payload['rsvpSettings'], {'rsvpLimit': 8, 'rsvpOpenTime': '2026-06-25T14:00:00-06:00'})
        self.assertNotIn('attendeeLimit', payload)
        self.assertNotIn('rsvpCloseTime', payload['rsvpSettings'])
        self.assertEqual(payload['question'], DEFAULT_RSVP_QUESTION)
        self.assertNotIn('rsvpSurvey', payload)

    def test_create_event_omits_rsvp_survey_when_question_is_not_required(self) -> None:
        client = RecordingMeetupClient()

        client.create_event(EventCreateRequest(publish_status="DRAFT",
            group_url_name='one',
            title='Event',
            description='Description',
            start_date_time='2026-07-02T14:00:00-06:00',
            duration='PT1H30M',
            venue_id='venue',
            how_to_find_us='Room',
            attendee_limit=8,
        ))

        self.assertNotIn('question', client.calls[0]['variables']['input'])

    def test_update_event_sends_venue_limit_and_question_contract(self) -> None:
        client = RecordingMeetupClient()

        client.update_event('event-1', {
            'venue_id': 'venue-2',
            'rsvp_limit': 12,
            'rsvp_question': 'What support would help?',
        })

        payload = client.calls[0]['variables']['input']
        self.assertEqual(payload['venueId'], 'venue-2')
        self.assertEqual(payload['rsvpSettings'], {'rsvpLimit': 12})
        self.assertEqual(payload['question'], 'What support would help?')
        self.assertEqual(payload['rsvpSurvey'], {'enabled': False})

    def test_update_event_clears_question_when_removed(self) -> None:
        client = RecordingMeetupClient()

        client.update_event('event-1', {'rsvp_question': ''})

        self.assertEqual(client.calls[0]['variables']['input']['question'], '')
        self.assertEqual(client.calls[0]['variables']['input']['rsvpSurvey'], {'enabled': False})

    def test_create_event_omits_rsvp_limit_when_none_is_configured(self) -> None:
        client = RecordingMeetupClient()

        client.create_event(EventCreateRequest(publish_status="DRAFT",
            group_url_name='one',
            title='Event',
            description='Description',
            start_date_time='2026-07-02T14:00:00-06:00',
            duration='PT1H30M',
            venue_id='venue',
            how_to_find_us='Room',
        ))

        self.assertNotIn('rsvpSettings', client.calls[0]['variables']['input'])

    def test_create_event_sends_configured_featured_photo_id(self) -> None:
        client = RecordingMeetupClient()

        client.create_event(EventCreateRequest(publish_status="DRAFT",
            group_url_name='one',
            title='Event',
            description='Description',
            start_date_time='2026-07-02T14:00:00-06:00',
            duration='PT1H30M',
            venue_id='venue',
            how_to_find_us='Room',
            attendee_limit=8,
            image_id='photo-123',
        ))

        payload = client.calls[0]['variables']['input']
        self.assertEqual(payload['featuredPhotoId'], 'photo-123')

    def test_create_network_event_copies_verified_network_propagation_through_create_event(self) -> None:
        client = RecordingMeetupClient()

        client.create_event(EventCreateRequest(publish_status="DRAFT",
            group_url_name='one',
            title='Network Event',
            description='Description',
            start_date_time='2026-07-02T14:00:00-06:00',
            duration='PT1H30M',
            venue_id='venue',
            how_to_find_us='Room',
            attendee_limit=8,
            network_from_event_id='template-event-1',
            timezone='America/Denver',
        ))

        self.assertEqual(len(client.calls), 1)
        create_call = client.calls[0]
        self.assertIn('createEvent', create_call['query'])
        self.assertNotIn('createNetworkEventFilter', create_call['query'])
        create_input = create_call['variables']['input']
        self.assertEqual(create_input['proNetworkEvents'], {'fromEventId': 'template-event-1', 'timezone': 'America/Denver'})
        self.assertEqual(create_input['groupUrlname'], 'one')
        self.assertEqual(create_input['rsvpSettings'], {'rsvpLimit': 8})
        self.assertNotIn('attendeeLimit', create_input)

    def test_update_event_uses_live_edit_event_contract(self) -> None:
        client = RecordingMeetupClient()

        updated = client.update_event(
            'event-1',
            {
                'title': 'Updated Event',
                'description': '<p>Updated description</p>',
                'start_date_time': '2026-07-02T15:00:00-06:00',
                'duration': 'PT2H',
                'how_to_find_us': 'Study Room 1.',
            },
        )

        call = client.calls[0]
        self.assertIn('EditEventInput', call['query'])
        self.assertIn('editEvent(input:', call['query'])
        self.assertNotIn('UpdateEventInput', call['query'])
        self.assertNotIn('updateEvent(input:', call['query'])
        self.assertEqual(call['variables']['input'], {
            'eventId': 'event-1',
            'title': 'Updated Event',
            'description': '<p>Updated description</p>',
            'startDateTime': '2026-07-02T15:00:00-06:00',
            'duration': 'PT2H',
            'howToFindUs': 'Study Room 1.',
        })
        self.assertEqual(updated.title, 'Updated Event')

    def test_update_event_sends_rsvp_open_time_without_close_time(self) -> None:
        client = RecordingMeetupClient()

        client.update_event('event-1', {'rsvp_open_time': '2026-06-25T14:00:00-06:00'})

        input_payload = client.calls[0]['variables']['input']
        self.assertEqual(input_payload['rsvpSettings'], {'rsvpOpenTime': '2026-06-25T14:00:00-06:00'})
        self.assertNotIn('rsvpCloseTime', input_payload['rsvpSettings'])

    def test_update_event_does_not_invent_unverified_host_field(self) -> None:
        client = RecordingMeetupClient()

        client.update_event('event-1', {'meetup_event_host_id': 'member-123'})

        input_payload = client.calls[0]['variables']['input']
        self.assertEqual(input_payload, {'eventId': 'event-1'})

    def test_get_event_uses_direct_event_query(self) -> None:
        client = RecordingMeetupClient()

        event = client.get_event('event-1')

        call = client.calls[0]
        self.assertIn('event(id:', call['query'])
        self.assertEqual(call['variables'], {'id': 'event-1'})
        self.assertIsNotNone(event)
        self.assertEqual(event.id, 'event-1')


class RecordingMeetupClient:
    def __init__(self) -> None:
        from meetup_integration import MeetupClient

        self._client = MeetupClient(token_supplier=lambda: "synthetic", transport=lambda *args: None)
        self.calls = []

    def create_event(self, request: EventCreateRequest) -> MeetupEvent:
        from meetup_integration import MeetupClient

        original = MeetupClient._graphql
        def fake_graphql(_client, query, *, variables=None):
            self.calls.append({'query': query, 'variables': variables})
            return {'data': {'createEvent': {'event': {
                'id': 'created',
                'title': request.title,
                'eventUrl': 'https://www.meetup.com/one/events/created/',
                'dateTime': request.start_date_time,
                'endTime': '',
                'duration': request.duration,
                'status': 'ACTIVE',
                'group': {'urlname': request.group_url_name},
                'venue': {'id': request.venue_id, 'name': 'Venue', 'address': ''},
                'howToFindUs': request.how_to_find_us,
                'description': request.description,
            }, 'errors': []}}}
        try:
            MeetupClient._graphql = fake_graphql
            return self._client.create_event(request)
        finally:
            MeetupClient._graphql = original

    def update_event(self, event_id: str, changes: dict[str, str]) -> MeetupEvent:
        from meetup_integration import MeetupClient

        original = MeetupClient._graphql

        def fake_graphql(_client, query, *, variables=None):
            self.calls.append({'query': query, 'variables': variables})
            return {'data': {'editEvent': {'event': {
                'id': event_id,
                'title': changes.get('title', 'Event'),
                'eventUrl': f'https://www.meetup.com/one/events/{event_id}/',
                'dateTime': changes.get('start_date_time', '2026-07-02T14:00:00-06:00'),
                'endTime': '',
                'duration': changes.get('duration', 'PT1H30M'),
                'status': 'ACTIVE',
                'group': {'urlname': 'one'},
                'venue': {'id': 'venue', 'name': 'Venue', 'address': ''},
                'howToFindUs': changes.get('how_to_find_us', ''),
                'description': changes.get('description', ''),
            }, 'errors': []}}}

        try:
            MeetupClient._graphql = fake_graphql
            return self._client.update_event(event_id, changes)
        finally:
            MeetupClient._graphql = original

    def get_event(self, event_id: str) -> MeetupEvent | None:
        from meetup_integration import MeetupClient

        original = MeetupClient._graphql

        def fake_graphql(_client, query, *, variables=None):
            self.calls.append({'query': query, 'variables': variables})
            return {'data': {'event': {
                'id': event_id,
                'title': 'Event',
                'eventUrl': f'https://www.meetup.com/one/events/{event_id}/',
                'dateTime': '2026-07-02T14:00:00-06:00',
                'endTime': '',
                'duration': 'PT1H30M',
                'status': 'ACTIVE',
                'group': {'urlname': 'one'},
                'venue': {'id': 'venue', 'name': 'Venue', 'address': ''},
                'howToFindUs': '',
                'description': 'Description',
            }}}

        try:
            MeetupClient._graphql = fake_graphql
            return self._client.get_event(event_id)
        finally:
            MeetupClient._graphql = original
