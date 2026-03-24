from datetime import datetime, timezone

from backend.app.services import history


class _Snap:
    def __init__(self, ts: datetime, total_eur: float, total_usd: float, meta: str):
        self.timestamp = ts
        self.total_eur = total_eur
        self.total_usd = total_usd
        self.meta = meta


def test_build_portfolio_history_reads_meta_totals_and_items():
    rows = [
        _Snap(
            datetime(2026, 2, 1, 0, 0, 0, tzinfo=timezone.utc),
            100.0,
            120.0,
            '{"totals":{"coins_eur":100,"coins_usd":120,"nfts_eur":5,"nfts_usd":6,"portfolio_eur":105,"portfolio_usd":126},"coins":[{"key":"BTC","name":"BTC","eur":100,"usd":120}],"nfts":[{"key":"ethereum:0xabc:1","name":"My NFT","eur":5,"usd":6}]}',
        )
    ]

    out = history.build_portfolio_history(rows)
    assert len(out["points"]) == 1
    p = out["points"][0]
    assert float(p["totals"]["portfolio_eur"]) == 105.0
    assert float(p["coins"]["BTC"]["eur"]) == 100.0
    assert float(p["nfts"]["ethereum:0xabc:1"]["usd"]) == 6.0
    assert out["coin_labels"]["BTC"] == "BTC"
    assert out["nft_labels"]["ethereum:0xabc:1"] == "My NFT"
