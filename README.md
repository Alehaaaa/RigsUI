# Rigs Library (RigsUI)

A professional Maya tool for organizing and managing 3D rig assets. The **Rigs Library** provides a dockable interface to easily browse, filter, and load rigs into your Maya scene.

## Features

- **Dockable Interface**: Seamlessly integrates into the Maya workspace.
- **Smart Filtering**: Filter rigs by **Collection**, **Tags**, or **Author**.
- **Search**: Quickly find rigs by name.
- **thumbnail Support**: Visual browsing with thumbnails.
- **JSON Database**: Lightweight and portable data storage (`rigs_database.json`).
- **Python 2 & 3 Compatible**: Works across multiple Maya versions.

## Installation

1. Copy the `RigsUI` folder to your Maya scripts directory:
   - **Windows**: `C:\Users\<NAME>\Documents\maya\scripts\`
   - **macOS**: `~/Library/Preferences/Autodesk/maya/scripts/`
   - **Linux**: `~/maya/scripts/`

2. Restart Maya.

## Usage

Run the following python code in the Maya Script Editor (Python tab):

```python
import RigsUI
RigsUI.show()
```

### Adding Rigs
1. Click the **+** (Plus) button in the top-left corner.
2. Select a Maya file (`.ma` or `.mb`).
3. Fill in the details (Name, Collection, Author, Tags).
4. The rig is added to the library.

### Editing Rigs
1. Right-click on a rig thumbnail (if context menu is supported) or use the Edit button in the UI if available.
2. Update the metadata as needed.

## Requirements

- Autodesk Maya (Supported versions: 2017+ recommended)
- Standard Maya Python environment (`maya.cmds`, `PySide2` or `PySide6`)

## License

MIT License. See [LICENSE](LICENSE) for details.
