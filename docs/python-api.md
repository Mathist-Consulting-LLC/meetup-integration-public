# Python API reference

Import from `meetup_integration` unless a module is shown. This inventory is derived from
current source declarations. Defaults, keyword-only arguments and record fields
are listed below; caller responsibilities are specified in [setup](setup.md).

## `meetup_integration`

[Source](../python/src/meetup_integration/__init__.py)

### `IntegrationError`

```python
IntegrationError.__init__(self, code: str)
```

### `Request`

Record fields (including shown defaults; inherited fields also apply):

```python
body: bytes = field(repr=False)
```

### `Result`

Record fields (including shown defaults; inherited fields also apply):

```python
status: int
body: bytes = field(repr=False)
```

### `TokenSupplier`

### `Transport`

```python
validate_topic(value: object) -> dict[str, str]
```

### `Boundary`

```python
Boundary.__init__(self, *, token_supplier: TokenSupplier | None=None, transport: Transport | None=None)
```

```python
Boundary.exchange(self, request: Request) -> Result
```

## `meetup_integration.client`

[Source](../python/src/meetup_integration/client.py)

### `MeetupVenue`

Record fields (including shown defaults; inherited fields also apply):

```python
id: str
name: str
address: str = ''
city: str = ''
state: str = ''
postal_code: str = ''
```

### `MeetupEvent`

Record fields (including shown defaults; inherited fields also apply):

```python
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
```

### `EventCreateRequest`

Record fields (including shown defaults; inherited fields also apply):

```python
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
```

### `MeetupClient`

```python
MeetupClient.__init__(self, *, token_supplier=None, transport=None, image_transport=None, resolver=None, sleep=time.sleep, max_pages=1000)
```

```python
MeetupClient.inspect_event_topic_contract(self) -> dict[str, Any]
```

```python
MeetupClient.search_event_topics(self, text: str) -> list[dict[str, str]]
```

```python
MeetupClient.validate_event_topics(self, selections: object) -> tuple[str, ...]
```

```python
MeetupClient.get_event_topic_ids(self, event_id: str) -> tuple[str, ...]
```

```python
MeetupClient.verify_auth(self) -> bool
```

```python
MeetupClient.inspect_network_creation_contract(self) -> dict[str, Any]
```

```python
MeetupClient.supports_event_images(self) -> bool
```

```python
MeetupClient.event_image_is_readable(self, event_id: str, expected_photo_id: str) -> bool
```

```python
MeetupClient.list_network_events(self, network_url_name: str, *, first: int=100) -> list[MeetupEvent]
```

```python
MeetupClient.list_group_events(self, group_url_name: str, *, after_date_time: str, before_date_time: str, first: int=50) -> list[MeetupEvent]
```

```python
MeetupClient.search_venues(self, group_url_name: str, query: str, *, first: int=25) -> list[MeetupVenue]
```

```python
MeetupClient.get_event(self, event_id: str) -> MeetupEvent | None
```

```python
MeetupClient.create_event(self, request: EventCreateRequest) -> MeetupEvent
```

```python
MeetupClient.list_network_groups(self, network_url_name: str, network_id: str='') -> list[dict[str, str]]
```

```python
MeetupClient.update_event(self, event_id: str, changes: dict[str, Any]) -> MeetupEvent
```

```python
MeetupClient.cancel_event(self, event_id: str, reason: str) -> None
```

## `meetup_integration.contract_check`

[Source](../python/src/meetup_integration/contract_check.py)

```python
check_snapshot(snapshot)
```

```python
synthetic_snapshot()
```

```python
main(argv=None)
```

## `meetup_integration.errors`

[Source](../python/src/meetup_integration/errors.py)

### `MeetupApiError`

```python
MeetupApiError.__init__(self, code: str, *, outcome_unknown: bool=False)
```

## `meetup_integration.images`

[Source](../python/src/meetup_integration/images.py)

### `ImageRequest`

Record fields (including shown defaults; inherited fields also apply):

```python
url: str = field(repr=False)
method: str
headers: Mapping[str, str]
addresses: tuple[str, ...]
body: bytes = field(default=b'', repr=False)
max_bytes: int = MAX_EVENT_IMAGE_BYTES
timeout_seconds: int = 30
```

### `ImageResult`

Record fields (including shown defaults; inherited fields also apply):

```python
status: int
body: bytes = field(repr=False)
content_type: str = ''
content_length: str = ''
redirected: bool = False
```

```python
validate_image_url(url, resolver)
```

```python
normalize_event_image(body: bytes, content_type: str) -> tuple[bytes, str]
```

### `ImageSupport`

```python
ImageSupport.upload_event_image_from_url(self, group_url_name: str, image_url: str) -> str
```

## `meetup_integration.topics`

[Source](../python/src/meetup_integration/topics.py)

### `TopicReviewRequired`

```python
TopicReviewRequired.__init__(self, *args)
```

### `Topic`

Record fields (including shown defaults; inherited fields also apply):

```python
id: str
name: str
```

```python
canonical_topics(value: object) -> tuple[Topic, ...]
```

### `MeetupTopicCatalog`

```python
MeetupTopicCatalog.__init__(self, graphql: Callable[..., dict[str, Any]], *, ttl_seconds: int=300)
```

```python
MeetupTopicCatalog.supported(self, *, refresh: bool=False) -> bool
```

```python
MeetupTopicCatalog.search(self, text: str) -> tuple[Topic, ...]
```

```python
MeetupTopicCatalog.validate(self, topics: tuple[Topic, ...]) -> tuple[str, ...]
```

```python
MeetupTopicCatalog.readback(self, event_id: str) -> tuple[str, ...]
```
