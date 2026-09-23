from __future__ import annotations

import asyncio
from functools import partial

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError

from fitness_bot.service.ports.object_storage import ObjectStorage


class InMemoryObjectStorage(ObjectStorage):
    def __init__(self) -> None:
        self._objects: dict[str, tuple[bytes, str]] = {}

    async def put(self, key: str, body: bytes, content_type: str) -> None:
        self._objects[key] = (body, content_type)

    async def get(self, key: str) -> bytes:
        try:
            body, _content_type = self._objects[key]
        except KeyError as exc:
            raise KeyError(key) from exc
        return body

    async def delete(self, key: str) -> None:
        self._objects.pop(key, None)


class S3ObjectStorage(ObjectStorage):
    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str,
        client: BaseClient | None = None,
    ) -> None:
        self._bucket = bucket
        self._client = client or boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region or None,
        )

    async def put(self, key: str, body: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            partial(
                self._client.put_object,
                Bucket=self._bucket,
                Key=key,
                Body=body,
                ContentType=content_type,
            ),
        )

    async def get(self, key: str) -> bytes:
        def _get() -> bytes:
            try:
                response = self._client.get_object(Bucket=self._bucket, Key=key)
            except ClientError as exc:
                error_code = exc.response.get("Error", {}).get("Code")
                if error_code in {"NoSuchKey", "404", "NotFound"}:
                    raise KeyError(key) from exc
                raise
            return response["Body"].read()

        return await asyncio.to_thread(_get)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(
            partial(self._client.delete_object, Bucket=self._bucket, Key=key),
        )
