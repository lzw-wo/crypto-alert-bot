"""Gate.io 现货行情适配器(无需 key,本机直连可达)。

一次请求拉取全量现货 ticker,本地按订阅币种过滤。
"""
import httpx

from .base import PricePoint, Source

API_URL = "https://api.gateio.ws/api/v4/spot/tickers"


class GateIoPriceSource(Source):
    def __init__(self, proxy: str | None = None, timeout: float = 10.0):
        # trust_env=False:不继承 Windows 系统代理(避免被坏 VPN 隧道劫持),默认直连;
        # 仅当显式传入 proxy 时走代理
        self._client = httpx.AsyncClient(
            proxy=proxy, timeout=timeout, trust_env=False
        )

    async def fetch(self) -> list[PricePoint]:
        resp = await self._client.get(API_URL)
        resp.raise_for_status()
        by_asset: dict[str, float] = {}
        for t in resp.json():
            pair = t.get("currency_pair") or ""   # 如 "BTC_USDT"
            last = t.get("last")
            if "_" not in pair or not last:
                continue
            base, quote = pair.split("_", 1)
            if quote != "USDT":   # 只取 USDT 计价对,避免同资产多报价重复
                continue
            try:
                price = float(last)
            except (TypeError, ValueError):
                continue
            if price > 0 and base not in by_asset:
                by_asset[base] = price
        return [PricePoint(asset=a, price=p, quote="USDT") for a, p in by_asset.items()]

    async def aclose(self):
        await self._client.aclose()
