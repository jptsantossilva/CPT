"""Generate synthetic daily portfolio history snapshots for chart testing."""

import argparse
import json
import math
import random
from datetime import datetime, timedelta, timezone

from ..app.db import get_session
from ..app.models import Snapshot


def _series_value(base: float, day: int, noise: float, trend: float, wave: float, period: float) -> float:
    n = random.uniform(-noise, noise)
    w = math.sin(day / period) * wave
    return max(0.0, base + day * trend + w + n)


def seed_history(days: int, replace: bool) -> int:
    now = datetime.now(timezone.utc)
    start_day = (now - timedelta(days=days - 1)).replace(hour=22, minute=0, second=0, microsecond=0)

    inserted = 0
    with get_session() as s:
        if replace:
            s.query(Snapshot).delete()

        for i in range(days):
            ts = start_day + timedelta(days=i)

            btc_eur = _series_value(12000, i, 240, 8, 450, 14)
            btc_usd = btc_eur * 1.18
            eth_eur = _series_value(4800, i, 120, 3, 210, 11)
            eth_usd = eth_eur * 1.18
            usdc_eur = _series_value(6000, i, 30, 1, 40, 20)
            usdc_usd = usdc_eur * 1.18
            nfts_eur = _series_value(1600, i, 80, 2.2, 160, 18)
            nfts_usd = nfts_eur * 1.18

            coins_eur = btc_eur + eth_eur + usdc_eur
            coins_usd = btc_usd + eth_usd + usdc_usd
            total_eur = coins_eur + nfts_eur
            total_usd = coins_usd + nfts_usd

            meta = {
                "holdings_count": 6,
                "symbols_count": 3,
                "nfts_count": 3,
                "totals": {
                    "coins_eur": coins_eur,
                    "coins_usd": coins_usd,
                    "nfts_eur": nfts_eur,
                    "nfts_usd": nfts_usd,
                    "portfolio_eur": total_eur,
                    "portfolio_usd": total_usd,
                },
                "coins": [
                    {"key": "BTC", "name": "BTC", "eur": btc_eur, "usd": btc_usd},
                    {"key": "ETH", "name": "ETH", "eur": eth_eur, "usd": eth_usd},
                    {"key": "USDC", "name": "USDC", "eur": usdc_eur, "usd": usdc_usd},
                ],
                "nfts": [
                    {"key": "ethereum:0xabc:1", "name": "Fontana #498", "eur": nfts_eur * 0.5, "usd": nfts_usd * 0.5},
                    {"key": "ethereum:0xdef:2", "name": "Trichro-matic #296", "eur": nfts_eur * 0.3, "usd": nfts_usd * 0.3},
                    {"key": "base:0xghi:3", "name": "BEL_Plate", "eur": nfts_eur * 0.2, "usd": nfts_usd * 0.2},
                ],
            }

            s.add(
                Snapshot(
                    timestamp=ts,
                    total_eur=total_eur,
                    total_usd=total_usd,
                    meta=json.dumps(meta),
                )
            )
            inserted += 1
        s.commit()
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed synthetic history snapshots for Dashboard chart testing.")
    parser.add_argument("--days", type=int, default=180, help="Number of daily points to generate")
    parser.add_argument("--replace", action="store_true", help="Delete existing snapshots before inserting")
    args = parser.parse_args()

    days = max(7, min(int(args.days), 1200))
    count = seed_history(days=days, replace=bool(args.replace))
    print(f"Seeded {count} snapshot rows.")


if __name__ == "__main__":
    main()
