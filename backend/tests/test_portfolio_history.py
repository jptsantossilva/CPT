import json
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
    assert p["exchanges"] == {}
    assert out["exchange_accounts"] == {}


def test_build_portfolio_history_reads_exchange_accounts_and_uses_latest_label():
    rows = [
        _Snap(
            datetime(2026, 2, day, 0, 0, 0, tzinfo=timezone.utc),
            100.0,
            120.0,
            json.dumps(
                {
                    "exchanges": [
                        {
                            "key": "account:7",
                            "account_id": 7,
                            "provider": "okx",
                            "label": label,
                            "eur": eur,
                            "usd": usd,
                        }
                    ]
                }
            ),
        )
        for day, label, eur, usd in (
            (1, "OKX-old", 40, 48),
            (2, "OKX-bec1", 55, 66),
        )
    ]

    out = history.build_portfolio_history(rows)

    assert out["points"][0]["exchanges"]["account:7"] == {"eur": 40.0, "usd": 48.0}
    assert out["points"][1]["exchanges"]["account:7"] == {"eur": 55.0, "usd": 66.0}
    assert out["exchange_accounts"]["account:7"] == {
        "account_id": 7,
        "provider": "okx",
        "label": "OKX-bec1",
    }


def test_build_portfolio_history_keeps_missing_exchange_data_absent():
    rows = [
        _Snap(datetime(2026, 2, 1, tzinfo=timezone.utc), 100.0, 120.0, "{}"),
        _Snap(
            datetime(2026, 2, 2, tzinfo=timezone.utc),
            100.0,
            120.0,
            '{"exchanges":[{"key":"account:7","account_id":7,"provider":"okx","label":"OKX-bec1","eur":0,"usd":0}]}',
        ),
        _Snap(datetime(2026, 2, 3, tzinfo=timezone.utc), 100.0, 120.0, "{}"),
    ]

    out = history.build_portfolio_history(rows)

    assert out["points"][0]["exchanges"] == {}
    assert out["points"][1]["exchanges"]["account:7"] == {"eur": 0.0, "usd": 0.0}
    assert out["points"][2]["exchanges"] == {}
