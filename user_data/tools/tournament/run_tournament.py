"""
Strateji turnuvası (Aşama 3). Sıra:

  1. Her strateji için parametreleri SADECE in-sample'da (2020-03..2024-12)
     hyperopt ile ayarla (taban risk ayarlarıyla: 2.5 ATR, takip eden stop, 5x).
  2. Bu parametrelerle 8 varyantı (ATR çarpanı 1.5/2/2.5/3 x takip eden stop /
     sabit kâr al) in-sample'da test et.
  3. Varyantı SADECE in-sample sonuçlarına göre seç; sonra out-of-sample'da
     (2025-01..bugün) ayrı bir koşuyla, yine 100 USDT'den başlayarak test et.
  4. Walk-forward: 6 pencerede (24 ay eğit -> 6 ay test) seçilen varyantla
     yeniden ayarla ve test et.
  5. Ölç ve puanla (metrics.py; kurallar önceden sabit).
  6. En iyi 2 strateji için kaldıraç taraması (1x/2x/3x/5x).

Çalıştırma (research imajında):
  docker compose --profile research run --rm research \
      /freqtrade/user_data/tools/tournament/run_tournament.py [--strategies A B] [--skip-leverage]
"""
import argparse
import json
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor

import common as c
import metrics as m

SLOTS = threading.Semaphore(4)  # aynı anda en fazla 4 Freqtrade işlemi (4 çekirdek)


def slot(fn, *args, **kwargs):
    with SLOTS:
        return fn(*args, **kwargs)


def evaluate(result_zip, start: str, end: str) -> dict:
    trades = c.load_trades(result_zip)
    return m.period_metrics(trades, m.equity_curve(trades, start, end), start, end)


def is_and_oos(run: str, s: str, risk: dict, params) -> dict:
    """In-sample ve out-of-sample ayrı koşular; ikisi de 100 USDT ile başlar."""
    z_is = slot(c.backtest, f"{run}/is", s, f"{c.START}-{c.IS_END}", risk, params)
    z_oos = slot(c.backtest, f"{run}/oos", s, f"{c.IS_END}-{c.END}", risk, params)
    return {"zip_is": str(z_is), "zip_oos": str(z_oos),
            "is": evaluate(z_is, c.START, c.IS_END), "oos": evaluate(z_oos, c.IS_END, c.END)}


def run_strategy(s: str) -> dict:
    # 1) in-sample hyperopt
    params_is = slot(c.hyperopt, f"{s}/is_opt", s, f"{c.START}-{c.IS_END}", c.BASELINE_RISK,
                     min_trades=m.MIN_IS_TRADES)
    # 2) varyantlar
    variants = [c.variant_risk(a, e) for a in c.ATR_MULTIPLIERS for e in c.EXIT_MODES]
    with ThreadPoolExecutor(len(variants)) as ex:
        zips = list(ex.map(lambda r: slot(c.backtest, f"{s}/grid/{c.variant_name(r)}", s,
                                          f"{c.START}-{c.IS_END}", r, params_is), variants))
    grid = {}
    for r, z in zip(variants, zips):
        ev = evaluate(z, c.START, c.IS_END)
        grid[c.variant_name(r)] = {"risk": r, "zip_is": str(z), "is": ev, "is_score": m.is_score(ev)}
    # 3) varyant seçimi: sadece in-sample puanı
    chosen = max(grid.values(), key=lambda g: g["is_score"])
    risk = chosen["risk"]

    # 4) walk-forward
    def wf_window(w):
        tr_s, tr_e, te_s, te_e = w
        p = slot(c.hyperopt, f"{s}/wf/{te_s}/opt", s, f"{tr_s}-{tr_e}", risk, min_trades=30)
        z = slot(c.backtest, f"{s}/wf/{te_s}/test", s, f"{te_s}-{te_e}", risk, p)
        t = c.load_trades(z)
        eq = m.equity_curve(t, te_s, te_e)
        pj = json.loads(p.read_text())
        return {"window": f"{te_s}-{te_e}", "params": pj["params"],
                "defaults_used": pj.get("defaults_used", False),
                **m.period_metrics(t, eq, te_s, te_e)}

    with ThreadPoolExecutor(len(c.WF_WINDOWS)) as ex:
        wf = list(ex.map(wf_window, c.WF_WINDOWS))

    z_oos = slot(c.backtest, f"{s}/oos/{c.variant_name(risk)}", s, f"{c.IS_END}-{c.END}",
                 risk, params_is)
    m_is, m_oos = chosen["is"], evaluate(z_oos, c.IS_END, c.END)
    pj = json.loads(params_is.read_text())
    return {"strategy": s, "params_is": pj["params"], "defaults_used": pj.get("defaults_used", False),
            "chosen_variant": c.variant_name(risk), "risk": risk,
            "zip_is": chosen["zip_is"], "zip_oos": str(z_oos), "is": m_is, "oos": m_oos,
            "robustness": m.robustness(m_is, m_oos, wf), "walk_forward": wf, "grid": grid}


def leverage_sweep(res: dict) -> dict:
    s = res["strategy"]
    params = c.OUT / "runs" / s / "is_opt" / "strategies" / f"{s}.json"
    out = {}

    def one(lev):
        r = {**res["risk"], "leverage": lev}
        return lev, is_and_oos(f"{s}/lev/{c.variant_name(r)}", s, r, params)

    with ThreadPoolExecutor(len(c.LEVERAGES)) as ex:
        for lev, ev in ex.map(one, c.LEVERAGES):
            out[str(lev)] = ev
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategies", nargs="*", default=c.STRATEGIES)
    ap.add_argument("--skip-leverage", action="store_true")
    args = ap.parse_args()
    (c.OUT / "results").mkdir(parents=True, exist_ok=True)

    def safe(s):
        try:
            res = run_strategy(s)
        except Exception:
            traceback.print_exc()
            return None
        (c.OUT / "results" / f"{s}.json").write_text(json.dumps(res, indent=1, default=str))
        rb = res["robustness"]
        print(f"[bitti] {s}: varyant={res['chosen_variant']} puan={rb['score']:.3f} "
              f"geçti={rb['passed']}", flush=True)
        return res

    with ThreadPoolExecutor(len(args.strategies)) as ex:
        results = [r for r in ex.map(safe, args.strategies) if r]

    if args.skip_leverage or not results:
        return
    # 6) kaldıraç taraması: puanı en yüksek 2 strateji
    finalists = sorted(results, key=lambda r: r["robustness"]["score"], reverse=True)[:2]
    for res in finalists:
        res["leverage_sweep"] = leverage_sweep(res)
        (c.OUT / "results" / f"{res['strategy']}.json").write_text(
            json.dumps(res, indent=1, default=str))
        print(f"[kaldıraç taraması bitti] {res['strategy']}", flush=True)


if __name__ == "__main__":
    main()
