"""Authenticated provider topic mechanics; ranking/private-event policy excluded."""
from __future__ import annotations
from dataclasses import dataclass
import re
from time import monotonic
from typing import Any, Callable
from .errors import MeetupApiError
class TopicReviewRequired(MeetupApiError):
    def __init__(self, *args):
        super().__init__('topic_unverified')
_REF = "kind name ofType { kind name ofType { kind name ofType { kind name } } }"
def _words(value: str) -> list[str]:
    # Lexical prefixes for identity revalidation, not recommendation ranking.
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9+#/-]*", value)

@dataclass(frozen=True)
class Topic:
    id: str
    name: str


def canonical_topics(value: object) -> tuple[Topic, ...]:
    if not isinstance(value, list) or len(value) > 5:
        raise TopicReviewRequired("Meetup topics require up to five canonical provider IDs and names.")
    topics: list[Topic] = []
    for entry in value:
        if not isinstance(entry, dict):
            raise TopicReviewRequired("Meetup topic selection has no canonical provider identity.")
        identifier, name = entry.get("id"), entry.get("name")
        if (not isinstance(identifier, str) or not identifier.strip() or len(identifier.strip()) > 128
                or not isinstance(name, str) or not name.strip() or len(name.strip()) > 160):
            raise TopicReviewRequired("Meetup topic selection has no canonical provider identity.")
        topics.append(Topic(identifier.strip(), name.strip()))
    if len({topic.id for topic in topics}) != len(topics):
        raise TopicReviewRequired("Meetup topic selection contains duplicate provider IDs.")
    return tuple(topics)


def _named(ref: Any) -> str:
    while isinstance(ref, dict):
        if ref.get("name"):
            return str(ref["name"])
        ref = ref.get("ofType")
    return ""


def _is_id_list(ref: Any) -> bool:
    while isinstance(ref, dict) and ref.get("kind") == "NON_NULL":
        ref = ref.get("ofType")
    return isinstance(ref, dict) and ref.get("kind") == "LIST" and _named(ref.get("ofType")) == "ID"


def _is_topic_list(ref: Any) -> bool:
    while isinstance(ref, dict) and ref.get("kind") == "NON_NULL":
        ref = ref.get("ofType")
    return isinstance(ref, dict) and ref.get("kind") == "LIST" and _named(ref.get("ofType")) == "Topic"


def _is_list_of(ref: Any, type_name: str) -> bool:
    while isinstance(ref, dict) and ref.get("kind") == "NON_NULL":
        ref = ref.get("ofType")
    return isinstance(ref, dict) and ref.get("kind") == "LIST" and _named(ref.get("ofType")) == type_name


class MeetupTopicCatalog:
    def __init__(self, graphql: Callable[..., dict[str, Any]], *, ttl_seconds: int = 300):
        self._graphql = graphql
        self._ttl = ttl_seconds
        self._capability: tuple[float, bool] | None = None
        self._cache: dict[str, tuple[float, tuple[Topic, ...]]] = {}

    def _query(self, query: str, *, variables: dict[str, str]) -> dict[str, Any]:
        response = self._graphql(query, variables=variables)
        if not isinstance(response, dict) or response.get("errors"):
            raise TopicReviewRequired("Meetup topic provider returned an incomplete response; review manually.")
        return response

    def _fields(self, type_name: str, part: str) -> list[dict[str, Any]]:
        data = self._query(
            "query($typeName: String!) { __type(name: $typeName) { "
            + part + " { name type { " + _REF + " } "
            + ("args { name type { " + _REF + " } } " if part == "fields" else "")
            + "} } }",
            variables={"typeName": type_name},
        )
        value = (data.get("data") or {}).get("__type") or {}
        fields = value.get(part)
        return fields if isinstance(fields, list) else []

    def supported(self, *, refresh: bool = False) -> bool:
        now = monotonic()
        if not refresh and self._capability and self._capability[0] > now:
            return self._capability[1]
        if refresh:
            self._capability = None
        try:
            query = {f.get("name"): f for f in self._fields("Query", "fields")}
            mutation = {f.get("name"): f for f in self._fields("Mutation", "fields")}
            event = {f.get("name"): f for f in self._fields("Event", "fields")}
            topic = {f.get("name"): f for f in self._fields("Topic", "fields")}
            connection = {f.get("name"): f for f in self._fields("TopicsConnection", "fields")}
            edge = {f.get("name"): f for f in self._fields("TopicEdge", "fields")}
            create = {f.get("name"): f for f in self._fields("CreateEventInput", "inputFields")}
            edit = {f.get("name"): f for f in self._fields("EditEventInput", "inputFields")}
            catalog = query.get("suggestTopics") or {}
            arguments = {a.get("name"): a for a in catalog.get("args") or []}
            create_args = {a.get("name"): a for a in (mutation.get("createEvent") or {}).get("args") or []}
            edit_args = {a.get("name"): a for a in (mutation.get("editEvent") or {}).get("args") or []}
            supported = (
                _named(catalog.get("type")) == "TopicsConnection"
                and _named((arguments.get("query") or {}).get("type")) == "String"
                and _named(query.get("event", {}).get("type")) == "Event"
                and _named(next((arg.get("type") for arg in query["event"].get("args") or []
                                 if arg.get("name") == "id"), None)) == "ID"
                and {"createEvent", "editEvent"} <= mutation.keys()
                and _named((create_args.get("input") or {}).get("type")) == "CreateEventInput"
                and _named((edit_args.get("input") or {}).get("type")) == "EditEventInput"
                and _named(event.get("topics", {}).get("type")) == "TopicsConnection"
                and _is_list_of(connection.get("edges", {}).get("type"), "TopicEdge")
                and _named(edge.get("node", {}).get("type")) == "Topic"
                and {"id", "name"} <= topic.keys()
                and _is_id_list(create.get("topics", {}).get("type"))
                and _is_id_list(edit.get("topics", {}).get("type"))
            )
        except TopicReviewRequired:
            supported = False
        except MeetupApiError:
            raise
        except (KeyError, AttributeError, TypeError, ValueError, RuntimeError, OSError):
            supported = False
        self._capability = (now + self._ttl, supported)
        return supported

    def search(self, text: str) -> tuple[Topic, ...]:
        if not self.supported():
            raise TopicReviewRequired("Meetup event-topic schema or catalog is unverified; review topics manually before publication.")
        if not text.strip():
            return ()
        key = text.strip()
        now = monotonic()
        cached = self._cache.get(key)
        if cached and cached[0] > now:
            return cached[1]
        try:
            data = self._query(
                "query($query: String!, $first: Int!) { suggestTopics(query: $query, first: $first, "
                "excludeMemberTopics: false) { edges { node { id name } } } }",
                variables={"query": key, "first": 20},
            )
            edges = ((data.get("data") or {}).get("suggestTopics") or {}).get("edges")
            if not isinstance(edges, list) or any(
                not isinstance(edge, dict) or not isinstance(edge.get("node"), dict)
                for edge in edges
            ):
                raise ValueError("invalid catalog")
            rows = [edge.get("node") for edge in edges or [] if isinstance(edge, dict)]
            if not isinstance(rows, list) or len(rows) > 100:
                raise ValueError("invalid catalog")
            results = canonical_topics(rows) if len(rows) <= 5 else tuple(
                Topic(str(row["id"]).strip(), str(row["name"]).strip()) for row in rows
                if isinstance(row, dict) and isinstance(row.get("id"), str)
                and isinstance(row.get("name"), str) and row["id"].strip() and row["name"].strip()
            )
            if len(results) != len(rows) or len({topic.id for topic in results}) != len(results) or any(
                len(topic.id) > 128 or len(topic.name) > 160 for topic in results
            ):
                raise ValueError("invalid topic result")
        except MeetupApiError:
            raise
        except (KeyError, AttributeError, TypeError, ValueError, RuntimeError, OSError) as exc:
            raise TopicReviewRequired("Meetup topic catalog is unavailable; review selections manually.") from None
        self._cache[key] = (now + self._ttl, results)
        if len(self._cache) > 128:
            self._cache.pop(next(iter(self._cache)))
        return results

    def validate(self, topics: tuple[Topic, ...]) -> tuple[str, ...]:
        if (not isinstance(topics, tuple) or len(topics) > 5
                or any(not isinstance(topic, Topic) for topic in topics)):
            raise TopicReviewRequired()
        topics = canonical_topics([{"id": topic.id, "name": topic.name} for topic in topics])
        if not self.supported(refresh=True):
            raise TopicReviewRequired("Meetup event-topic schema is unverified; review topics manually before publication.")
        for topic in topics:
            # Meetup's suggestTopics search is not self-consistent: a canonical topic
            # can be absent for its exact name yet present for a prefix (for example,
            # "Neurodivergence" is returned for "Neurodivergen"). Revalidate against
            # fresh provider results using bounded prefixes, while still requiring the
            # exact saved provider id and canonical name before any write.
            compact_name = re.sub(r"\s+", " ", topic.name).strip()
            queries = [compact_name]
            for amount in range(1, min(6, max(1, len(compact_name) - 3))):
                queries.append(compact_name[:-amount].rstrip())
            for word in _words(compact_name):
                queries.extend([word, word[:-1] if len(word) > 4 else word])
            matched = False
            for query in dict.fromkeys(query for query in queries if len(query) >= 4):
                self._cache.pop(query, None)
                if topic in self.search(query):
                    matched = True
                    break
            if not matched:
                raise TopicReviewRequired(
                    f'Meetup tag "{topic.name}" is no longer recognized; refresh the tag selection.'
                )
        return tuple(topic.id for topic in topics)

    def readback(self, event_id: str) -> tuple[str, ...]:
        if not self.supported():
            raise TopicReviewRequired("Meetup event-topic readback schema is unverified.")
        try:
            data = self._query(
                "query($id: ID!) { event(id: $id) { id topics { edges { node { id name } } } } }",
                variables={"id": event_id},
            )
            event = (data.get("data") or {}).get("event")
            if not isinstance(event, dict) or str(event.get("id")) != event_id:
                raise ValueError("event identity mismatch")
            topic_connection = event.get("topics")
            if not isinstance(topic_connection, dict) or not isinstance(topic_connection.get("edges"), list):
                raise ValueError("invalid topic connection")
            edges = topic_connection.get("edges")
            if any(not isinstance(edge, dict) or not isinstance(edge.get("node"), dict) for edge in edges):
                raise ValueError("invalid topic edge")
            rows = [edge.get("node") for edge in edges or [] if isinstance(edge, dict)]
            return tuple(topic.id for topic in canonical_topics(rows))
        except MeetupApiError:
            raise
        except (KeyError, AttributeError, TypeError, ValueError, RuntimeError, OSError) as exc:
            raise TopicReviewRequired("Meetup topic readback is unavailable; review provider state before retrying.") from None


def _redacted(method):
    def call(*args, **kwargs):
        error = None
        try:
            return method(*args, **kwargs)
        except MeetupApiError as exc:
            error = (exc.code, exc.outcome_unknown)
        except Exception:
            error = ("topic_unverified", False)
        if error[0] == "topic_unverified":
            raise TopicReviewRequired()
        raise MeetupApiError(error[0], outcome_unknown=error[1])
    return call


for _name in ("supported", "search", "validate", "readback"):
    setattr(MeetupTopicCatalog, _name, _redacted(getattr(MeetupTopicCatalog, _name)))
