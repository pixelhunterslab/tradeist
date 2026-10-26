"""
Performans ölçüleri ve sağlamlık puanı.

ÖNEMLİ: Puanlama ve eleme kuralları sonuçlar görülmeden ÖNCE yazıldı ve
sonradan değiştirilmez (sonuca göre kural değiştirmek de bir tür hiledir).

Özsermaye (equity) eğrisi kapanmış işlemlerden hesaplanır (açık işlemlerin
anlık kâr/zararı dahil değil; düşüş gerçekte biraz daha derin olabilir).
"""
import numpy as np
import pandas as pd

START_BALANCE = 100.0

# ---- Eleme kuralları (biri bile tutmazsa strateji "sağlam değil") ----
MIN_IS_TRADES = 100          # 2020-2024 arası en az 100 işlem
MIN_OOS_TRADES = 30          # 2025-bugün arası en az 30 işlem
MIN_OOS_PROFIT_FACTOR = 1.10
MAX_DRAWDOWN = 0.40          # in-sample ve out-of-sample'da en fazla %40 düşüş
MIN_WF_PROFITABLE = 4        # 6 walk-forward test penceresinin en az 4'ü kârlı


def equity_curve(trades: pd.DataFrame, start: str, end: str) -> pd.Series:
    """Günlük özsermaye (kapanmış işlemlere göre)."""
    days = pd.date_range(pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC"), freq="D")
    if trades.empty:
        return pd.Series(START_BALANCE, index=days)
    pnl = trades.groupby(trades["close_date"].dt.floor("D"))["profit_abs"].sum()
    return START_BALANCE + pnl.reindex(days, fill_value=0.0).cumsum()


def _clip01(x: float) -> float:
    return float(np.clip(x, 0.0, 1.0)) if np.isfinite(x) else 0.0


def period_metrics(trades: pd.DataFrame, equity: pd.Series, start: str, end: str) -> dict:
    s, e = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC")
    before = equity[equity.index < s]
    e0 = before.iloc[-1] if len(before) else START_BALANCE
    eq = equity[(equity.index >= s) & (equity.index < e)]
    t = trades[(trades["close_date"] >= s) & (trades["close_date"] < e)] if len(trades) else trades
    years = max((e - s).days / 365.25, 1e-9)
    ret = eq.iloc[-1] / e0 - 1 if len(eq) else 0.0
    cagr = (1 + ret) ** (1 / years) - 1 if ret > -1 else -1.0
    path = pd.concat([pd.Series([e0]), eq.reset_index(drop=True)])
    dd_series = 1 - path / path.cummax()
    max_dd = float(dd_series.max())
    wins = t["profit_abs"][t["profit_abs"] > 0].sum() if len(t) else 0.0
    losses = -t["profit_abs"][t["profit_abs"] < 0].sum() if len(t) else 0.0
    return {
        "trades": int(len(t)),
        "return_pct": 100 * ret,
        "cagr_pct": 100 * cagr,
        "max_dd_pct": 100 * max_dd,
        "calmar": cagr / max_dd if max_dd > 0 else (np.inf if cagr > 0 else 0.0),
        "profit_factor": wins / losses if losses > 0 else (np.inf if wins > 0 else 0.0),
        "win_rate_pct": 100 * float((t["profit_abs"] > 0).mean()) if len(t) else 0.0,
        "avg_hours": float((t["close_date"] - t["open_date"]).dt.total_seconds().mean() / 3600)
        if len(t) else 0.0,
        "funding_usdt": float(t["funding_fees"].sum()) if len(t) and "funding_fees" in t else 0.0,
        "end_equity": float(eq.iloc[-1]) if len(eq) else e0,
    }


def is_score(m_is: dict) -> float:
    """Varyant seçimi (ATR çarpanı / çıkış modu) SADECE in-sample ile yapılır."""
    if m_is["trades"] < MIN_IS_TRADES:
        return 0.0
    return (0.5 * _clip01(m_is["calmar"] / 2) + 0.3 * _clip01(m_is["profit_factor"] - 1)
            + 0.2 * _clip01(1 - m_is["max_dd_pct"] / 100 / MAX_DRAWDOWN))


def robustness(m_is: dict, m_oos: dict, wf: list[dict]) -> dict:
    """Sıralama puanı (0-1) ve eleme sebepleri. Toplam kâra göre DEĞİL.
    In-sample ve out-of-sample ayrı koşulardır, ikisi de 100 USDT ile başlar."""
    worst_dd = max(m_is["max_dd_pct"], m_oos["max_dd_pct"]) / 100
    wf_profitable = sum(1 for w in wf if w["return_pct"] > 0)
    reasons = []
    if m_is["trades"] < MIN_IS_TRADES:
        reasons.append(f"in-sample işlem sayısı az ({m_is['trades']} < {MIN_IS_TRADES})")
    if m_oos["trades"] < MIN_OOS_TRADES:
        reasons.append(f"out-of-sample işlem sayısı az ({m_oos['trades']} < {MIN_OOS_TRADES})")
    if m_oos["return_pct"] <= 0:
        reasons.append(f"out-of-sample zararda ({m_oos['return_pct']:.1f}%)")
    if m_oos["profit_factor"] < MIN_OOS_PROFIT_FACTOR:
        reasons.append(f"out-of-sample kâr faktörü düşük ({m_oos['profit_factor']:.2f} "
                       f"< {MIN_OOS_PROFIT_FACTOR})")
    if worst_dd > MAX_DRAWDOWN:
        reasons.append(f"en büyük düşüş çok fazla ({worst_dd * 100:.0f}% > "
                       f"{MAX_DRAWDOWN * 100:.0f}%)")
    if wf_profitable < MIN_WF_PROFITABLE:
        reasons.append(f"walk-forward tutarsız ({wf_profitable}/{len(wf)} pencere kârlı "
                       f"< {MIN_WF_PROFITABLE})")
    degradation = (m_oos["cagr_pct"] / m_is["cagr_pct"]) if m_is["cagr_pct"] > 0 else 0.0
    score = (0.30 * _clip01(m_oos["calmar"] / 2)
             + 0.20 * _clip01(m_oos["profit_factor"] - 1)
             + 0.20 * (wf_profitable / len(wf) if wf else 0.0)
             + 0.15 * _clip01(1 - worst_dd / MAX_DRAWDOWN)
             + 0.15 * _clip01(degradation))
    return {"score": score, "passed": not reasons, "reject_reasons": reasons,
            "wf_profitable": wf_profitable}
