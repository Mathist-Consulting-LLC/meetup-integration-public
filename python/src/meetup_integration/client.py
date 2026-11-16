"""Provider mappings extracted from calendar source 5da23e5; caller owns policy."""
from __future__ import annotations
from dataclasses import dataclass
import json
import re
from typing import Any
from . import Boundary, Request, Result, IntegrationError
from .errors import MeetupApiError
from .topics import MeetupTopicCatalog, TopicReviewRequired, canonical_topics
from .images import ImageSupport
from .images import EVENT_IMAGE_CONTENT_TYPES
from functools import wraps
import time


def _validate_response(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "edges":
                if not isinstance(child, list) or any(
                    not isinstance(edge, dict) or not isinstance(edge.get("node"), dict)
                    for edge in child
                ):
                    raise ValueError()
            if key == "pageInfo" and (
                not isinstance(child, dict) or type(child.get("hasNextPage")) is not bool
                or (child["hasNextPage"] and not isinstance(child.get("endCursor"), str))
            ):
                raise ValueError()
            if key in ("events", "venues") and (
                not isinstance(child, dict) or not {"edges", "pageInfo"} <= child.keys()
            ):
                raise ValueError()
            if key in ("eventsSearch", "groupsSearch", "eventSearch", "suggestTopics", "topics") and (
                not isinstance(child, dict) or "edges" not in child
            ):
                raise ValueError()
            _validate_response(child)
    elif isinstance(value, list):
        for child in value:
            _validate_response(child)


def _safe_operation(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        error = None
        mutation = method.__name__ in ("create_event", "update_event", "cancel_event")
        try:
            return method(self, *args, **kwargs)
        except MeetupApiError as exc:
            error = (exc.code, exc.outcome_unknown)
        except Exception:
            error = ("mutation_uncertain" if mutation else "response_invalid", mutation)
        if mutation and error[0] == "response_invalid":
            error = ("mutation_uncertain", True)
        raise MeetupApiError(error[0], outcome_unknown=error[1])
    return call

@dataclass(frozen=True)
class MeetupVenue:
    id: str
    name: str
    address: str = ''
    city: str = ''
    state: str = ''
    postal_code: str = ''


@dataclass(frozen=True)
class MeetupEvent:
    id: str
    title: str
    event_url: str
    date_time: str
    end_time: str
    duration: str
    status: str
    group_url_name: str
    venue: MeetupVenue | None
    how_to_find_us: str
    description: str
    network_event_id: str = ''
    network_group_count: int = 0
    group_id: str = ''
    group_name: str = ''
    created_time: str = ''
    rsvp_open_time: str = ''
    rsvp_limit: int | None = None
    rsvp_question: str = ''
    rsvp_question_required: bool = False
    registration_form_enabled: bool = False
    featured_photo_id: str = ''
    featured_photo_base_url: str = ''


@dataclass(frozen=True)
class EventCreateRequest:
    group_url_name: str
    title: str
    description: str
    start_date_time: str
    duration: str
    venue_id: str
    how_to_find_us: str
    publish_status: str
    attendee_limit: int | None = None
    rsvp_open_time: str = ''
    image_id: str = ''
    network_from_event_id: str = ''
    timezone: str = ''
    rsvp_question: str = ''
    topic_ids: tuple[str, ...] = ()
    topic_selections: tuple[dict[str, str], ...] = ()


class MeetupClient(ImageSupport):
    def __init__(self, *, token_supplier=None, transport=None,
                 image_transport=None, resolver=None, sleep=time.sleep, max_pages=1000):
        if type(max_pages) is not int or not 1 <= max_pages <= 10000:
            raise MeetupApiError("invalid_request")
        self._boundary = Boundary(token_supplier=token_supplier, transport=transport)
        self._image_transport = image_transport
        self._resolver = resolver
        self._sleep = sleep
        self._max_pages = max_pages
        self._topic_catalog = MeetupTopicCatalog(self._graphql)

    def _graphql(self, query: str, *, variables=None):
        mutation = query.lstrip().startswith("mutation")
        payload = {"query": query}
        if variables is not None:
            payload["variables"] = variables
        result = None
        code = None
        try:
            result = self._boundary.exchange(Request(json.dumps(payload).encode()))
        except IntegrationError as exc:
            code = exc.code
        if code:
            if code == "authentication_unavailable":
                raise MeetupApiError(code)
            raise MeetupApiError("mutation_uncertain" if mutation else "transport_unavailable")
        codes = {401: "authentication_failed", 403: "permission_denied", 429: "rate_limited"}
        if result.status in codes:
            raise MeetupApiError(codes[result.status], outcome_unknown=mutation)
        if not 200 <= result.status < 300:
            raise MeetupApiError("mutation_uncertain" if mutation else "response_invalid")
        data = None
        invalid = False
        try:
            if len(result.body) > 16 * 1024 * 1024:
                raise ValueError()
            data = json.loads(result.body)
            if not isinstance(data, dict):
                raise ValueError()
            errors = data.get("errors")
            if errors:
                if not isinstance(errors, list):
                    raise ValueError()
                extensions = {e.get("extensions", {}).get("code") for e in errors if isinstance(e, dict)}
                for provider, public in (("UNAUTHENTICATED", "authentication_failed"),
                                         ("FORBIDDEN", "permission_denied"),
                                         ("RATE_LIMITED", "rate_limited")):
                    if provider in extensions:
                        code = public
                if code is None:
                    code = "mutation_uncertain" if mutation else "schema_unsupported"
            else:
                root = data.get("data")
                if not isinstance(root, dict) or not root:
                    raise ValueError()
                operation = next((name for name in (
                    "createGroupEventPhoto", "createEvent", "editEvent", "deleteEvent",
                    "__type", "groupByUrlname", "proNetwork", "eventSearch", "suggestTopics",
                    "event", "self") if re.search(r"\b" + name + r"\b", query)), None)
                if operation not in root:
                    raise ValueError()
                node = root[operation]
                if operation not in ("event", "__type") and not isinstance(node, dict):
                    raise ValueError()
                for key in ("eventsSearch", "groupsSearch", "events", "venues"):
                    if re.search(r"\b" + key + r"\s*\(", query) and key not in node:
                        raise ValueError()
                if mutation:
                    if operation in ("createEvent", "editEvent"):
                        if (not isinstance(node.get("event"), dict)
                                or not isinstance(node["event"].get("id"), str)
                                or not node["event"]["id"].strip()):
                            raise ValueError()
                    if operation == "deleteEvent" and node.get("errors") != []:
                        raise ValueError()
                    if node.get("errors"):
                        raise ValueError()
                    if operation == "createGroupEventPhoto" and (
                        not isinstance(node.get("photo"), dict)
                        or any(not isinstance(node["photo"].get(key), str)
                               or not node["photo"][key].strip() for key in ("id", "baseUrl"))
                        or not isinstance(node.get("uploadUrl"), str) or not node["uploadUrl"].strip()
                    ):
                        raise ValueError()
                _validate_response(root)
        except Exception:
            invalid = True
        if invalid:
            raise MeetupApiError("mutation_uncertain" if mutation else "response_invalid")
        if code:
            raise MeetupApiError(code, outcome_unknown=mutation)
        return data
    def inspect_event_topic_contract(self) -> dict[str, Any]:
        """Read-only schema probe; unsupported contracts never authorize writes."""
        return {"supported": self._topic_catalog.supported(), "provenance": "authenticated_graphql_introspection"}

    def search_event_topics(self, text: str) -> list[dict[str, str]]:
        return [{"id": topic.id, "name": topic.name} for topic in self._topic_catalog.search(text)]

    def validate_event_topics(self, selections: object) -> tuple[str, ...]:
        return self._topic_catalog.validate(canonical_topics(selections))

    def get_event_topic_ids(self, event_id: str) -> tuple[str, ...]:
        return self._topic_catalog.readback(event_id)

    def verify_auth(self) -> bool:
        data = self._graphql('query { self { id name } }')
        identity = data.get('data', {}).get('self')
        if not isinstance(identity, dict) or not isinstance(identity.get('id'), str) or not identity['id']:
            raise MeetupApiError("response_invalid")
        return True

    def inspect_network_creation_contract(self) -> dict[str, Any]:
        mutation_fields = self._introspection_fields('Mutation', 'fields')
        create_event_fields = self._introspection_fields('CreateEventInput', 'inputFields')
        rsvp_settings_fields = self._introspection_fields('RsvpSettings', 'inputFields')
        rsvp_survey_fields = self._introspection_fields('RsvpSurvey', 'inputFields')
        question_fields = self._introspection_fields('QuestionInput', 'inputFields')
        network_fields = self._introspection_fields('ProNetworkEventsInput', 'inputFields')
        mutation_names = {str(field.get('name') or '') for field in mutation_fields}
        create_event_names = {str(field.get('name') or '') for field in create_event_fields}
        network_names = {str(field.get('name') or '') for field in network_fields}
        checks = {
            'createEvent mutation is available': 'createEvent' in mutation_names,
            'removed createNetworkEventFilter mutation is absent': 'createNetworkEventFilter' not in mutation_names,
            'CreateEventInput accepts proNetworkEvents': 'proNetworkEvents' in create_event_names,
            'CreateEventInput accepts rsvpSettings': 'rsvpSettings' in create_event_names,
            'CreateEventInput accepts rsvpSurvey': 'rsvpSurvey' in create_event_names,
            'RsvpSettings accepts rsvpLimit and rsvpOpenTime': {'rsvpLimit', 'rsvpOpenTime'} <= {
                str(field.get('name') or '') for field in rsvp_settings_fields
            },
            'RsvpSurvey accepts required questions and custom rsvpQuestions': {'questions', 'rsvpQuestions'} <= {
                str(field.get('name') or '') for field in rsvp_survey_fields
            },
            'QuestionInput accepts required text questions': {'name', 'order', 'required', 'type'} <= {
                str(field.get('name') or '') for field in question_fields
            },
            'ProNetworkEventsInput accepts fromEventId': 'fromEventId' in network_names,
            'ProNetworkEventsInput accepts timezone': 'timezone' in network_names,
        }
        return {'supported': all(checks.values()), 'checks': checks}

    def _introspection_fields(self, type_name: str, field_name: str) -> list[dict[str, Any]]:
        query = (
            'query($typeName: String!) { __type(name: $typeName) { '
            + field_name
            + ' { name } } }'
        )
        data = self._graphql(query, variables={'typeName': type_name})
        type_data = data.get('data', {}).get('__type') or {}
        fields = type_data.get(field_name) or []
        return fields if isinstance(fields, list) else []

    def supports_event_images(self) -> bool:
        import importlib.util
        return (callable(self._image_transport) and callable(self._resolver)
                and importlib.util.find_spec("PIL") is not None)

    def event_image_is_readable(self, event_id: str, expected_photo_id: str) -> bool:
        event = self.get_event(event_id)
        if not event or event.featured_photo_id != str(expected_photo_id or '').strip():
            return False
        return self._meetup_photo_is_readable(event.featured_photo_id, event.featured_photo_base_url)

    def _create_group_event_photo_placeholder(self, group_url_name: str, content_type: str) -> tuple[str, str, str]:
        group_id = self._group_id_from_urlname(group_url_name)
        dollar = chr(36)
        query = (
            'mutation(' + dollar + 'input: GroupEventPhotoCreateInput!) '
            '{ createGroupEventPhoto(input: ' + dollar + 'input) '
            '{ uploadUrl photo { id baseUrl } imagePath } }'
        )
        variables = {
            'input': {
                'groupId': group_id,
                'photoType': 'GROUP_PHOTO',
                'contentType': EVENT_IMAGE_CONTENT_TYPES[content_type],
                'setAsMain': False,
            }
        }
        data = self._graphql(query, variables=variables)
        payload = data.get('data', {}).get('createGroupEventPhoto') or {}
        upload_url = str(payload.get('uploadUrl') or '').strip()
        photo_id = str((payload.get('photo') or {}).get('id') or '').strip()
        base_url = str((payload.get('photo') or {}).get('baseUrl') or '').strip()
        if not upload_url or not photo_id or not base_url:
            raise MeetupApiError("mutation_uncertain")
        return upload_url, photo_id, base_url

    def _group_id_from_urlname(self, group_url_name: str) -> str:
        dollar = chr(36)
        query = (
            'query(' + dollar + 'urlname: String!) '
            '{ groupByUrlname(urlname: ' + dollar + 'urlname) { id } }'
        )
        data = self._graphql(query, variables={'urlname': group_url_name})
        group_id = data.get('data', {}).get('groupByUrlname', {}).get('id')
        if not isinstance(group_id, str) or not group_id.strip():
            raise MeetupApiError("response_invalid")
        return group_id.strip()

    def list_network_events(self, network_url_name: str, *, first: int = 100) -> list[MeetupEvent]:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", network_url_name) or type(first) is not int or not 1 <= first <= 100:
            raise MeetupApiError("invalid_request")
        q = chr(34)
        query = (
            'query { proNetwork(urlname: ' + q + network_url_name + q + ') '
            '{ eventsSearch(input: {first: ' + str(first) + ', sort: ' + q + 'DATETIME' + q + '}) '
            '{ edges { node { id title eventUrl dateTime endTime duration status '
            'group { urlname } venue { id name address } howToFindUs description '
            'networkEvent { id groupCount } maxTickets rsvpSettings { rsvpOpenTime } '
            'rsvpQuestions { questionId text } rsvpSurveySettings { requiresProQuestionnaire } '
            'featuredEventPhoto { id baseUrl } } } } } }'
        )
        data = self._graphql(query)
        edges = data.get('data', {}).get('proNetwork', {}).get('eventsSearch', {}).get('edges', [])
        return [_event_from_node(edge['node']) for edge in edges]

    def list_group_events(
        self,
        group_url_name: str,
        *,
        after_date_time: str,
        before_date_time: str,
        first: int = 50,
    ) -> list[MeetupEvent]:
        """List an arbitrary group's upcoming and cancelled events using supported GraphQL."""
        dollar = chr(36)
        query = (
            'query(' + dollar + 'urlname: String!, ' + dollar + 'first: Int!, '
            + dollar + 'after: String, ' + dollar + 'afterDateTime: DateTime!, '
            + dollar + 'beforeDateTime: DateTime!) { '
            'groupByUrlname(urlname: ' + dollar + 'urlname) { id name urlname '
            'events(first: ' + dollar + 'first, after: ' + dollar + 'after, sort: ASC, '
            'filter: {afterDateTime: ' + dollar + 'afterDateTime, beforeDateTime: '
            + dollar + 'beforeDateTime, status: [ACTIVE, CANCELLED, CANCELLED_PERM, AUTOSCHED_CANCELLED]}) '
            '{ pageInfo { endCursor hasNextPage } edges { node { '
            'id title eventUrl dateTime endTime duration status createdTime '
            'group { id name urlname } venue { id name address } '
            'howToFindUs description maxTickets rsvpSettings { rsvpOpenTime } '
            'rsvpQuestions { questionId text } rsvpSurveySettings { requiresProQuestionnaire } '
            'featuredEventPhoto { id baseUrl } } } } } }'
        )
        events: list[MeetupEvent] = []
        cursor: str | None = None
        seen = set()
        while True:
            if len(seen) >= self._max_pages:
                raise MeetupApiError("response_invalid")
            seen.add(cursor)
            data = self._graphql(
                query,
                variables={
                    'urlname': group_url_name,
                    'first': max(1, min(int(first), 100)),
                    'after': cursor,
                    'afterDateTime': after_date_time,
                    'beforeDateTime': before_date_time,
                },
            )
            group = data.get('data', {}).get('groupByUrlname')
            if not group:
                raise MeetupApiError("response_invalid")
            connection = group.get('events') or {}
            events.extend(
                _event_from_node(edge.get('node') or {})
                for edge in connection.get('edges') or []
                if edge.get('node')
            )
            page_info = connection.get('pageInfo') or {}
            if not page_info.get('hasNextPage'):
                break
            next_cursor = str(page_info.get('endCursor') or '').strip()
            if not next_cursor or next_cursor in seen:
                raise MeetupApiError("response_invalid")
            cursor = next_cursor
        return events

    def search_venues(self, group_url_name: str, query: str, *, first: int = 25) -> list[MeetupVenue]:
        """Search group venues and nearby Meetup events without making provider writes."""
        dollar = chr(36)
        group_query = (
            'query(' + dollar + 'urlname: String!, ' + dollar + 'first: Int!, ' + dollar + 'after: String) { '
            'groupByUrlname(urlname: ' + dollar + 'urlname) { lat lon venues(first: ' + dollar
            + 'first, after: ' + dollar + 'after) { pageInfo { endCursor hasNextPage } edges { node { '
            'id name address city state postalCode } } } } }'
        )
        venues: list[MeetupVenue] = []
        cursor: str | None = None
        lat = lon = None
        seen = set()
        while True:
            if len(seen) >= self._max_pages:
                raise MeetupApiError("response_invalid")
            seen.add(cursor)
            data = self._graphql(group_query, variables={
                'urlname': group_url_name,
                'first': 100,
                'after': cursor,
            })
            group = data.get('data', {}).get('groupByUrlname')
            if not group:
                raise MeetupApiError("response_invalid")
            lat, lon = group.get('lat'), group.get('lon')
            connection = group.get('venues') or {}
            venues.extend(_venue_from_node(edge.get('node') or {}) for edge in connection.get('edges') or [])
            page_info = connection.get('pageInfo') or {}
            if not page_info.get('hasNextPage'):
                break
            next_cursor = str(page_info.get('endCursor') or '').strip()
            if not next_cursor or next_cursor in seen:
                raise MeetupApiError("response_invalid")
            cursor = next_cursor

        if lat is not None and lon is not None and query.strip():
            event_query = (
                'query(' + dollar + 'query: String!, ' + dollar + 'lat: Float!, ' + dollar
                + 'lon: Float!, ' + dollar + 'first: Int!) { eventSearch(first: ' + dollar
                + 'first, filter: {query: ' + dollar + 'query, lat: ' + dollar + 'lat, lon: '
                + dollar + 'lon, radius: 100}) { edges { node { venue { id name address city state postalCode } } } } }'
            )
            data = self._graphql(event_query, variables={
                'query': query.strip(),
                'lat': float(lat),
                'lon': float(lon),
                'first': max(1, min(int(first), 50)),
            })
            for edge in data.get('data', {}).get('eventSearch', {}).get('edges') or []:
                venue = (edge.get('node') or {}).get('venue')
                if venue:
                    venues.append(_venue_from_node(venue))

        unique: dict[str, MeetupVenue] = {}
        for venue in venues:
            if venue.id:
                unique.setdefault(venue.id, venue)
        return list(unique.values())

    def get_event(self, event_id: str) -> MeetupEvent | None:
        dollar = chr(36)
        query = (
            'query(' + dollar + 'id: ID!) { event(id: ' + dollar + 'id) '
            '{ id title eventUrl dateTime endTime duration status group { urlname } '
            'venue { id name address } howToFindUs description networkEvent { id groupCount } '
            'maxTickets rsvpSettings { rsvpOpenTime } rsvpQuestions { questionId text } '
            'rsvpSurveySettings { requiresProQuestionnaire } '
            'featuredEventPhoto { id baseUrl } } }'
        )
        data = self._graphql(query, variables={'id': event_id})
        event = data.get('data', {}).get('event')
        if event is not None and (not isinstance(event, dict) or event.get('id') != event_id):
            raise MeetupApiError("response_invalid")
        return _event_from_node(event) if event else None

    def create_event(self, request: EventCreateRequest) -> MeetupEvent:
        if request.network_from_event_id and (
            not isinstance(request.timezone, str) or not request.timezone.strip()
        ):
            raise MeetupApiError("invalid_request")
        dollar = chr(36)
        if request.topic_ids and (
            not request.topic_selections
            or self.validate_event_topics(list(request.topic_selections)) != request.topic_ids
        ):
            raise MeetupApiError("topic_unverified")
        query = (
            'mutation(' + dollar + 'input: CreateEventInput!) '
            '{ createEvent(input: ' + dollar + 'input) '
            '{ event { id title eventUrl dateTime endTime duration status group { urlname } '
            'venue { id name address } howToFindUs description featuredEventPhoto { id baseUrl } } errors { message code field } } }'
        )
        variables = {
            'input': {
                'groupUrlname': request.group_url_name,
                'title': request.title,
                'description': request.description,
                'startDateTime': request.start_date_time,
                'duration': request.duration,
                'venueId': request.venue_id,
                'howToFindUs': request.how_to_find_us,
                'publishStatus': request.publish_status,
            }
        }
        if request.rsvp_question.strip():
            variables['input']['question'] = request.rsvp_question.strip()
        rsvp_settings: dict[str, object] = {}
        if request.attendee_limit:
            rsvp_settings['rsvpLimit'] = request.attendee_limit
        if request.rsvp_open_time:
            rsvp_settings['rsvpOpenTime'] = request.rsvp_open_time
        if rsvp_settings:
            variables['input']['rsvpSettings'] = rsvp_settings
        if request.image_id:
            variables['input']['featuredPhotoId'] = request.image_id
        if request.topic_ids:
            variables['input']['topics'] = list(request.topic_ids)
        if request.network_from_event_id:
            variables['input']['proNetworkEvents'] = {
                'fromEventId': request.network_from_event_id,
                'timezone': request.timezone,
            }
        data = self._graphql(query, variables=variables)
        payload = data.get('data', {}).get('createEvent') or {}
        if payload.get('errors') or not payload.get('event'):
            raise MeetupApiError("mutation_uncertain")
        return _event_from_node(payload['event'])

    def list_network_groups(self, network_url_name: str, network_id: str = '') -> list[dict[str, str]]:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", network_url_name):
            raise MeetupApiError("invalid_request")
        q = chr(34)
        query = (
            'query { proNetwork(urlname: ' + q + network_url_name + q + ') '
            '{ id groupsSearch(input: {first: 100}) { edges { node { id urlname name } } } } }'
        )
        data = self._graphql(query)
        network = data.get('data', {}).get('proNetwork') or {}
        if network_id and str(network.get('id') or '') != network_id:
            raise MeetupApiError("response_invalid")
        edges = network.get('groupsSearch', {}).get('edges', [])
        return [
            {
                'id': str(edge.get('node', {}).get('id') or ''),
                'urlname': str(edge.get('node', {}).get('urlname') or ''),
                'name': str(edge.get('node', {}).get('name') or ''),
                'parentNetworkId': str(network.get('id') or ''),
            }
            for edge in edges
        ]

    def update_event(self, event_id: str, changes: dict[str, Any]) -> MeetupEvent:
        dollar = chr(36)
        if 'topic_ids' in changes and (
            'topic_selections' not in changes
            or self.validate_event_topics(list(changes['topic_selections'])) != tuple(changes['topic_ids'])
        ):
            raise MeetupApiError("topic_unverified")
        query = (
            'mutation(' + dollar + 'input: EditEventInput!) '
            '{ editEvent(input: ' + dollar + 'input) '
            '{ event { id title eventUrl dateTime endTime duration status group { urlname } '
            'venue { id name address } howToFindUs description maxTickets rsvpSettings { rsvpOpenTime } '
            'rsvpQuestions { questionId text } rsvpSurveySettings { requiresProQuestionnaire } '
            'featuredEventPhoto { id baseUrl } } errors { message code field } } }'
        )
        input_payload: dict[str, Any] = {'eventId': event_id}
        if changes.get('title'):
            input_payload['title'] = changes['title']
        if changes.get('description'):
            input_payload['description'] = changes['description']
        if changes.get('start_date_time'):
            input_payload['startDateTime'] = changes['start_date_time']
        if changes.get('duration'):
            input_payload['duration'] = changes['duration']
        if changes.get('how_to_find_us'):
            input_payload['howToFindUs'] = changes['how_to_find_us']
        if changes.get('venue_id'):
            input_payload['venueId'] = changes['venue_id']
        rsvp_settings: dict[str, Any] = {}
        if changes.get('rsvp_open_time'):
            rsvp_settings['rsvpOpenTime'] = changes['rsvp_open_time']
        if 'rsvp_limit' in changes:
            rsvp_settings['rsvpLimit'] = changes['rsvp_limit']
        if rsvp_settings:
            input_payload['rsvpSettings'] = rsvp_settings
        if 'rsvp_question' in changes:
            question = str(changes.get('rsvp_question') or '').strip()
            input_payload['question'] = question
            input_payload['rsvpSurvey'] = {'enabled': False}
        if changes.get('featured_photo_id'):
            input_payload['featuredPhotoId'] = changes['featured_photo_id']
        if 'topic_ids' in changes:
            input_payload['topics'] = list(changes['topic_ids'])
        data = self._graphql(query, variables={'input': input_payload})
        payload = data.get('data', {}).get('editEvent') or {}
        event = payload.get('event')
        if payload.get('errors') or not isinstance(event, dict) or event.get('id') != event_id:
            raise MeetupApiError("mutation_uncertain")
        return _event_from_node(event)

    def cancel_event(self, event_id: str, reason: str) -> None:
        dollar = chr(36)
        query = (
            'mutation(' + dollar + 'input: DeleteEventInput!) '
            '{ deleteEvent(input: ' + dollar + 'input) { errors { message code field } } }'
        )
        data = self._graphql(
            query,
            variables={'input': {'eventId': event_id, 'removeFromCalendar': False, 'updateSeries': False}},
        )
        payload = data.get('data', {}).get('deleteEvent') or {}
        errors = payload.get('errors') or []
        if errors:
            raise MeetupApiError("mutation_uncertain")


def _venue_from_node(node: dict[str, Any]) -> MeetupVenue:
    if not isinstance(node, dict) or not isinstance(node.get("id"), str) or not node["id"].strip():
        raise MeetupApiError("response_invalid")
    return MeetupVenue(
        id=str(node.get('id') or ''),
        name=str(node.get('name') or ''),
        address=str(node.get('address') or ''),
        city=str(node.get('city') or ''),
        state=str(node.get('state') or ''),
        postal_code=str(node.get('postalCode') or ''),
    )


def _event_from_node(node: dict[str, Any]) -> MeetupEvent:
    if not isinstance(node, dict) or not isinstance(node.get("id"), str) or not node["id"].strip():
        raise MeetupApiError("response_invalid")
    venue = None
    if node.get('venue'):
        venue = _venue_from_node(node['venue'])
    network_event = node.get('networkEvent') if isinstance(node.get('networkEvent'), dict) else {}
    group = node.get('group') if isinstance(node.get('group'), dict) else {}
    rsvp_settings = node.get('rsvpSettings') if isinstance(node.get('rsvpSettings'), dict) else {}
    custom_questions = node.get('rsvpQuestions') if isinstance(node.get('rsvpQuestions'), list) else []
    managed_question = next((question for question in custom_questions if isinstance(question, dict)), {})
    survey_settings = node.get('rsvpSurveySettings') if isinstance(node.get('rsvpSurveySettings'), dict) else {}
    featured_photo = node.get('featuredEventPhoto') if isinstance(node.get('featuredEventPhoto'), dict) else {}
    return MeetupEvent(
        id=str(node.get('id', '')),
        title=str(node.get('title', '')),
        event_url=str(node.get('eventUrl', '')),
        date_time=str(node.get('dateTime', '')),
        end_time=str(node.get('endTime', '')),
        duration=str(node.get('duration', '')),
        status=str(node.get('status', '')),
        group_url_name=str(group.get('urlname', '')),
        venue=venue,
        how_to_find_us=str(node.get('howToFindUs') or ''),
        description=str(node.get('description') or ''),
        network_event_id=str(network_event.get('id') or ''),
        network_group_count=int(network_event.get('groupCount') or 0),
        group_id=str(group.get('id') or ''),
        group_name=str(group.get('name') or ''),
        created_time=str(node.get('createdTime') or ''),
        rsvp_open_time=str(rsvp_settings.get('rsvpOpenTime') or node.get('rsvpOpenTime') or ''),
        rsvp_limit=(int(node['maxTickets']) if node.get('maxTickets') is not None else None),
        rsvp_question=str(managed_question.get('text') or ''),
        rsvp_question_required=bool(managed_question and survey_settings.get('requiresProQuestionnaire')),
        registration_form_enabled=bool(survey_settings.get('requiresProQuestionnaire')),
        featured_photo_id=str(featured_photo.get('id') or ''),
        featured_photo_base_url=str(featured_photo.get('baseUrl') or ''),
    )


for _name in (
    "verify_auth", "inspect_event_topic_contract", "search_event_topics",
    "validate_event_topics", "get_event_topic_ids", "inspect_network_creation_contract",
    "list_group_events", "list_network_events", "search_venues", "list_network_groups",
    "get_event", "create_event", "update_event", "cancel_event",
):
    setattr(MeetupClient, _name, _safe_operation(getattr(MeetupClient, _name)))
