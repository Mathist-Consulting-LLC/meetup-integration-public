import json
import unittest
from dataclasses import replace
import test_provider as base
from meetup_integration import MeetupClient, MeetupApiError, ImageResult
from topic_fixture import SyntheticGraphQL


class WriteTests(unittest.TestCase):
    assert_error = base.ProviderTests.assert_error
    client = base.ProviderTests.client
    def test_network_timezone_preflight_before_tokens_or_topic_transport(self):
        missing = replace(base.request(), network_from_event_id="template")
        for request in (missing, *(replace(missing, timezone=value)
                                  for value in ("", " \t\n", None, 42, False, [], {}))):
            with self.subTest(timezone=request.timezone):
                calls = []
                client = MeetupClient(
                    token_supplier=lambda: calls.append("token") or "synthetic-token",
                    transport=lambda *args: calls.append("transport") or base.response({}),
                )
                # Even topic verification must not submit before this preflight.
                request = replace(request, topic_ids=("t",),
                                  topic_selections=({"id": "t", "name": "Python"},))
                self.assert_error("invalid_request", lambda: client.create_event(request), False)
                self.assertEqual(calls, [])

    def test_network_explicit_timezone_preserves_provider_payload(self):
        calls = []
        def transport(req, token):
            calls.append(json.loads(req.body)["variables"]["input"])
            return base.response({"data": {"createEvent": {"event": {"id": "e"}, "errors": []}}})
        client = self.client(transport)
        self.assertEqual(client.create_event(replace(
            base.request(), network_from_event_id="template", timezone="Etc/UTC")).id, "e")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["proNetworkEvents"],
                         {"fromEventId": "template", "timezone": "Etc/UTC"})

    def test_timeout_after_provider_success_retains_uncertainty(self):
        provider_objects = []
        def submitted(req, token):
            provider_objects.append(json.loads(req.body)["variables"]["input"])
            raise TimeoutError("SECRET after successful remote creation")
        client = self.client(submitted)
        self.assert_error("mutation_uncertain", lambda: client.create_event(base.request()), True)
        self.assertEqual(len(provider_objects), 1)
        self.assertEqual(provider_objects[0]["title"], "Synthetic")
        for action in (lambda: client.update_event("e", {"title": "New"}),
                       lambda: client.cancel_event("e", "ignored")):
            self.assert_error("mutation_uncertain", action, True)
        self.assertEqual(len(provider_objects), 3)

    def test_topic_writes_use_fresh_canonical_ids_and_no_unverified_writes(self):
        provider = SyntheticGraphQL()
        provider.selections["Python"] = [{"id": "t", "name": "Python"}]
        writes = []
        def transport(req, token):
            data = json.loads(req.body)
            query = data["query"]
            if query.startswith("mutation"):
                writes.append(data["variables"]["input"])
                name = "createEvent" if "CreateEventInput" in query else "editEvent"
                return base.response({"data": {name: {"event": {"id": "e"}, "errors": []}}})
            return base.response(provider(query, variables=data.get("variables")))
        client = self.client(transport)
        client.create_event(replace(base.request(), topic_ids=("t",),
                                    topic_selections=({"id": "t", "name": "Python"},)))
        client.update_event("e", {"topic_ids": ("t",),
                                 "topic_selections": ({"id": "t", "name": "Python"},)})
        self.assertEqual(writes[0]["topics"], ["t"])
        self.assertEqual(writes[1], {"eventId": "e", "topics": ["t"]})
        self.assert_error("topic_unverified", lambda: client.update_event("e", {"topic_ids": ("bad",)}))
        provider.supported = False
        self.assert_error("topic_unverified", lambda: client.update_event("e", {
            "topic_ids": ("t",), "topic_selections": ({"id": "t", "name": "Python"},)}))
        self.assertEqual(len(writes), 2)

    def test_venue_pagination_and_cycle(self):
        calls = []
        def transport(req, token):
            data = json.loads(req.body)
            calls.append(data["variables"]["after"])
            cursor = data["variables"]["after"]
            return base.response({"data": {"groupByUrlname": {"venues": {
                "edges": [{"node": {"id": "v1" if cursor is None else "v2", "name": "Place"}}],
                "pageInfo": {"hasNextPage": cursor is None, "endCursor": "next"}
            }}}})
        client = self.client(transport)
        self.assertEqual([v.id for v in client.search_venues("g", "")], ["v1", "v2"])
        self.assertEqual(calls, [None, "next"])
        client = self.client(lambda *args: base.response({"data": {"groupByUrlname": {"venues": {
            "edges": [], "pageInfo": {"hasNextPage": True, "endCursor": "same"}}}}}))
        self.assert_error("response_invalid", lambda: client.search_venues("g", ""))

    def test_mismatched_and_malformed_mutation_event(self):
        for node in ({"id": "other"}, {"id": "e", "maxTickets": "SECRET"}):
            client = self.client(lambda *args: base.response({"data": {"editEvent": {"event": node}}}))
            self.assert_error("mutation_uncertain", lambda: client.update_event("e", {}), True)

    def test_unknown_error_codes_are_safe(self):
        for code in ([], {}, None, "SECRET"):
            self.assertEqual(MeetupApiError(code).code, "response_invalid")

    def test_core_import_and_explicit_missing_image_extra(self):
        import sys
        from unittest.mock import patch
        from meetup_integration import normalize_event_image
        with patch.dict(sys.modules, {"PIL": None}):
            self.assert_error("image_support_unavailable",
                              lambda: normalize_event_image(b"synthetic", "image/jpeg"))

    def test_put_timeout_is_uncertain(self):
        def timeout(req):
            raise TimeoutError("SECRET")
        client = MeetupClient(resolver=lambda *args: ["93.184.216.34"], image_transport=timeout)
        self.assert_error("mutation_uncertain", lambda: client._image_exchange("https://upload.example/a", method="PUT"))
