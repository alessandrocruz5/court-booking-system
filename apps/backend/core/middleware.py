"""Sets `Cache-Control: no-store` on every response under `/api/` and `/webhooks/`.

The views already do it, but some responses never reach a view: the URL resolver's 404, the 400
from `DisallowedHost` (raised by `CommonMiddleware`), a 400 from `RequestDataTooBig` and a 500.
It must stay FIRST in `MIDDLEWARE`: Django converts exceptions to responses around each middleware,
so only the outermost one sees the final response of every request. The views' own no-store code
stays as defence in depth.
"""

_PREFIXES = ("/api/", "/webhooks/")


class NoStoreMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(_PREFIXES):
            response["Cache-Control"] = "no-store"
        return response
