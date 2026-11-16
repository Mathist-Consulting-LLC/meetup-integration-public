"""No HTTP/DNS defaults. Transports must pin the supplied validated addresses."""
from dataclasses import dataclass, field
from io import BytesIO
import ipaddress
from urllib.parse import urlsplit
import warnings
from types import MappingProxyType
from typing import Mapping

from .errors import MeetupApiError

MAX_EVENT_IMAGE_BYTES = 10 * 1024 * 1024
MAX_EVENT_IMAGE_PIXELS = 40_000_000
EVENT_IMAGE_CONTENT_TYPES = {
    "image/jpeg": "JPEG", "image/jpg": "JPEG", "image/png": "PNG",
    "image/webp": "WEBP", "image/gif": "GIF",
}


@dataclass(frozen=True)
class ImageRequest:
    url: str = field(repr=False)
    method: str
    headers: Mapping[str, str]
    addresses: tuple[str, ...]
    body: bytes = field(default=b"", repr=False)
    max_bytes: int = MAX_EVENT_IMAGE_BYTES
    timeout_seconds: int = 30


@dataclass(frozen=True)
class ImageResult:
    status: int
    body: bytes = field(repr=False)
    content_type: str = ""
    content_length: str = ""
    redirected: bool = False


def validate_image_url(url, resolver):
    invalid = False
    addresses = ()
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        if (parsed.scheme != "https" or not host or parsed.username is not None
                or parsed.password is not None or parsed.fragment
                or parsed.port not in (None, 443) or host.endswith(".localhost")
                or host == "localhost" or any(ord(c) <= 32 or ord(c) == 127 for c in url)):
            raise ValueError()
        try:
            addresses = (str(ipaddress.ip_address(host)),)
        except ValueError:
            addresses = tuple(resolver(host, 443)) if callable(resolver) else ()
        if not addresses:
            raise ValueError()
        for address in addresses:
            ip = ipaddress.ip_address(address)
            for value in (ip, getattr(ip, "ipv4_mapped", None)):
                if value is not None and (not value.is_global or value.is_multicast
                                          or value.is_reserved):
                    raise ValueError()
    except Exception:
        invalid = True
    if invalid:
        raise MeetupApiError("image_unsafe")
    return addresses


def normalize_event_image(body: bytes, content_type: str) -> tuple[bytes, str]:
    if (type(body) is not bytes or not body or len(body) > MAX_EVENT_IMAGE_BYTES
            or type(content_type) is not str or content_type not in EVENT_IMAGE_CONTENT_TYPES):
        raise MeetupApiError("image_invalid")
    available = True
    try:
        from PIL import Image, ImageOps
    except ImportError:
        available = False
    if not available:
        raise MeetupApiError("image_support_unavailable")
    failed = False
    normalized = b""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(body)) as source:
                if (source.format != EVENT_IMAGE_CONTENT_TYPES[content_type]
                        or source.width < 1 or source.height < 1
                        or source.width * source.height > MAX_EVENT_IMAGE_PIXELS):
                    raise ValueError()
                source.verify()
            with Image.open(BytesIO(body)) as source:
                source.load()
                # Validate JPEG too; do not preserve the source's unvalidated fast path.
                if content_type in ("image/jpeg", "image/jpg"):
                    return body, "image/jpeg"
                image = ImageOps.exif_transpose(source)
                if image.mode in ("RGBA", "LA") or "transparency" in image.info:
                    rgba = image.convert("RGBA")
                    image = Image.new("RGB", rgba.size, "white")
                    image.paste(rgba, mask=rgba.getchannel("A"))
                else:
                    image = image.convert("RGB")
                output = BytesIO()
                image.save(output, format="JPEG", quality=92, optimize=True)
                normalized = output.getvalue()
    except Exception:
        failed = True
    if failed or not normalized or len(normalized) > MAX_EVENT_IMAGE_BYTES:
        raise MeetupApiError("image_invalid")
    return normalized, "image/jpeg"


class ImageSupport:
    def _image_exchange(self, url, *, method="GET", body=b"", content_type="", readback=False):
        addresses = validate_image_url(url, self._resolver)
        if not callable(self._image_transport):
            raise MeetupApiError("transport_unavailable")
        headers = {"Content-Type": content_type} if method == "PUT" else {
            "Accept": ", ".join(EVENT_IMAGE_CONTENT_TYPES)}
        if readback:
            headers["Range"] = "bytes=0-0"
        request = ImageRequest(
            url, method, MappingProxyType(headers), addresses, body,
            1 if readback or method == "PUT" else MAX_EVENT_IMAGE_BYTES,
            15 if readback else 30,
        )
        result = None
        try:
            result = self._image_transport(request)
        except Exception:
            pass
        if (type(result) is not ImageResult or type(result.status) is not int
                or not 200 <= result.status < 300 or result.redirected
                or type(result.redirected) is not bool or type(result.content_type) is not str
                or type(result.content_length) is not str
                or type(result.body) is not bytes or len(result.body) > request.max_bytes):
            raise MeetupApiError("mutation_uncertain" if method == "PUT" else "image_unsafe")
        return result

    def upload_event_image_from_url(self, group_url_name: str, image_url: str) -> str:
        result = self._image_exchange(image_url)
        invalid = False
        try:
            if result.content_length and not 0 <= int(result.content_length) <= MAX_EVENT_IMAGE_BYTES:
                invalid = True
        except (TypeError, ValueError):
            invalid = True
        if invalid:
            raise MeetupApiError("image_invalid")
        body, content_type = normalize_event_image(result.body, result.content_type)
        upload_url, photo_id, base_url = self._create_group_event_photo_placeholder(group_url_name, content_type)
        failed = False
        try:
            self._image_exchange(upload_url, method="PUT", body=body, content_type=content_type)
            for delay in (0, 1, 2, 4, 8):
                if delay:
                    self._sleep(delay)
                if self._meetup_photo_is_readable(photo_id, base_url):
                    return photo_id
        except Exception:
            failed = True
        # Placeholder submission/upload may have happened even if readback failed.
        if failed or photo_id:
            raise MeetupApiError("mutation_uncertain")

    def _meetup_photo_is_readable(self, photo_id: str, base_url: str) -> bool:
        try:
            parsed = urlsplit(base_url)
            if (parsed.hostname != "secure-content.meetupstatic.com"
                    or not photo_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in photo_id)):
                return False
            result = self._image_exchange(base_url.rstrip("/") + "/" + photo_id + "/676x380.webp", readback=True)
            return result.content_type.startswith("image/") and bool(result.body)
        except (MeetupApiError, ValueError):
            return False
