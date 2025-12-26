# Changelog

All notable changes to this project will be documented in this file.

## [0.0.4] - 2025-12-26
### Added
- **Threaded Search**: Implemented background thread for search/filtering to prevent UI freezing.
- **Sorting**: Added a Sort Menu to sort by Name, Collection, or Author (Ascending/Descending).
- **Advanced Search**: Support for field-based search queries (e.g., `tag:human`, `author:Mike`).
- **WebP Support**: Added support for `.webp` image files for rig thumbnails.
- **Settings Persistence**: Sort preferences are now saved and restored along with filters.

### Changed
- **Performance**: Refactored grid population to reuse existing widgets ("reconciliation strategy"), significantly reducing flicker and load times.
- **UI UX**: "Empty" collections and authors are now explicitly handled and displayed in italics; sorting treats them as empty strings (first in Asc, last in Desc).
- **Codebase**: extensive refactoring for cleanliness, removal of duplicate code, and standardized variable naming (`search_input`, `action_btn`).

### Fixed
- **Visual Artifacts**: Fixed "ghosting" bug where widgets would overlap after reloading or filtering.
- **Floating Windows**: Fixed issue where widgets would float momentarily before docking into the layout.


## [0.0.3] - 2025-12-26
### Added
- Added `VERSION` file for single source of truth.
- Added `README.md` with installation and usage instructions.
- Added `LICENSE` (MIT).
- Updated `.gitignore` to include standard Maya and Python files.
