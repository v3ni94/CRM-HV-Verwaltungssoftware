"""Generic list parameters of section 12 (S12-03): ``filter[field]=value``, ``sort``,
``fields`` and ``include``.

Each list declares what it allows; anything else is answered with 422 (never silently
ignored), so a caller never mistakes an unfiltered list for a filtered one.

- ``filter[field]=value`` compares one allowed column for equality; ``a,b`` means ``IN``.
  Values are converted by the column type (UUID, bool, int, date, enum, text).
- ``sort=field,-other`` orders by allowed columns (``-`` descending). The list's own default
  order follows as tiebreaker, so paging stays stable.
- ``fields=a,b`` returns sparse items (``id`` is always kept).
- ``include=x`` embeds a relation the list offers; the list resolves it itself.

Tenant scope, soft delete and object assignment filters of the list stay in force; the
parameters only narrow further.
"""

import enum
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from fastapi import Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import Select
from sqlalchemy.orm import InstrumentedAttribute

from mhvp.core.problems import ErrorCodes, FieldError, ProblemError

MAX_FILTER_VALUES = 100


@dataclass(frozen=True, slots=True)
class ListParams:
    filters: dict[str, list[str]] = field(default_factory=dict)
    sort: list[tuple[str, bool]] = field(default_factory=list)  # (field, descending)
    fields: list[str] = field(default_factory=list)
    include: list[str] = field(default_factory=list)


def _invalid(param: str, message: str) -> ProblemError:
    return ProblemError(
        ErrorCodes.VALIDATION,
        detail=message,
        errors=[
            FieldError(location=["query", param], field=param, code="invalid", message=message)
        ],
    )


def _split(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def list_params(request: Request) -> ListParams:
    """FastAPI dependency: parses the generic parameters from the query string."""
    filters: dict[str, list[str]] = {}
    for key, value in request.query_params.multi_items():
        if key.startswith("filter[") and key.endswith("]"):
            name = key[7:-1].strip()
            if not name:
                raise _invalid(key, "Filterfeld fehlt.")
            values = filters.setdefault(name, [])
            values.extend(_split(value) or [""])
            if len(values) > MAX_FILTER_VALUES:
                raise _invalid(key, f"Höchstens {MAX_FILTER_VALUES} Filterwerte.")
    sort: list[tuple[str, bool]] = []
    for part in _split(request.query_params.get("sort", "")):
        desc = part.startswith("-")
        sort.append((part.lstrip("+-"), desc))
    return ListParams(
        filters=filters,
        sort=sort,
        fields=_split(request.query_params.get("fields", "")),
        include=_split(request.query_params.get("include", "")),
    )


def _convert(column: Any, raw: str, param: str) -> Any:
    try:
        python_type = column.type.python_type
    except NotImplementedError:
        return raw
    try:
        if raw == "" or raw.lower() == "null":
            return None
        if python_type is bool:
            if raw.lower() in {"true", "1"}:
                return True
            if raw.lower() in {"false", "0"}:
                return False
            raise ValueError(raw)
        if python_type is uuid.UUID:
            return uuid.UUID(raw)
        if python_type is int:
            return int(raw)
        if python_type is date:
            return date.fromisoformat(raw)
        if isinstance(python_type, type) and issubclass(python_type, enum.Enum):
            return python_type(raw)
    except ValueError as exc:
        raise _invalid(param, f"Filterwert '{raw}' passt nicht zum Feld.") from exc
    return raw


def apply_filters(
    query: Select[Any], params: ListParams, allowed: Mapping[str, InstrumentedAttribute[Any]]
) -> Select[Any]:
    for name, raws in params.filters.items():
        column = allowed.get(name)
        param = f"filter[{name}]"
        if column is None:
            raise _invalid(
                param, f"Filter '{name}' nicht erlaubt. Erlaubt: {', '.join(sorted(allowed))}."
            )
        values = [_convert(column, raw, param) for raw in raws]
        if any(v is None for v in values):
            others = [v for v in values if v is not None]
            clause = column.is_(None) if not others else (column.is_(None) | column.in_(others))
            query = query.where(clause)
        elif len(values) == 1:
            query = query.where(column == values[0])
        else:
            query = query.where(column.in_(values))
    return query


def apply_sort(
    query: Select[Any],
    params: ListParams,
    allowed: Mapping[str, InstrumentedAttribute[Any]],
    default: Sequence[Any],
) -> Select[Any]:
    """Orders by the requested columns, then by ``default``. Without ``sort`` only
    ``default`` applies (the list's previous order)."""
    order: list[Any] = []
    for name, desc in params.sort:
        column = allowed.get(name)
        if column is None:
            raise _invalid(
                "sort",
                f"Sortierung nach '{name}' nicht erlaubt. Erlaubt: {', '.join(sorted(allowed))}.",
            )
        order.append(column.desc().nulls_last() if desc else column.asc().nulls_last())
    return query.order_by(None).order_by(*order, *default)


def check_include(params: ListParams, allowed: Iterable[str]) -> set[str]:
    allowed_set = set(allowed)
    unknown = [name for name in params.include if name not in allowed_set]
    if unknown:
        offer = ", ".join(sorted(allowed_set)) or "keine"
        raise _invalid("include", f"include '{unknown[0]}' nicht angeboten. Angeboten: {offer}.")
    return set(params.include)


def check_fields(params: ListParams, model: type[BaseModel] | Iterable[str]) -> None:
    known = set(model.model_fields) if isinstance(model, type) else set(model)
    unknown = [name for name in params.fields if name not in known]
    if unknown:
        raise _invalid("fields", f"Feld '{unknown[0]}' unbekannt.")


def _sparse_item(item: Any, keep: set[str]) -> Any:
    data = jsonable_encoder(item)
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if k in keep}
    return data


def _with_headers(out: JSONResponse, response: Response | None) -> JSONResponse:
    """Carries headers set on the injected response (X-Total-Count and friends)."""
    if response is not None:
        for key in ("X-Total-Count", "X-Page", "X-Page-Size", "ETag"):
            if key in response.headers:
                out.headers[key] = response.headers[key]
    return out


def sparse(
    result: Any,
    params: ListParams,
    item_model: type[BaseModel] | None,
    *,
    extra: Iterable[str] = (),
    response: Response | None = None,
) -> Any:
    """Returns ``result`` unchanged without ``fields``. With ``fields`` the items (a list, or
    the ``items`` of a page object) are reduced to the requested keys plus ``id`` and any
    ``extra`` keys (e.g. included relations); the response bypasses the response model."""
    if not params.fields:
        return result
    if item_model is not None:
        check_fields(params, item_model)
    elif isinstance(result, list) and result and isinstance(result[0], dict):
        check_fields(params, result[0].keys())
    keep = {"id", *params.fields, *extra}
    if isinstance(result, BaseModel) and hasattr(result, "items"):
        data = jsonable_encoder(result)
        data["items"] = [_sparse_item(i, keep) for i in data.get("items", [])]
        return _with_headers(JSONResponse(data), response)
    if isinstance(result, list | tuple):
        return _with_headers(JSONResponse([_sparse_item(i, keep) for i in result]), response)
    return result


def embed(
    result: Any,
    params: ListParams,
    item_model: type[BaseModel] | None,
    embedded: Mapping[str, Callable[[dict[str, Any]], Any]],
    *,
    response: Response | None = None,
) -> Any:
    """Like :func:`sparse`, but adds included relations (Q12): for each ``name`` in
    ``embedded`` every item gets ``item[name] = resolver(item)``. Without ``embedded`` the
    result goes through :func:`sparse` unchanged. With ``embedded`` the response bypasses the
    response model so the additional keys survive."""
    if not embedded:
        return sparse(result, params, item_model, response=response)
    if params.fields and item_model is not None:
        check_fields(params, item_model)
    data = jsonable_encoder(result)
    items = data.get("items", []) if isinstance(data, dict) else data
    for item in items:
        for name, resolve in embedded.items():
            item[name] = jsonable_encoder(resolve(item))
    if params.fields:
        keep = {"id", *params.fields, *embedded}
        reduced = [{k: v for k, v in i.items() if k in keep} for i in items]
        if isinstance(data, dict):
            data["items"] = reduced
        else:
            data = reduced
    return _with_headers(JSONResponse(data), response)


LIST_PARAMS_DOC = (
    "Allgemeine Listenparameter (Abschnitt 12): `filter[feld]=wert` (mehrere Werte mit Komma), "
    "`sort=feld,-feld`, `fields=a,b` (Sparantwort, `id` bleibt), `include=relation`. "
    "Nicht angebotene Felder werden mit 422 abgelehnt."
)


# Generic list parameters for all list routers (GA04-05) ---------------------------------

GENERIC_LIST_KEYS = frozenset({"sort", "fields", "include", "as_of"})


@dataclass(frozen=True)
class ListSpec:
    """Declares the allowed filter, sort and include names of one list.

    ``dependency`` parses the generic parameters and rejects with 422 any query parameter
    the route neither declares nor offers (no silent ignoring). ``apply`` narrows and orders
    a query; ``as_of`` (ISO date) keeps rows valid on that day when ``valid_from`` and
    ``valid_to`` columns are given, otherwise it is rejected with 422.
    """

    filters: Mapping[str, InstrumentedAttribute[Any]] = field(default_factory=dict)
    sort: Mapping[str, InstrumentedAttribute[Any]] = field(default_factory=dict)
    includes: tuple[str, ...] = ()
    valid_from: InstrumentedAttribute[Any] | None = None
    valid_to: InstrumentedAttribute[Any] | None = None

    def dependency(self, request: Request) -> ListParams:
        params = list_params(request)
        route = request.scope.get("route")
        dependant = getattr(route, "dependant", None)
        declared: set[str] = set()
        if dependant is not None:
            stack = [dependant]
            while stack:
                dep = stack.pop()
                declared.update(p.alias for p in dep.query_params)
                stack.extend(dep.dependencies)
        for key in request.query_params:
            if key.startswith("filter[") or key in GENERIC_LIST_KEYS or key in declared:
                continue
            raise _invalid(key, f"Parameter '{key}' wird von dieser Liste nicht angeboten.")
        for name in params.filters:
            if name not in self.filters:
                offer = ", ".join(sorted(self.filters)) or "keine"
                raise _invalid(
                    f"filter[{name}]", f"Filter '{name}' nicht erlaubt. Erlaubt: {offer}."
                )
        for name, _desc in params.sort:
            if name not in self.sort:
                offer = ", ".join(sorted(self.sort)) or "keine"
                raise _invalid("sort", f"Sortierung nach '{name}' nicht erlaubt. Erlaubt: {offer}.")
        check_include(params, self.includes)
        if "as_of" in request.query_params:
            if self.valid_from is None:
                raise _invalid("as_of", "Stichtag (as_of) wird von dieser Liste nicht angeboten.")
            try:
                date.fromisoformat(request.query_params["as_of"])
            except ValueError as exc:
                raise _invalid("as_of", "Stichtag muss ein Datum JJJJ-MM-TT sein.") from exc
        return params

    def apply(
        self,
        query: Select[Any],
        params: ListParams,
        default: Sequence[Any],
        request: Request | None = None,
    ) -> Select[Any]:
        query = apply_filters(query, params, self.filters)
        if request is not None and self.valid_from is not None:
            raw = request.query_params.get("as_of")
            if raw:
                day = date.fromisoformat(raw)
                query = query.where((self.valid_from.is_(None)) | (self.valid_from <= day))
                if self.valid_to is not None:
                    query = query.where((self.valid_to.is_(None)) | (self.valid_to >= day))
        if params.sort:
            return apply_sort(query, params, self.sort, default)
        return query.order_by(None).order_by(*default)


# Strict query check for lists without generic parameters (GA04-05, AB04) ----------------


def _route_declares(request: Request) -> tuple[set[str], bool]:
    """Query aliases the route declares, and whether it parses the generic list parameters
    itself (``list_params`` or a :class:`ListSpec` dependency)."""
    route = request.scope.get("route")
    dependant = getattr(route, "dependant", None)
    declared: set[str] = set()
    generic = False
    if dependant is not None:
        stack = [dependant]
        while stack:
            dep = stack.pop()
            declared.update(p.alias for p in dep.query_params)
            call = dep.call
            if call is list_params or isinstance(getattr(call, "__self__", None), ListSpec):
                generic = True
            stack.extend(dep.dependencies)
    return declared, generic


def strict_query(request: Request) -> None:
    """Route dependency for lists that offer no generic list parameters yet: every query
    parameter the route does not declare answers 422 (also ``filter[...]``, ``sort``,
    ``fields``, ``include`` and ``as_of``), so a caller never mistakes an unfiltered list
    for a filtered one. Routes that parse the generic parameters themselves are left to
    that parser. Use as ``@router.get(..., dependencies=[Depends(strict_query)])``."""
    declared, generic = _route_declares(request)
    for key in request.query_params:
        if key in declared:
            continue
        if generic and (key.startswith("filter[") or key in GENERIC_LIST_KEYS):
            continue
        raise _invalid(key, f"Parameter '{key}' wird von dieser Liste nicht angeboten.")
