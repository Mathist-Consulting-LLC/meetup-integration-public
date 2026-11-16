"""Fixed diagnostics: no provider text, URLs, tokens or caller exceptions."""
_MESSAGES = {
    "invalid_request": "Invalid provider request.",
    "authentication_unavailable": "Access token unavailable.",
    "authentication_failed": "Provider authentication failed.",
    "permission_denied": "Provider permission denied.",
    "rate_limited": "Provider rate limit reached.",
    "transport_unavailable": "Caller transport unavailable.",
    "response_invalid": "Provider response is incomplete or invalid.",
    "schema_unsupported": "Provider schema is unsupported.",
    "topic_unverified": "Provider topic identity or schema is unverified.",
    "mutation_uncertain": "Mutation outcome is uncertain; reconcile before any replay.",
    "image_unsafe": "Image URL, address or response is unsafe.",
    "image_invalid": "Image bytes, type, size or dimensions are invalid.",
    "image_support_unavailable": "Optional image support is unavailable.",
}


class MeetupApiError(RuntimeError):
    def __init__(self, code: str, *, outcome_unknown: bool = False):
        self.code = code if type(code) is str and code in _MESSAGES else "response_invalid"
        self.outcome_unknown = outcome_unknown or self.code == "mutation_uncertain"
        super().__init__(_MESSAGES[self.code])
