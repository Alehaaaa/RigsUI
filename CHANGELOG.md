# Changelog

All notable changes to this project will be documented in this file.

## [0.1.4] - 2025-12-30
### 🚀 Added
- **Blacklist Feature**:
    - Added "Blacklist Rig" option to the rig card context menu.
    - Blacklisting a rig hides it from the library without deleting its metadata or files.
    - Added a confirmation dialog before blacklisting with a clear explanation of its effect.

## [0.1.3] - 2025-12-29
### 🚀 Added
- **Scanner Customization**:
    - **Blocked Paths**: Added a "Scanning Settings" section to the Settings tab to manage blocked folder patterns.
    - **Glob Support**: Use patterns like `.*` (prefix) or `*.anim` (suffix) to skip specific folders during scans. Exact matches are also supported.
- **Image Polish**:

### 📦 Changed
- **UX Improvements**:
    - **Scanning Status**: Re-aligned the status layout to place the animated loading dots directly next to the scanning path.

### 🐛 Fixed
- **Resource Management**: Background scanner workers are now reliably stopped when closing the "Manage Rigs" dialog.
- **Auto-Cropping**: Images are now automatically center-cropped to a square ratio when saved or updated.


## [0.1.2] - 2025-12-28
### 🚀 Added
- **UI Interaction**:
    - **Add Button**: The main "Add" (+) button can be triggered with **Right-Click**.

### 📦 Changed
- **Alternatives**: You can now see the rigs that are alternatives to the selected rig in the **Info Dialog** and **Edit Rig Dialog**.
- **Edit Rig Dialog**: Click the path field to edit the path of a rig.
- **Manage Rigs**: Added a `Remove` button to remove rigs from the database.

### 🐛 Fixed
- **Layout Consistency**: Fixed a bug where UI elements in the Info Dialog could be misplaced after a refresh.


## [0.1.1] - 2025-12-28
### 🚀 Added
- **Search & Filtering**:
    - **Summed Filters**: Search box supports `a:`, `c:`, and `t:` prefixes which are merged (ORed) with dropdown filters.
    - **Persistence**: Search box text is saved and is kept across sessions.
    - **Clear Button**: Added an "x" button to the search field for quick clearing.
- **Security & UX**:
    - **API Key Masking**: API Key field in settings now features a visibility toggle, to see the key as plain text.
    - **Auto-Hide Key**: Sensitive keys automatically revert to password mode when the input field loses focus.
    - **Custom Icons**: Added styled SVG icons for the API key visibility toggle.

### 📦 Changed
- **Rig Management**:
    - **Dialog Layout**: Re-ordered `RigSetupDialog` layout for better flow (Target Rig selection now appears above alternative toggle).
    - **Unique Naming**: Implemented automatic consecutive renaming (e.g., "Apollo 2", "Apollo 3") for duplicate rigs in both Manual and AI setup.
    - **Scanner Sync**: AI auto-tagging results now trigger an immediate UI refresh, correctly moving rigs between sections.

### 🐛 Fixed
- **Whitelisting UX**: Fixed an issue where rigs would disappear when whitelisting untagged files from the scanner's blacklist.
- **Path Normalization**: Implemented standardized POSIX-style path handling across all management dialogs to prevent cross-platform mismatches.


## [0.1.0] - 2025-12-28
### 🚀 Added
- **Scanning UX**:
    - **Filter Menu**: Refactored the style of the filter menu to be scrollable.
    - **Stop Scan**: Added a "Stop" button to folder searches to halt the process while keeping discovered results.
    - **Live Elision**: Folder paths in the scanner header now elide dynamically on window resize, utilizing 100% of available width.
    - **Animated Feedback**: "Scanning..." message with animated dots! Cool.
- **AI Integration**:
    - **Multiple Providers**: Added support for **Gemini**, **ChatGPT**, **Claude**, **Grok**, and **OpenRouter**.
    - **Custom Endpoints**: Support for local or custom AI endpoints (Ollama, LM Studio).
    - **Model Fetching**: Automatic retrieval of available models from the selected provider's API.

### 📦 Changed
- **Data Integrity**: Centralized logic to use "replaced paths" as the source of truth for duplicate checking and internal UI mapping.

### 🐛 Fixed
- **Highlight Precision**: Fixed a CSS bleed issue where highlighting a duplicate rig would accidentally color the background of its inner buttons and labels.


## [0.0.11] - 2025-12-27
### 📦 Changed
- **Visual Polish**: 
    - Updated `PillWidget` for tags to use a more compact and allow for easier interaction.
    - Standardized naming and title constants across the application.
- **Code Cleanup**: Removed redundant debug prints and internal implementation comments.

### 🐛 Fixed
- **Manage Rigs Database Population**: Fixed a bug where blacklisted items could incorrectly display data from a previous rig entry during scanning.
- **Tag Editor UX**: Improved the responsiveness of tag removal. Clicking the "✕" button on a tag pill now reliably removes the tag.


## [0.0.10] - 2025-12-27
### 🚀 Added
- **Status Filters**: New filters filter rigs by status:
    - **Only Available**: Shows only rigs where the file exists on disk.
    - **Only Referenced**: Shows only rigs currently referenced in the active Maya scene.
- **Tag Editor**: Redesigned input for tags using interactive "pills":
    - Visual representation of tags with remove (x) buttons.
    - Smart auto-complete dropdown from existing tags.

### 📦 Changed
- **Path Replacements**: Rewrote the logic to apply path replacements *only* in memory, not saved to the database.


## [0.0.9] - 2025-12-27
### 📦 Changed
- **Manage Rigs UI**: Improved resizing behavior for expandable sections and path replacement lists.
- **Duplicate Handling**: Manually adding an existing rig now shows a warning message while still highlighting the original entry.
- **Stability**: Fixed a crash when adding path replacements.


## [0.0.8] - 2025-12-27
### 🚀 Added
- **Batch Add Rigs**: New tool to scan entire directories for Maya files. Categorizes rigs as *New*, *In Database*, or *Blacklisted*.
- **Standalone Blacklist**: New blacklist management with a dedicated `blacklist.json` file.
- **Filter Button Counter**: The Filters button now displays the number of active filters (e.g., `Filters (2)`).

### 📦 Changed
- **Batch Add UX**: 
    - Improved path display with two-tone eliding (grey directory, highlighted filename).
    - Disabled the "Edit" button for rigs recognized as *Alternatives* to prevent accidental primary-entry overwrites.
- **Data Integrity**: `load_data` now automatically cleans up the database by removing duplicate paths in alternatives.

### 🐛 Fixed
- **Scroll Position Persistence**: The library grid now maintains your scroll position when reloading data or refreshing the UI.


## [0.0.7] - 2025-12-27
### 🚀 Added
- **Author "Empty" Support**: Rigs without an author are now grouped under the *Empty* Author tag.
- **Database Cleanup**: Significant cleanup and standardization of tags and metadata for several rig packs (Maurice Racoon, ProRigs, individual characters, ...).

### 📦 Changed
- **UI UX Protective Toggle**: Menus opened via buttons (Filters, Sort) now ignore accidental triggers.
- **Edit UI Refinement**: In the Rig Setup dialog, metadata fields containing "Empty" values now display as blank.

### 🤖 Testing
- **Rig Scanner powered by AI**: Testing an integrated scanner temporarily using **AI APIs** to automatically index rig folders, write metadata and more.


## [0.0.6] - 2025-12-26
### 🚀 Added
- **Context Menu Actions**: Expanded the right-click menu on rig cards with new actions:
    - **Open Rig Scene**: Opens the rig's source file in a new Maya scene (includes safety warning).
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
- **Sorting**: Sort library by Name, Collection, or Author.
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
