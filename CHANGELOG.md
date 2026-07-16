# Changelog

All notable changes to this module will be documented in this file.

## [19.0.1.1.3] - 2025-12-16

### Changed
- Moved `_name` and `_description` to top of AbstractModel class (code structure)
- Changed debug logging from `_logger.error` to `_logger.debug`

### Removed
- Removed unused XLSX report files (`multi_currency_general_ledger_report_xlsx.py`, `multi_currency_general_ledger_report_xlsx_fixed.py`)

### Added
- Added `README.rst` documentation
- Added `CHANGELOG.md`

## [19.0.1.1.2] - 2025-05-04

### Changed
- Direct Excel export and currency handling improvements
- Removed report_xlsx dependency
- Ensured Excel matches PDF structure and values are in selected currency

## [19.0.1.1.0] - 2025-01-01

### Added
- Initial release for Odoo 18
- Multi-currency general ledger report
- PDF and Excel export functionality
- Account type filtering
- Initial balance support
2026-07-07 | v19.0.x.x.x | Forward-port sync from 18.0. | AI
