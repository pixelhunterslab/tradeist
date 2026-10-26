# Backtest raporları için: resmi Freqtrade imajı + grafik kütüphanesi.
FROM freqtradeorg/freqtrade:2026.9
RUN pip install --user --no-cache-dir matplotlib==3.10.7
