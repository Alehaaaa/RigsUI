# Rigs Library (RigsUI)

A professional Maya tool for organizing and managing 3D rig assets. The **Rigs Library** provides a dockable interface to easily browse, filter, and load rigs into your Maya scene.

## Features

- **Dockable Interface**: Seamlessly integrates into the Maya workspace.
- **Smart Filtering**: Filter rigs by **Collection**, **Tags**, or **Author**.
- **Advanced Search**: Search by name or use specific filters (e.g., `tag:human`, `author:ProRigs`). Search text persists across sessions and includes a native clear button.
- **Sorting**: Sort library by Name, Collection, or Author.
- **Context Actions**: Right-click to Edit Details, Open Rig Scene, Show in Folder, or Remove Rig.
- **Thumbnail Support**: Visual browsing with thumbnails (supports .jpg, .png, .webp).
- **Batch Import**: Scan entire folders and categorize rigs for rapid library expansion.
- **Path Replacements**: Define local path swaps (e.g., `D:/Rigs` -> `Z:/Server/Rigs`) to share databases across different machines/OS without breaking paths.
- **AI Auto-Tagging**: AI integration to automatically add metadata for new rigs. Supports **Gemini**, **ChatGPT**, **Claude**, **Grok**, **OpenRouter** or **Custom AI Endpoints** (e.g., LM Studio, Ollama).
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

**Add One Rig**:
1. Click the **+** (Add) button and select **Add Manually**.
2. Select a Maya file (`.ma` or `.mb`).
3. Fill in the details (Name, Collection, Author, Tags).
4. The rig is added to the library.

**Add Multiple Rigs**:
1. Click the **+** (Add) button and select **Scan Folder**.
2. Select a directory to scan.
3. Review discovered rigs, categorize them, or add them instantly using the scanner UI.

### Managing Rigs
1. **Info & Edit**: Click the ⓘ button to view rig details. 
2. **Context Menu**: Right-click the ⓘ button to access advanced actions:
   - **Edit Details**: Modification of metadata.
   - **Open Rig Scene**: Opens the original file in a new Maya scene.
   - **Show in Folder**: Reveals the file in Explorer/Finder.
   - **Remove Rig**: Removes the entry from the library.

## Requirements

- Autodesk Maya 2022+ or higher.
- Python 3. Working on Python 2 compatibility.
- Standard Maya Python environment (`maya.cmds`, `PySide2` or `PySide6`)

## Changelog

Check it out on [CHANGELOG.md](CHANGELOG.md).

## Issues

If you find any issues, please report them on the [GitHub issue tracker](https://github.com/Alehaaaa/RigsUI/issues).

## Contributing

Contributions are welcome! Please submit a pull request.

## Transparency

The source code was written by me, **Alehaaaa**, with significant assistance from AI tools.
Specifically, **AI Agents** (like Gemini within Antigravity or ChatGPT) and manual contributors.

- Check out Antigravity here: [https://antigravity.google/](https://antigravity.google/)
- And ChatGPT here: [https://chat.openai.com/](https://chat.openai.com/)

## License

MIT License. See [LICENSE](LICENSE) for details.
