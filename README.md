# Rigs Library (RigsUI)

A professional Maya tool for organizing and managing 3D rig assets. Provides a dockable interface to easily browse, filter, and load rigs into your Maya scene.

![Main UI](_public/main_ui_showcase.png)

## Features

- **Favorites System**: Mark your most-used rigs with high-fidelity, interactive heart icons featuring dynamic contrast detection for visibility on any background.
- **Rig Versions**: Switch between different file versions (e.g., Proxy, Performance, Render) directly from the rig card.
- **Bulk Editing**: Select multiple rigs to update tags, collections, or authors in a single operation.
- **Instance Management**: Handle multiple rig instances in your scene with dynamic buttons (ADD/REMOVE/MANAGE).
- **Advanced Search**: Filter by metadata or use keywords that now include a dedicated **Notes** field.
- **AI Auto-Tagging**: Automatically add metadata using Gemini, ChatGPT, Claude, Grok, or OpenRouter.
- **Path Replacements**: Map shared databases across machines with localized path swaps.

### Edit Rig Details

View and modify rig metadata including name, collection, author, tags, and thumbnail.

![Edit Rig Dialog](_public/edit_rig_dialog_showcase.png)

> Featuring the rig [Golem Critter](https://tristenanimates.gumroad.com/l/nywts) by Tristen

### Smart Filtering

Quickly find rigs using filters for collection, tags, author, or status.

![Filters](_public/filters_showcase.png)

> Featuring the [Body Mechanics Rigs](https://joedanimation.gumroad.com/l/xhRK) by Joe Daniels

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

### Rig Referencing

RigsUI provides a dynamic system to manage references in your Maya scene:

- **ADD**: Click to add the first reference of a rig.
- **REMOVE**: Click to remove the rig reference (appears when exactly 1 instance exists).
- **[+] Button**: A small shortcut button that appears next to the main action button once a rig is referenced, allowing you to quickly add additional instances.
- **MANAGE**: Click to open a menu of all current instances. You can remove specific instances by their namespace from here.

### Managing Library
1. **Info & Edit**: Click the ⓘ button to view rig details. 
2. **Context Menu**: Right-click the ⓘ button to access advanced actions:
   - **Edit Details**: Modification of metadata.
   - **Open Rig Scene**: Opens the original file in a new Maya scene.
   - **Show in Folder**: Reveals the file in Explorer/Finder.
   - **Remove Rig**: Removes the entry from the library database.

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
