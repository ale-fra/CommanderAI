"""API routers, one per area of the contract (docs/UI_PLAN.md §2)."""

from commanderai.api.schemas import ErrorResponse

# Documented on every router: all failures share the ErrorResponse shape.
ERROR_RESPONSES: dict = {
    status: {"model": ErrorResponse}
    for status in (400, 404, 409, 410, 422, 503)
}
