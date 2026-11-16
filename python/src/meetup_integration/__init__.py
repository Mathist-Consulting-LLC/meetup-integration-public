"""Caller-injected Meetup provider and offline interfaces."""
from dataclasses import dataclass, field
from typing import Callable, Protocol

_MESSAGES = {
    "invalid_contract": "Invalid offline contract.",
    "authentication_unavailable": "Access token unavailable.",
    "transport_unavailable": "Caller transport unavailable.",
}

class IntegrationError(RuntimeError):
    """Safe diagnostic: never contains caller data or underlying exceptions."""
    def __init__(self, code: str):
        if type(code) is not str or code not in _MESSAGES:
            code = "invalid_contract"
        self.code = code
        super().__init__(_MESSAGES[code])

@dataclass(frozen=True)
class Request:
    """Opaque bytes for a caller transport; no URL or provider operation implied."""
    body: bytes = field(repr=False)

@dataclass(frozen=True)
class Result:
    status: int
    body: bytes = field(repr=False)

class TokenSupplier(Protocol):
    def __call__(self) -> str: ...

class Transport(Protocol):
    def __call__(self, request: Request, token: str) -> Result: ...

def validate_topic(value: object) -> dict[str, str]:
    """Validate synthetic neutral identity; not authenticated catalog evidence."""
    if type(value) is not dict or set(value) != {"id", "name"}:
        raise IntegrationError("invalid_contract")
    if any(type(value[k]) is not str or not value[k].strip() or
           value[k] != value[k].strip() or len(value[k]) > limit
           for k, limit in (("id", 128), ("name", 160))):
        raise IntegrationError("invalid_contract")
    return dict(value)

class Boundary:
    """Runs only caller code. Construction does not supply network defaults."""
    def __init__(self, *, token_supplier: TokenSupplier | None = None,
                 transport: Transport | None = None):
        self._token_supplier = token_supplier
        self._transport = transport

    def exchange(self, request: Request) -> Result:
        if type(request) is not Request or type(request.body) is not bytes:
            raise IntegrationError("invalid_contract")
        if not callable(self._transport):
            raise IntegrationError("transport_unavailable")
        token = None
        try:
            token = self._token_supplier() if callable(self._token_supplier) else None
        except Exception:
            pass
        if type(token) is not str or not token or any(ord(c) < 33 or ord(c) > 126 for c in token):
            raise IntegrationError("authentication_unavailable")
        result = None
        failed = False
        try:
            result = self._transport(request, token)
        except Exception:
            failed = True
        if failed:
            raise IntegrationError("transport_unavailable")
        if (type(result) is not Result or type(result.status) is not int
                or not 100 <= result.status <= 599 or type(result.body) is not bytes):
            raise IntegrationError("invalid_contract")
        return result

__all__ = ["Boundary", "Request", "Result", "IntegrationError", "TokenSupplier", "Transport", "validate_topic"]

from .client import MeetupClient, MeetupEvent, MeetupVenue, EventCreateRequest
from .errors import MeetupApiError
from .images import ImageRequest, ImageResult, normalize_event_image
from .topics import MeetupTopicCatalog, Topic, TopicReviewRequired, canonical_topics

__all__ += ["MeetupClient", "MeetupEvent", "MeetupVenue", "EventCreateRequest",
            "MeetupApiError", "ImageRequest", "ImageResult", "normalize_event_image",
            "MeetupTopicCatalog", "Topic", "TopicReviewRequired", "canonical_topics"]
