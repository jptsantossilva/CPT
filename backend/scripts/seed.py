"""Seed script to create sample data in dev DB."""

from ..app.db import get_session, init_db
from ..app.models import Account, Holding, Price, Snapshot


def seed():
    init_db()
    with get_session() as s:
        a = Account(provider="binance", identifier="main", label="Binance Main")
        s.add(a)
        s.commit()
        s.refresh(a)
        h1 = Holding(
            account_id=a.id, asset_symbol="BTC", asset_name="Bitcoin", quantity=0.01234
        )
        h2 = Holding(
            account_id=a.id, asset_symbol="USDT", asset_name="Tether", quantity=123.45
        )
        s.add_all([h1, h2])
        snap = Snapshot(total_eur=1000.0)
        s.add(snap)
        s.commit()


if __name__ == "__main__":
    seed()
