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
1. Click the **+** (Plus) button in the top-left corner.
2. Select a Maya file (`.ma` or `.mb`).
3. Fill in the details (Name, Collection, Author, Tags).
4. The rig is added to the library.

### Editing Rigs
1. Open the information dialog by clicking the (i) button under the rig thumbnail.
2. Click the Edit button to edit the rig's metadata.
3. Click the Save button to save the changes.

## Requirements

- Autodesk Maya (Supported versions: 2019+ recommended)
- Standard Maya Python environment (`maya.cmds`, `PySide2` or `PySide6`)

## Issues

If you find any issues, please report them on the [GitHub issue tracker](https://github.com/aleha/RigsUI/issues).

## Contributing

Contributions are welcome! Please submit a pull request.

## Transparency

The source code was written by me, **Aleha**, with significant assistance from AI tools. Specifically, **Gemini** within **Antigravity** (an AI-powered IDE) and **ChatGPT**.

Check out Antigravity here: [https://antigravity.google/](https://antigravity.google/)
And ChatGPT here: [https://chat.openai.com/](https://chat.openai.com/)

## License

MIT License. See [LICENSE](LICENSE) for details.
