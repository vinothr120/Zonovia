from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str
    field_errors: dict[str, Any] | None = None


class PageMeta(BaseModel):
    page: int
    page_size: int
    total: int


class Envelope(BaseModel, Generic[T]):
    data: T | None = None
    meta: PageMeta | None = None
    error: ErrorDetail | None = None


def ok(data: Any, meta: PageMeta | None = None) -> dict[str, Any]:
    return {"data": data, "meta": meta, "error": None}
