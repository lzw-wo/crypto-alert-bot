"""通用 RSS/Atom 订阅源:每个订阅绑定一个 feed URL,支持关键词在引擎层过滤。

- feedparser 解析任意 RSS/Atom
- 首次拉取某 URL 只建基线(不推历史),之后只返回新条目
- 单个 URL 拉取失败不影响其他订阅
"""
import hashlib
import logging

import feedparser
import httpx

from .base import AlertItem, Source

logger = logging.getLogger(__name__)


class RSSFeedSource(Source):
    def __init__(self, feed_provider, proxy: str | None = None, timeout: float = 15.0):
        # feed_provider: 无参可调用,返回需要监控的 feed URL 列表(从订阅中提取)
        self._client = httpx.AsyncClient(proxy=proxy, timeout=timeout, trust_env=False)
        self._feed_provider = feed_provider
        self._baseline: set[str] = set()          # 已完成基线的 URL
        self._seen: dict[str, set[str]] = {}      # url -> 已见条目 key 集合

    async def fetch(self) -> list[AlertItem]:
        urls = self._feed_provider()
        if not urls:
            return []
        items: list[AlertItem] = []
        for url in urls:
            try:
                items.extend(await self._fetch_one(url))
            except Exception as exc:
                logger.warning("RSS 拉取失败 %s: %s", url, exc)
        return items

    async def _fetch_one(self, url: str) -> list[AlertItem]:
        resp = await self._client.get(url)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)

        seen = self._seen.setdefault(url, set())
        baseline_done = url in self._baseline
        out: list[AlertItem] = []
        for entry in parsed.entries:
            key = (
                entry.get("id")
                or entry.get("link")
                or hashlib.md5((entry.get("title", "") + entry.get("link", "")).encode()).hexdigest()
            )
            if key in seen:
                continue
            seen.add(key)
            if len(seen) > 3000:
                self._seen[url] = set(list(seen)[-1500:])
            item = AlertItem(
                category="rss",
                key=key,
                asset=url,
                value=1.0,
                extra={
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "summary": (entry.get("summary") or entry.get("description") or ""),
                },
            )
            if not baseline_done:
                continue  # 首次只建基线,不推历史
            out.append(item)

        if not baseline_done:
            self._baseline.add(url)
        return out

    async def aclose(self):
        await self._client.aclose()
