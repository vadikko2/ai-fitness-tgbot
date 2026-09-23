from __future__ import annotations

import cqrs


class Query(cqrs.Request):
    """Base query DTO."""


class QueryResult(cqrs.Response):
    """Base query result DTO."""
