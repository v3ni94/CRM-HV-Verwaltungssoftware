"""pgvector column type without the ``pgvector`` Python package (M7-03, ADR 0001 unchanged).

The extension is created by ``infra/postgres/sql/bootstrap.sql`` (superuser); the baseline
migration checks its presence. Values travel as the text form ``[0.1,0.2,...]`` that the
``vector`` input function accepts; results are parsed back to ``list[float]``. Only cosine
distance (``<=>``) is used (``Vector.cosine_distance``)."""

from typing import Any

from sqlalchemy import Float
from sqlalchemy.sql import operators
from sqlalchemy.types import UserDefinedType


def to_db(value: list[float] | None) -> str | None:
    if value is None:
        return None
    return "[" + ",".join(repr(float(v)) for v in value) + "]"


def from_db(value: object) -> list[float] | None:
    if value is None:
        return None
    text = value.decode() if isinstance(value, bytes | bytearray) else str(value)
    text = text.strip()
    if text.startswith("["):
        text = text[1:-1]
    return [float(v) for v in text.split(",") if v.strip()] if text else []


class Vector(UserDefinedType[list[float]]):
    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **kw: Any) -> str:
        return f"vector({self.dimensions})"

    def bind_processor(self, dialect: Any) -> Any:
        return to_db

    def result_processor(self, dialect: Any, coltype: Any) -> Any:
        return from_db

    class comparator_factory(UserDefinedType.Comparator[list[float]]):  # noqa: N801
        def cosine_distance(self, other: list[float]) -> Any:
            # The right operand is bound with the column type, so the list goes through
            # ``bind_processor`` (text form) like any inserted value.
            return self.operate(operators.custom_op("<=>", return_type=Float()), other).cast(
                Float()
            )
