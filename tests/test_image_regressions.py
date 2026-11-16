import unittest
from io import BytesIO
from unittest.mock import patch
import test_provider as base
from meetup_integration import MeetupClient, ImageResult, normalize_event_image
from meetup_integration.images import MAX_EVENT_IMAGE_BYTES

try:
    from PIL import Image
except ImportError:
    Image = None


class ImageBoundaryTests(unittest.TestCase):
    assert_error = base.ProviderTests.assert_error
    def test_public_readback_malformed_provider_url_is_unreadable(self):
        for url in ("https://[SYNTHETIC_SECRET]/a", "https://[SYNTHETIC_SECRET/a",
                    "https://secure-content.meetupstatic.com：SYNTHETIC_SECRET/a"):
            with self.subTest(url=url):
                calls = []
                client = MeetupClient(
                    token_supplier=lambda: "synthetic-token",
                    transport=lambda *args: base.response({"data": {"event": {
                        "id": "e", "featuredEventPhoto": {"id": "photo", "baseUrl": url},
                    }}}),
                    resolver=lambda *args: calls.append("dns") or ["93.184.216.34"],
                    image_transport=lambda req: calls.append(req) or ImageResult(206, b"x", "image/webp"),
                )
                self.assertFalse(client.event_image_is_readable("e", "photo"))
                self.assertEqual(calls, [])

    def test_resolver_failure_empty_and_missing_transport(self):
        def failed(*args):
            raise OSError("SECRET")
        client = MeetupClient(resolver=failed)
        self.assert_error("image_unsafe", lambda: client.upload_event_image_from_url("g", "https://cdn.example/a"))
        client._resolver = lambda *args: ["93.184.216.34"]
        self.assert_error("transport_unavailable", lambda: client.upload_event_image_from_url("g", "https://cdn.example/a"))
        client._image_transport = lambda req: ImageResult(200, b"x" * (MAX_EVENT_IMAGE_BYTES+1), "image/jpeg")
        self.assert_error("image_unsafe", lambda: client.upload_event_image_from_url("g", "https://cdn.example/a"))

    def test_readback_host_identity_and_redirect_rejected(self):
        calls = []
        client = MeetupClient(resolver=lambda *args: ["93.184.216.34"],
                              image_transport=lambda req: calls.append(req) or ImageResult(302, b"", redirected=True))
        self.assertFalse(client._meetup_photo_is_readable("photo", "https://other.example/a"))
        self.assertEqual(calls, [])
        self.assertFalse(client._meetup_photo_is_readable("../unsafe", "https://secure-content.meetupstatic.com/a"))
        self.assertEqual(calls, [])
        self.assertFalse(client._meetup_photo_is_readable("photo", "https://secure-content.meetupstatic.com/a"))
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].timeout_seconds, 15)
        self.assertEqual(calls[0].max_bytes, 1)

    @unittest.skipIf(Image is None, "optional Pillow not installed")
    def test_jpeg_passthrough_is_decoded_and_transparency_is_white(self):
        output = BytesIO()
        Image.new("RGB", (2, 2), "red").save(output, format="JPEG")
        body = output.getvalue()
        self.assertEqual(normalize_event_image(body, "image/jpeg"), (body, "image/jpeg"))
        with patch("meetup_integration.images.MAX_EVENT_IMAGE_PIXELS", 3):
            self.assert_error("image_invalid", lambda: normalize_event_image(body, "image/jpeg"))
        output = BytesIO()
        Image.new("RGBA", (2, 2), (255, 0, 0, 0)).save(output, format="PNG")
        normalized, content_type = normalize_event_image(output.getvalue(), "image/png")
        with Image.open(BytesIO(normalized)) as decoded:
            self.assertEqual(decoded.mode, "RGB")
            self.assertTrue(all(channel >= 250 for channel in decoded.getpixel((0, 0))))
        self.assertEqual(content_type, "image/jpeg")
