# Changelog

All notable changes to this project will be documented in this file.

## [2026.07.20]

### Fixed
- Distinguished native EVM assets from ERC-20 tokens by chain and contract address, preventing arbitrary contracts that reuse symbols such as `ETH` from receiving native-asset prices.
- Fixed contract-address pricing for legitimate ERC-20 holdings such as USDC and WETH by resolving contracts through CoinGecko's platform map, avoiding the keyless token-price endpoint's batch restriction.
- Kept unknown contracts safely unpriced instead of falling back to potentially ambiguous symbol-only prices.
- Hidden ERC-20 tokens that impersonate a chain's native symbol from portfolio totals by default, with an optional Coins-page diagnostic view showing the suspicious contract and reason.
- Added backward-compatible holding/price identity migrations and contract-aware asset API fields for existing SQLite and PostgreSQL deployments.

## [2026.05.27]

### Fixed
- Fixed Toncoin valuation by mapping `TON` explicitly to CoinGecko's `the-open-network` asset id.
- Added a CPT-specific `AGENTS.md` guide adapted from the BEC project context.
- Changed the sidebar app version indicator to derive from the latest dated `CHANGELOG.md` entry instead of a hardcoded frontend constant.
- Fixed the frontend Docker build by copying the root `CHANGELOG.md` into the build image.
- Replaced hardcoded CoinGecko symbol overrides with DB-managed price mappings seeded from the previous defaults and added a Settings page to manage them.

## [2026.04.02]

### Changed
- Split former `Admin` area into two sections:
  - `Accounts` page for Binance Accounts + Wallets management only.
  - `Sync & Notifications` page for `Automatic Sync Schedule` and `Portfolio Notifications`.
- Improved Portfolio Notifications preview UX in Admin with a dedicated modal and clearer labels for HTML vs plain-text preview blocks.
- Added a discreet app version indicator (`YYYY.MM.DD` from latest changelog date) in the sidebar.
- Refined Portfolio Notifications scheduling: `Automatic Sync Schedule` now triggers only after new automatic sync snapshots (manual sync snapshots are ignored).
- Improved notification analytics logic: comparison is based on latest vs previous sync snapshots, with better filtering for noisy/low-value movers.
- Updated notification currency handling to follow app `USD/EUR` preference and send a single selected currency in messages.
- Redesigned notification email content (plain text + HTML): cleaner portfolio header, compact period line, colored trend indicators, and simplified Top 5 sections.
- Simplified Admin notification wording/labels and schedule help text for better clarity.

## [2026.03.26]

### Changed
- Fixed dashboard total mismatch by making `Total Portfolio` use full portfolio totals (`coins + NFTs`) from snapshot metadata, aligned with `Portfolio Price History`.
- Improved Admin Notifications UX:
  - Renamed schedule option label from `Inherit` to `Automatic Sync Schedule`.
  - Renamed field label to `Schedule Mode`.
  - Added contextual help via tooltip on the `Schedule Mode` label.
- Updated notification comparison logic to always use sync snapshots (`latest` vs `previous`) instead of `last notification` anchor snapshots.
- Notification currency now follows the app currency toggle (`USD/EUR`) via persisted backend setting (`/settings/currency`), and messages are sent in a single selected currency.
- Added sync timestamps to notification messages, including time difference (`Diff Xd Yh`) between compared snapshots.
- Improved notification message formatting (`Portfolio Snapshot` block) and added HTML email rendering with color-coded variations (green for `>= 0`, red for `< 0`) while keeping plain-text fallback.
- Updated notification email subject to include only the day (`Portfolio update - YYYY-MM-DD`) to reduce Gmail thread grouping.
- Refined movers logic for `Top 5 up/down`:
  - Ignore assets with valuation at or below threshold in USD.
  - Ignore transitions from low/noisy valuations that generate unrealistic percentage spikes.
- `Automatic Sync Schedule` notification dispatch now waits for a new sync snapshot and tracks consumption with `last_sync_snapshot_id` in `NotificationAnchor`.
- `Automatic Sync Schedule` notifications now trigger only from snapshots produced by the automatic scheduler (`sync_trigger=auto`) and ignore manual sync snapshots.
- Added DB compatibility migration for `notificationanchor.last_sync_snapshot_id`.

## [2026.03.24]

### Changed
- Reworked app layout to match a CoinStats-like structure: full-width top header card plus left sidebar navigation card.
- Moved global currency toggle (`USD/EUR`) to the top header and removed duplicate toggle from dashboard content.
- Added sidebar collapse/expand behavior with persisted state (`localStorage`) and moved the control into the sidebar.
- Unified card corner radius usage in the main layout and corrected inconsistent rounding behavior.
- Improved `Portfolio Price History` readability with compact Y-axis values (`K/M/B`), smaller axis labels, and softer grid lines.
- Added `Low`/`High` markers to the history chart and increased spacing between chart area and range/filter controls.
- Improved history chart tooltip positioning at right/top edges to prevent clipping.
- Updated history chart tooltip sizing behavior to keep a base width while expanding for long content.
- Updated currency formatting in `Portfolio Classification` and `Portfolio Price History` to use symbols (`€`, `$`) instead of trailing `EUR/USD` labels.

## [2026.02.26]

### Added
- Initial public project release.
