# Changelog

All notable changes to WSB-Crawler will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-02-02

### Added
- Initial release with refactored codebase
- Version management system with automatic releases
- Docker support with docker-compose
- Comprehensive documentation (DOCKER.md, REFACTORING_SUMMARY.md)
- Type hints and docstrings for all major functions
- GitHub Actions workflow for automated releases and Docker builds
- Automatic version incrementing on code changes

### Changed
- Consolidated duplicate code across multiple files
- Improved code organization and structure
- Enhanced error handling and logging
- Updated README with Docker quick-start

### Removed
- Duplicate `download_and_clean_tickerlist()` functions
- Unused `stop_crawler()` stub function
- Redundant OpenAI cost tracking functions (consolidated to one)
- Dead code paths and commented-out code
- Streamlit code from headless crawler

### Fixed
- Double variable declarations in run_crawler_headless.py
- Inconsistent imports and dependencies
- Code quality issues identified during refactoring

## [Unreleased]

### Planned
- Unit tests for critical functions
- Centralized logging configuration
- Pre-commit hooks for code quality

---

[1.0.0]: https://github.com/fgrfn/reddit-wsb-crawler/releases/tag/v1.0.0
