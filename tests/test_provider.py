import json
import traceback
import unittest
from io import BytesIO
from unittest.mock import patch

from meetup_integration import (
    MeetupClient, MeetupApiError, EventCreateRequest, Result,
    ImageResult, normalize_event_image, MeetupTopicCatalog, Topic, canonical_topics,
)
from meetup_integration.images import validate_image_url, MAX_EVENT_IMAGE_BYTES
from topic_fixture import SyntheticGraphQL


def response(data, status=200):
    return Result(status, json.dumps(data).encode())


def request():
    return EventCreateRequest("group", "Synthetic", "Description", "2026-12-01T10:00:00Z",
                              "PT1H", "venue", "", "DRAFT")


class ProviderTests(unittest.TestCase):
    def client(self, transport):
        return MeetupClient(token_supplier=lambda: "synthetic-token", transport=transport)

    def assert_error(self, code, action, unknown=None):
        with self.assertRaises(MeetupApiError) as caught:
            action()
        error = caught.exception
        self.assertEqual(error.code, code)
        if unknown is not None:
            self.assertEqual(error.outcome_unknown, unknown)
        self.assertIsNone(error.__cause__)
        self.assertIsNone(error.__context__)
        self.assertNotIn("SECRET", "".join(traceback.format_exception(error)))

    def test_no_defaults_or_token_storage(self):
        calls = []
        client = MeetupClient(token_supplier=lambda: calls.append(1))
        self.assert_error("transport_unavailable", client.verify_auth)
        self.assertEqual(calls, [])
        def supply():
            calls.append(1)
            return "synthetic-token"
        client = MeetupClient(token_supplier=supply, transport=lambda req, tok: response({"data": {"self": {"id": "member"}}}))
        self.assertTrue(client.verify_auth())
        self.assertTrue(client.verify_auth())
        self.assertEqual(calls, [1, 1])

    def test_auth_permission_rate_and_graphql_errors(self):
        for status, code in ((401, "authentication_failed"), (403, "permission_denied"), (429, "rate_limited")):
            client = self.client(lambda *args: Result(status, b"SECRET"))
            self.assert_error(code, client.verify_auth, False)
            self.assert_error(code, lambda: client.create_event(request()), True)
        for extension, code in (("UNAUTHENTICATED", "authentication_failed"), ("FORBIDDEN", "permission_denied"), ("RATE_LIMITED", "rate_limited"), ("GRAPHQL_VALIDATION_FAILED", "schema_unsupported")):
            client = self.client(lambda *args: response({"errors": [{"message": "SECRET", "extensions": {"code": extension}}]}))
            self.assert_error(code, client.verify_auth)

    def test_transport_timeout_and_unknown_write_no_retry(self):
        calls = []
        def transport(*args):
            calls.append(1)
            raise TimeoutError("SECRET")
        client = self.client(transport)
        self.assert_error("transport_unavailable", client.verify_auth)
        self.assert_error("mutation_uncertain", lambda: client.create_event(request()), True)
        self.assertEqual(len(calls), 2)

    def test_bad_token_is_redacted_before_transport(self):
        def supplier():
            raise ValueError("SECRET")
        client = MeetupClient(token_supplier=supplier, transport=lambda *args: self.fail("called"))
        self.assert_error("authentication_unavailable", client.verify_auth)

    def test_malformed_and_missing_mutation_identity(self):
        for body in (b"SECRET", b"[]", b"null", b"{}", b'{"data":{}}',
                     b'{"data":{"createEvent":{"event":{"title":"SECRET"}}}}'):
            client = self.client(lambda *args: Result(200, body))
            self.assert_error("mutation_uncertain", lambda: client.create_event(request()), True)
        for data in ({}, {"data": {"groupByUrlname": {"events": {}}}},
                     {"data": {"groupByUrlname": {"events": {"edges": [], "pageInfo": {"hasNextPage": "false"}}}}}):
            client = self.client(lambda *args: response(data))
            self.assert_error("response_invalid", lambda: client.list_group_events("g", after_date_time="a", before_date_time="b"))
        client = self.client(lambda *args: response({"data": {"deleteEvent": {}}}))
        self.assert_error("mutation_uncertain", lambda: client.cancel_event("e", "ignored"))

    def test_cursor_cycle_and_page_bound(self):
        calls = []
        def transport(req, token):
            payload = json.loads(req.body)
            calls.append(payload["variables"]["after"])
            return response({"data": {"groupByUrlname": {"events": {
                "edges": [], "pageInfo": {"hasNextPage": True, "endCursor": "a" if len(calls) % 2 else "b"}
            }}}})
        client = self.client(transport)
        self.assert_error("response_invalid", lambda: client.list_group_events("g", after_date_time="a", before_date_time="b"))
        self.assertEqual(calls, [None, "a", "b"])
        calls.clear()
        client._max_pages = 1
        self.assert_error("response_invalid", lambda: client.list_group_events("g", after_date_time="a", before_date_time="b"))
        self.assertEqual(calls, [None])

    def test_network_reads_and_identity(self):
        client = self.client(lambda *args: response({"data": {"proNetwork": {"id": "n", "groupsSearch": {"edges": [{"node": {"id": "g", "urlname": "slug", "name": "Group"}}]}}}}))
        self.assertEqual(client.list_network_groups("network", "n")[0]["parentNetworkId"], "n")
        self.assert_error("response_invalid", lambda: client.list_network_groups("network", "wrong"))
        client = self.client(lambda *args: response({"data": {"proNetwork": {"eventsSearch": {"edges": [{"node": {"id": "e"}}]}}}}))
        self.assertEqual(client.list_network_events("network")[0].id, "e")
        client = self.client(lambda *args: response({"data": {"event": None}}))
        self.assertIsNone(client.get_event("missing"))

    def test_topic_validation_refresh_prefix_and_readback(self):
        provider = SyntheticGraphQL()
        provider.selections["Neurodivergen"] = [{"id": "t", "name": "Neurodivergence"}]
        catalog = MeetupTopicCatalog(provider)
        self.assertEqual(catalog.validate((Topic("t", "Neurodivergence"),)), ("t",))
        self.assertTrue(any(v.get("query") == "Neurodivergen" for q, v in provider.calls))
        self.assert_error("topic_unverified", lambda: catalog.validate((Topic("bad", "Python"),)))
        def readback(q, *, variables=None):
            if "event(id:" in q:
                return {"data": {"event": {"id": variables["id"], "topics": {"edges": [{"node": {"id": "t", "name": "Topic"}}]}}}}
            return provider(q, variables=variables)
        self.assertEqual(MeetupTopicCatalog(readback).readback("e"), ("t",))
        self.assert_error("topic_unverified", lambda: canonical_topics([{"id": "t", "name": "Topic"}] * 2))
        self.assertFalse(MeetupTopicCatalog(SyntheticGraphQL(False)).supported())

    def test_topic_malformed_catalog_fails_closed(self):
        provider = SyntheticGraphQL()
        for value in (None, {}, {"edges": None}, {"edges": [{"node": {}}]}):
            def malformed(q, *, variables=None):
                if "suggestTopics(" in q:
                    return {"data": {"suggestTopics": value}}
                return provider(q, variables=variables)
            self.assert_error("topic_unverified", lambda: MeetupTopicCatalog(malformed).search("Python"))

    def test_image_urls_dns_and_redirect(self):
        for url in ("http://example.test/a", "https://user:pass@example.test/a", "https://localhost/a",
                    "https://assets.localhost/a", "https://127.0.0.1/a", "https://10.0.0.5/a",
                    "https://169.254.1.1/a", "https://224.0.0.1/a", "https://[::1]/a",
                    "https://[fe80::1]/a", "https://[::ffff:127.0.0.1]/a", "https://x:bad/a"):
            self.assert_error("image_unsafe", lambda: validate_image_url(url, lambda *args: ["93.184.216.34"]))
        for addresses in ([], ["10.0.0.8"], ["93.184.216.34", "127.0.0.1"], ["bad"]):
            self.assert_error("image_unsafe", lambda: validate_image_url("https://cdn.example/a", lambda *args: addresses))
        client = MeetupClient(resolver=lambda *args: ["93.184.216.34"],
                              image_transport=lambda req: ImageResult(302, b"", redirected=True))
        self.assert_error("image_unsafe", lambda: client.upload_event_image_from_url("g", "https://cdn.example/a"))


try:
    from PIL import Image
except ImportError:
    Image = None


@unittest.skipIf(Image is None, "optional Pillow not installed")
class ImageTests(unittest.TestCase):
    assert_error = ProviderTests.assert_error
    def image(self, mode="RGBA", fmt="PNG"):
        output = BytesIO()
        Image.new(mode, (2, 2)).save(output, format=fmt)
        return output.getvalue()

    def test_normalization_type_size_pixel_and_corrupt(self):
        normalized, kind = normalize_event_image(self.image(), "image/png")
        self.assertEqual(kind, "image/jpeg")
        self.assertTrue(normalized.startswith(b"\xff\xd8"))
        for body, kind in ((b"bad", "image/jpeg"), (self.image(), "image/jpeg"),
                           (b"", "image/png"), (b"x" * (MAX_EVENT_IMAGE_BYTES + 1), "image/png"),
                           (self.image(), "text/plain")):
            self.assert_error("image_invalid", lambda: normalize_event_image(body, kind))
        with patch("meetup_integration.images.MAX_EVENT_IMAGE_PIXELS", 3):
            self.assert_error("image_invalid", lambda: normalize_event_image(self.image(), "image/png"))

    def test_placeholder_put_and_readback_without_bearer(self):
        calls = []
        def graphql(req, token):
            data = json.loads(req.body)
            calls.append(data)
            if "groupByUrlname" in data["query"]:
                return response({"data": {"groupByUrlname": {"id": "g"}}})
            return response({"data": {"createGroupEventPhoto": {
                "uploadUrl": "https://upload.example/photo", "photo": {
                    "id": "p", "baseUrl": "https://secure-content.meetupstatic.com/images"}}}})
        images = []
        def image_transport(req):
            images.append(req)
            self.assertNotIn("Authorization", req.headers)
            self.assertEqual(req.addresses, ("93.184.216.34",))
            if req.method == "PUT":
                self.assertTrue(req.body.startswith(b"\xff\xd8"))
                return ImageResult(200, b"")
            if req.max_bytes == 1:
                return ImageResult(206, b"x", "image/webp")
            return ImageResult(200, self.image(), "image/png")
        client = MeetupClient(token_supplier=lambda: "synthetic-token", transport=graphql,
                              resolver=lambda *args: ["93.184.216.34"], image_transport=image_transport,
                              sleep=lambda seconds: None)
        self.assertEqual(client.upload_event_image_from_url("g", "https://cdn.example/a"), "p")
        self.assertEqual([r.method for r in images], ["GET", "PUT", "GET"])
        self.assertEqual(calls[1]["variables"]["input"], {
            "groupId": "g", "photoType": "GROUP_PHOTO", "contentType": "JPEG", "setAsMain": False})
        client._meetup_photo_is_readable = lambda *args: False
        self.assert_error("mutation_uncertain", lambda: client.upload_event_image_from_url("g", "https://cdn.example/a"))

    def test_image_response_rejections(self):
        client = MeetupClient(resolver=lambda *args: ["93.184.216.34"])
        for result, code in ((ImageResult(200, self.image(), "text/plain"), "image_invalid"),
                             (ImageResult(200, self.image(), "image/png", str(MAX_EVENT_IMAGE_BYTES+1)), "image_invalid"),
                             (ImageResult(200, b"", "image/png"), "image_invalid"),
                             (ImageResult(200, self.image(), "image/png", "bad"), "image_invalid")):
            client._image_transport = lambda req: result
            self.assert_error(code, lambda: client.upload_event_image_from_url("g", "https://cdn.example/a"))
