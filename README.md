# Rigs Library (RigsUI)

A professional Maya tool for organizing and managing 3D rig assets. The **Rigs Library** provides a dockable interface to easily browse, filter, and load rigs into your Maya scene.

## Features

- **Dockable Interface**: Seamlessly integrates into the Maya workspace.
- **Smart Filtering**: Filter rigs by **Collection**, **Tags**, or **Author**.
- **Advanced Search**: Search by name or use specific filters (e.g., `tag:human`, `author:ProRigs`).
- **Sorting**: Sort library by Name, Collection, or Author.
- **Context Actions**: Right-click to Edit Details, Open Rig Scene, Show in Folder, or Remove Rig.
- **Thumbnail Support**: Visual browsing with thumbnails (supports .jpg, .png, .webp).
- **Batch Import**: Scan entire folders and categorize rigs for rapid library expansion.
- **Path Replacements**: Define local path swaps (e.g., `D:/Rigs` -> `Z:/Server/Rigs`) to share databases across different machines/OS without breaking paths.
- **AI Auto-Tagging**: Optional Google Gemini integration to automatically analyze file names and suggest metadata for batch imports.
- **JSON Database**: Lightweight and portable data storage (`rigs_database.json` and `blacklist.json`).

## Installation

Copy the `RigsUI` folder to your Maya scripts directory:
   - **Windows**: `C:\Users\<NAME>\Documents\maya\scripts\`
   - **macOS**: `~/Library/Preferences/Autodesk/maya/scripts/`
   - **Linux**: `~/maya/scripts/`

## Usage

Run the following python code in the Maya Script Editor (Python tab):

```python
import RigsUI
RigsUI.show()
```

### Adding Rigs

**Singular Add**:
1. Click the **+** (Plus) button and select **Add Single Rig...**.
2. Select a Maya file (`.ma` or `.mb`).
3. Fill in the details (Name, Collection, Author, Tags).
4. The rig is added to the library.

**Batch Add**:
1. Click the **+** (Plus) button and select **Batch Add Rigs from Folder...**.
2. Select a directory to scan.
3. Review discovered rigs, categorize them, or add them instantly using the scanner UI.

### Managing Rigs
1. **Info & Edit**: Click the (i) button to view rig details. 
2. **Context Menu**: Right-click the (i) button to access advanced actions:
   - **Edit Details**: Modification of metadata.
   - **Open Rig Scene**: Opens the original file in a new Maya scene.
   - **Show in Folder**: Reveals the file in Explorer/Finder.
   - **Remove Rig**: Removes the entry from the library.

## Requirements

- Autodesk Maya 2022+ or higher.
- Python 3. Working on Python 2 compatibility.
- Standard Maya Python environment (`maya.cmds`, `PySide2` or `PySide6`)

## Changelog

### v0.0.11
- **Visual Polish & Stability**: Major fix for "popping" floating layouts and flicker during UI initialization.
- **Tag Editor Fixes**: Robust tag removal and improved pill aesthetics.
- **Improved UX**: Corrected menu parenting and standardized application titles.

### v0.0.10
- **Status Filters**: New "Only Available" and "Only Referenced" filters to quickly check file status.
- **Tag Editor 2.0**: New visual tag editor with "pills", auto-complete, and improved interaction.
- **Safe Path Replacements**: Non-destructive path swapping at runtime ensures your database remains portable.
- **Manage Rigs UI**: Improved stretch behavior and resizing logic.

## Issues

If you find any issues, please report them on the [GitHub issue tracker](https://github.com/Alehaaaa/RigsUI/issues).

## Contributing

Contributions are welcome! Please submit a pull request.

## Transparency

The source code was written by me, **Alehaaaa**, with significant assistance from AI tools.
Specifically, **Gemini** within **Antigravity** (an AI-powered IDE) and **ChatGPT**.

- Check out Antigravity here: [https://antigravity.google/](https://antigravity.google/)
- And ChatGPT here: [https://chat.openai.com/](https://chat.openai.com/)

## License

MIT License. See [LICENSE](LICENSE) for details.
