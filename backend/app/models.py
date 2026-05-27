from datetime import datetime
from typing import List, Optional

from sqlmodel import Field, Relationship, SQLModel


class Account(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    provider: str
    identifier: str
    label: Optional[str] = None
    # Encrypted API credentials (Fernet). Keep empty if not applicable.
    api_key_encrypted: Optional[str] = None
    api_secret_encrypted: Optional[str] = None
    is_exchange: bool = False


class Holding(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    account_id: int
    asset_symbol: str
    asset_name: Optional[str] = None
    quantity: float


class Price(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    asset_symbol: str
    price_eur: float
    price_usd: Optional[float] = None
    ts: datetime = Field(default_factory=datetime.utcnow)


class PriceSymbolMapping(SQLModel, table=True):
    symbol: str = Field(primary_key=True)
    provider: str = "coingecko"
    provider_id: str
    label: Optional[str] = None
    enabled: bool = True
    notes: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Snapshot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    total_eur: float
    total_usd: Optional[float] = None
    meta: Optional[str] = None


class NFTCollection(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    chain: str
    contract_address: str
    name: Optional[str]
    floor_price_eur: Optional[float]


class NFTItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    collection_id: int
    token_id: str
    owner: Optional[str]
    last_sale_eur: Optional[float]


class NFTHolding(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    account_id: int
    chain: str
    contract: str
    token_id: str
    name: Optional[str] = None
    collection: Optional[str] = None
    owner: Optional[str] = None
    valuation_symbol: Optional[str] = None
    valuation_native: Optional[float] = None
    valuation_source: Optional[str] = None
    valuation_confidence: Optional[str] = None
    valuation_usd: Optional[float] = None
    valuation_eur: Optional[float] = None
    is_spam: bool = False
    has_floor_or_last_sale: bool = False
    visibility: str = "visible"


class NFTBlacklist(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    chain: str
    contract: str
    token_id: str
    reason: Optional[str] = None


class AppSetting(SQLModel, table=True):
    # Generic key/value settings storage for admin-managed runtime config.
    key: str = Field(primary_key=True)
    value: str


class NotificationConfig(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    channel: str  # email|telegram
    enabled: bool = True
    schedule_mode: str = "inherit"  # inherit|custom
    interval_value: int = 1
    interval_unit: str = "days"  # minutes|hours|days|weeks
    time_of_day: str = "00:00"  # HH:MM
    day_of_week: str = "monday"
    timezone: str = "UTC"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class NotificationRecipient(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    notification_id: int
    type: str  # email|telegram_chat
    value: str  # email or chat_id
    enabled: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class NotificationAnchor(SQLModel, table=True):
    notification_id: int = Field(primary_key=True)
    last_snapshot_id: Optional[int] = None
    # Last sync Snapshot.id consumed by this notification scheduler.
    last_sync_snapshot_id: Optional[int] = None
    last_sent_at: Optional[datetime] = None


class NotificationRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    notification_id: int
    status: str  # running|sent|partial|failed
    reason: str = "scheduled"  # scheduled|manual
    scheduled_for: Optional[datetime] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None
    sent_recipients: int = 0
    failed_recipients: int = 0
    payload_json: Optional[str] = None
    error: Optional[str] = None


class NotificationSnapshot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    notification_id: int
    captured_at: datetime = Field(default_factory=datetime.utcnow)
    total_eur: float
    total_usd: Optional[float] = None
    base_snapshot_id: Optional[int] = None


class NotificationAssetSnapshot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    snapshot_id: int
    asset_type: str  # coin|nft
    asset_key: str
    asset_label: str
    value_eur: float
    value_usd: Optional[float] = None
