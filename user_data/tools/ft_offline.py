"""
Freqtrade'i Binance'in canlı API'sine bağlanmadan çalıştırır (sadece backtest /
hyperopt / analiz için).

Freqtrade açılışta Binance'in işlem kurallarını (min emir, fiyat/miktar adımı...)
canlı API'den (fapi.binance.com/fapi/v1/exchangeInfo) okur. Bu API bazı
sunuculardan/ülkelerden kapalıdır (HTTP 451). Bu script aynı bilgiyi
user_data/market_snapshot/exchangeInfo.json dosyasından verir; geri kalan her
şey normal Freqtrade'dir.

Snapshot'ı yenilemek için: tarayıcıda
  https://fapi.binance.com/fapi/v1/exchangeInfo
açıp kaydet ve user_data/market_snapshot/exchangeInfo.json'ın yerine koy.

Kullanım (normal "freqtrade" komutu yerine):
  docker compose run --rm --entrypoint python freqtrade \
      /freqtrade/user_data/tools/ft_offline.py backtesting --strategy ...
"""
import functools
import json
import sys
from pathlib import Path

import ccxt
import ccxt.async_support as ccxt_async

SNAPSHOT = Path("/freqtrade/user_data/market_snapshot/exchangeInfo.json")
ALLOWED = {"backtesting", "hyperopt", "backtesting-show", "backtesting-analysis",
           "hyperopt-list", "hyperopt-show", "lookahead-analysis", "recursive-analysis",
           "list-markets", "list-pairs", "test-pairlist", "plot-dataframe", "plot-profit",
           "show-config", "list-data"}


def patch_binance(snapshot: dict) -> None:
    def sync_exchange_info(self, params={}):
        return snapshot

    async def async_exchange_info(self, params={}):
        return snapshot

    def only_linear(fetch_markets, is_async):
        # Sadece USD-M vadeli piyasaları yükle (spot/coin-M canlı API ister).
        def set_options(self):
            self.options["fetchMarkets"] = {"types": ["linear"], "loadAllOptions": False}

        if is_async:
            @functools.wraps(fetch_markets)
            async def wrapper(self, params={}):
                set_options(self)
                return await fetch_markets(self, params)
        else:
            @functools.wraps(fetch_markets)
            def wrapper(self, params={}):
                set_options(self)
                return fetch_markets(self, params)
        return wrapper

    for cls, getter, is_async in ((ccxt.binance, sync_exchange_info, False),
                                  (ccxt_async.binance, async_exchange_info, True)):
        cls.fapiPublicGetExchangeInfo = getter
        cls.fapipublic_get_exchangeinfo = getter
        cls.fetch_markets = only_linear(cls.fetch_markets, is_async)


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command not in ALLOWED:
        print(f"ft_offline.py sadece analiz komutları içindir, '{command}' çalıştırılamaz.\n"
              f"İzin verilenler: {', '.join(sorted(ALLOWED))}")
        return 2
    patch_binance(json.loads(SNAPSHOT.read_text()))
    from freqtrade.main import main as freqtrade_main
    return freqtrade_main(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
