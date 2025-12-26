# Changelog

All notable changes to this project will be documented in this file.

## [0.0.6] - 2025-12-26
### 🚀 Added
- **Context Menu Actions**: Expanded the right-click menu on rig cards with new actions:
    - **Open Source File**: Opens the rig's source file in a new Maya scene (includes safety warning).
    - **Show in Folder**: Opens the system file explorer with the rig file selected/highlighted.
    - **Remove Rig**: Allows removing a rig from the library database (does not delete the physical file).
- **File Explorer Integration**: Enhanced "Show in Folder" and path links in the Info Dialog to select the specific file in Windows Explorer/Finder instead of just opening the parent directory.

### 📦 Changed
- **Menu Organization**: improved context menu layout with clear separators and logical grouping (Edit / File Actions / Destructive).
- **Tooltips**: Improved path display in tooltips to show a shortened readable format for paths.
- **Icons**: Added trash icon for the Remove action.

## [0.0.5] - 2025-12-26
### 🚀 Added
- **Context Menu**: Added right-click context menu to the Info button for quick access to "Edit Details".

### 🐛 Fixed
- **Tags Autocomplete**: Resolved issues where selecting a tag would overwrite the entire field. It now correctly appends the tag with a comma separator and preserves cursor position.
- **UI Layout**: Fixed a bug where buttons were being added to the layout twice, causing visual artifacts.

## [0.0.4] - 2025-12-26
### 🚀 Added
- **Threaded Search**: Implemented background thread for search/filtering to prevent UI freezing.
- **Sorting**: Added a Sort Menu to sort by Name, Collection, or Author (Ascending/Descending).
- **Advanced Search**: Support for field-based search queries (e.g., `tag:human`, `author:Mike`).
- **WebP Support**: Added support for `.webp` image files for rig thumbnails.
- **Settings Persistence**: Sort preferences are now saved and restored along with filters.

### 📦 Changed
- **Performance**: Refactored grid population to reuse existing widgets ("reconciliation strategy"), significantly reducing flicker and load times.
- **UI UX**: "Empty" collections and authors are now explicitly handled and displayed in italics; sorting treats them as empty strings (first in Asc, last in Desc).
- **Codebase**: extensive refactoring for cleanliness, removal of duplicate code, and standardized variable naming (`search_input`, `action_btn`).

### 🐛 Fixed
- **Visual Artifacts**: Fixed "ghosting" bug where widgets would overlap after refreshing or filtering.
- **Floating Windows**: Fixed issue where widgets would float momentarily before docking into the layout.


## [0.0.3] - 2025-12-26
### 🚀 Added
- Added `VERSION` file for single source of truth.
- Added `README.md` with installation and usage instructions.
- Added `LICENSE` (MIT).
- Updated `.gitignore` to include standard Maya and Python files.
