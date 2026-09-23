from __future__ import annotations

from collections.abc import Sequence
from urllib.parse import urljoin

import httpx

from fitness_bot.service.ports.video_search import RutubeSearch, VideoSearchHit


class RutubeApiSearch(RutubeSearch):
    """Public Rutube search API — URLs come from search results only."""

    def __init__(self, *, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._owns_client = client is None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def search(self, query: str, *, limit: int = 5) -> Sequence[VideoSearchHit]:
        client = await self._http()
        response = await client.get(
            "https://rutube.ru/api/search/video/",
            params={"query": query, "page": 1},
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results") or payload.get("videos") or []
        hits: list[VideoSearchHit] = []
        for item in results:
            video_id = item.get("id") or item.get("video_id")
            video_url = item.get("video_url") or item.get("url")
            if video_url:
                url = str(video_url)
            elif video_id:
                url = urljoin("https://rutube.ru/video/", f"{video_id}/")
            else:
                continue
            hits.append(
                VideoSearchHit(
                    platform="rutube",
                    url=url,
                    title=str(item.get("title") or ""),
                ),
            )
            if len(hits) >= limit:
                break
        return hits
