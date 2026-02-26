from pathlib import Path

from pydantic import AnyHttpUrl, BaseSettings

ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT_DIR / ".env"


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./dev.db"
    BINANCE_API_KEY: str | None = None
    BINANCE_API_SECRET: str | None = None
    ALCHEMY_API_KEY: str | None = None
    OPENSEA_API_KEY: str | None = None
    NFT_OPENSEA_ENABLED: bool = True
    NFT_OPENSEA_MAX_LOOKUPS: int = 30
    NFT_CHAINS: str = "ethereum"
    NFT_SCAM_SLUG_PATTERNS: str = (
        "airdrop,voucher,reward,claim,coupon,redeem,free,mint-pass,mintpass,usdc,usdt,busd,dai,shib"
    )
    ETH_RPC_URL: str | None = None
    BASE_RPC_URL: str | None = None
    POLYGON_RPC_URL: str | None = None
    SOLANA_RPC_URL: str | None = None
    SOLANA_RPC_FALLBACK_URL: AnyHttpUrl = "https://api.mainnet.solana.com"
    SOLANA_TOKEN_LIST_URL: AnyHttpUrl = "https://tokens.jup.ag/tokens"
    SOLANA_TOKEN_LOOKUP_URL_TEMPLATE: str = "https://lite-api.jup.ag/tokens/v1/token/{mint}"
    BTC_API_BASE: AnyHttpUrl = "https://blockstream.info/api"
    ENCRYPTION_KEY: str | None = None
    COINGECKO_API_BASE: AnyHttpUrl = "https://api.coingecko.com/api/v3"
    PORT: int = 8000

    class Config:
        env_file = str(ENV_PATH)


settings = Settings()
