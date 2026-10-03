# ADR 0037: JSON format of Decimal amounts in API responses (as built)

- Status: Accepted (descriptive, records the behaviour of version 1.68.0; no change)
- Date: 2026-10-03

## Context

GAI-304 (packages AK11, AL04) left routes with money amounts without a typed response model
"until the JSON format of Decimal is decided" (number or string). Package AN11 was asked to
establish what the code does today and to record it, without changing any output. Amounts are
stored as `NUMERIC(14,2)` and intermediate values as `NUMERIC(20,8)` and handled as
`decimal.Decimal` (master prompt 6.9.8, rule 10).

## Decision

This ADR only describes the existing behaviour (FastAPI 0.141, Pydantic 2.13):

1. **Typed models serialize `Decimal` as a JSON string.** Pydantic v2 writes `str(value)`:
   `Decimal("1234.50")` becomes `"1234.50"` (the scale is kept, no float rounding). Example:
   `AccountingOpenItemOut.amount`, `ai/schemas.py` `cost_eur`.
2. **Routes annotated `dict[str, Any]`, `list[dict[str, Any]]` or `Any` also serialize
   `Decimal` as a string.** FastAPI derives a response field from the return annotation and
   serializes the handler result through Pydantic (`TypeAdapter(...).dump_json`, the "fast
   path" in `fastapi/routing.py`); a `Decimal` inside the dict therefore becomes `"1234.50"`
   as well. All JSON routes of `accounting`, `billing` and `banking` with amounts have such an
   annotation. Verified by `tests/unit/test_an11_raw_json_out.py`.
3. **Only a plain value without any response field** (no return annotation, or an annotation
   such as `Response | CheckOut` that FastAPI cannot use as a model) goes through
   `fastapi.encoders.jsonable_encoder`, which writes a bare `Decimal` as a JSON number
   (`12.5`, `3`). A Pydantic model returned on that path is still dumped with
   `model_dump(mode="json")`, so its amounts stay strings (DATEV check
   `datev_check_routers.py`). No route of the three domains returns a bare `Decimal` dict on
   this path; file downloads return `Response` objects.
4. **Explicit string conversions exist in handlers** and stay as they are, for example
   `control_sum: str(batch.control_sum)` of the payment batch and `str(...)` in event payloads.
5. **Plain notation is a per field decision:** `properties/schemas.py` uses a
   `field_serializer` with `f"{value:f}"` so that a zero with eight places is `"0.00000000"`
   and not `"0E-8"`. Elsewhere `str(Decimal)` applies unchanged.
6. **Datetimes** in both paths 1 and 2 are written by Pydantic (`"2026-10-03T08:00:00Z"`).

To type further money routes without changing a byte, AN11 adds
`mhvp.accounting.write_responses.RawJsonOut`: the model declares and validates the fields for
OpenAPI, keeps the original handler value and serializes exactly that value in JSON mode, so
a declared `Decimal` field never coerces an `int` or `float` (`7` stays `7`). The route keeps
FastAPI's default response class; the bytes equal those of the former `dict[str, Any]`
annotation. 60 routes of `accounting`, `billing` and `banking` use it (list in
`tests/unit/test_an11_raw_json_out.py`, `AN11_TYPED`).

## Consequences

- Clients (CRM, portal, generated `packages/api-client`) receive amounts as strings, as before;
  the generated types now name the fields (OpenAPI shows `Decimal` as number or string,
  validation schema), `make openapi` is run by the coordinator.
- A future change of the format (for example always plain notation or JSON numbers) is a new
  decision with an ADR of its own; it is not part of this record.
- Tests: `test_an11_raw_json_out.py` (bytes equal to the untyped annotation, schema present,
  AN11 routes stay `RawJsonOut`), `test_ak11_untyped_routes_ratchet.py` (allowlist shrank by
  60 lines).

## Alternatives considered

- Plain Pydantic models without `RawJsonOut`: identical only as long as every declared type
  matches the handler value exactly; an `int` in a `Decimal` field would become `"7"`.
- Leaving the routes untyped until a format decision: keeps OpenAPI without fields for
  money routes, which GAI-304 criticised.

## References

- `docs/MASTER-PROMPT.md` 6.9.8, rule 10 (numbers), section 4.1 (API first)
- ADR 0004 (errors), GAI-304, packages AK11, AL04, AN11
