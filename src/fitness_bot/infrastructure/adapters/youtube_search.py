from __future__ import annotations

from collections.abc import Sequence

import httpx

from fitness_bot.service.ports.video_search import VideoSearchHit, YouTubeSearch


class YouTubeDataApiSearch(YouTubeSearch):
    def __init__(self, api_key: str, *, client: httpx.AsyncClient | None = None) -> None:
        if not api_key.strip():
            raise ValueError("YOUTUBE_API_KEY is required for catalog video search")
        self._api_key = api_key
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
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "part": "snippet",
                "type": "video",
                "q": query,
                "maxResults": min(limit, 5),
                "key": self._api_key,
            },
        )
        response.raise_for_status()
        payload = response.json()
        hits: list[VideoSearchHit] = []
        for item in payload.get("items") or []:
            video_id = (item.get("id") or {}).get("videoId")
            if not video_id:
                continue
            snippet = item.get("snippet") or {}
            hits.append(
                VideoSearchHit(
                    platform="youtube",
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    title=str(snippet.get("title") or ""),
                ),
            )
            if len(hits) >= limit:
                break
        return hits
