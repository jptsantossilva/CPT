# Changelog

All notable changes to this project will be documented in this file.

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
