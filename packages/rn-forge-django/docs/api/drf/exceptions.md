# Exceptions

## Which handler do I want?

Two exception handlers ship, and this package wires neither — name one in
`REST_FRAMEWORK["EXCEPTION_HANDLER"]`:

- `problem_details_exception_handler` renders RFC 9457 `application/problem+json`. It is the wire
  contract shared with `rn-forge-fastapi`, so choose it for any new API. The normative description
  of the body, the status mapping and the 401/403 boundary is `rn-forge-web`'s
  `api-conventions.md`; this page does not restate it.
- `drf_exception_handler` renders this package's original `{"path", "error", "message"}` body, for
  existing consumers.

For Django's own routing errors, name `rn_forge.django.exceptions.problem_details_handler404` (and
`problem_details_handler500`) in your root URLconf — see [Exceptions](../exceptions.md).

::: rn_forge.django.drf.exceptions
