"""WhaleAlert 巨鲸转账适配器(需免费 API key:https://whale-alert.io)。

- 用 cursor 增量拉取,hash 去重
- 首次拉取只建基线(不推历史,避免轰炸)
- 未配置 key 时优雅降级,返回空列表
"""
import logging

import httpx

from .base import AlertItem, Source

logger = logging.getLogger(__name__)

API_URL = "https://api.whale-alert.io/v1/transactions"
DEFAULT_MIN_USD = 1_000_000  # 默认只拉 100 万美元以上的大额转账


class WhaleAlertSource(Source):
    def __init__(
        self,
        api_key: str = "",
        proxy: str | None = None,
        min_value: int = DEFAULT_MIN_USD,
        timeout: float = 10.0,
    ):
        self._client = httpx.AsyncClient(proxy=proxy, timeout=timeout, trust_env=False)
        self._api_key = api_key
        self._min_value = min_value
        self._cursor: str | None = None
        self._baseline_done = False
        self._seen: set[str] = set()

    async def fetch(self) -> list[AlertItem]:
        if not self._api_key:
            logger.warning("未配置 WHALEALERT_API_KEY,跳过巨鲸拉取(价格提醒不受影响)")
            return []

        params: dict = {
            "api_key": self._api_key,
            "min_value": self._min_value,
            "limit": 20,
        }
        if self._cursor:
            params["cursor"] = self._cursor

        try:
            resp = await self._client.get(API_URL, params=params)
        except httpx.HTTPError as exc:
            logger.warning("WhaleAlert 请求失败: %s", exc)
            return []

        if resp.status_code == 401:
            logger.warning("WhaleAlert key 无效或已达请求限额(免费版约 60 次/小时)")
            return []
        if resp.status_code != 200:
            logger.warning("WhaleAlert 返回异常状态: %s", resp.status_code)
            return []

        data = resp.json()
        self._cursor = data.get("cursor") or self._cursor

        items: list[AlertItem] = []
        for tx in data.get("transactions") or []:
            tx_hash = tx.get("hash") or f"{tx.get('blockchain')}:{tx.get('timestamp')}"
            if tx_hash in self._seen:
                continue
            self._seen.add(tx_hash)
            # 简单裁剪,防止长期运行内存膨胀
            if len(self._seen) > 5000:
                self._seen = set(list(self._seen)[-2000:])
            try:
                amount_usd = float(tx.get("amount_usd") or 0)
            except (TypeError, ValueError):
                amount_usd = 0.0
            items.append(
                AlertItem(
                    category="whale",
                    key=tx_hash,
                    asset=(tx.get("symbol") or "?").upper(),
                    value=amount_usd,
                    extra={
                        "blockchain": tx.get("blockchain") or "?",
                        "from": self._short_addr((tx.get("from") or {}).get("address")),
                        "to": self._short_addr((tx.get("to") or {}).get("address")),
                        "amount": tx.get("amount"),
                    },
                )
            )

        # 首次拉取只建基线,不推送历史交易
        if not self._baseline_done:
            self._baseline_done = True
            logger.info("WhaleAlert 基线已建立,共 %d 条新交易,本轮不推送", len(items))
            return []

        return items

    @staticmethod
    def _short_addr(addr: str | None) -> str:
        if not addr:
            return "?"
        addr = str(addr)
        return addr[:10] + "…" if len(addr) > 12 else addr

    async def aclose(self):
        await self._client.aclose()
