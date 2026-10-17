from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def healthz(request):
    """Liveness probe. It never touches the database, so uptime checks can't keep Neon awake."""
    response = JsonResponse({"status": "ok"})
    response["Cache-Control"] = "no-store"
    return response
