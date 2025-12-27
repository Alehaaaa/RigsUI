import os
import re
import json
import logging
import urllib.request
import urllib.error

try:
    from PySide6 import QtGui
except ImportError:
    from PySide2 import QtGui

# -------------------- Logging --------------------
LOG = logging.getLogger("LibraryUI")


# -------------------- Constants --------------------
try:
    MODULE_DIR = os.path.dirname(__file__)
except NameError:
    MODULE_DIR = "/"

IMAGES_DIR = os.path.join(MODULE_DIR, "images")
ICONS_DIR = os.path.join(MODULE_DIR, "_icons")


# -------------------- Utils --------------------
def format_name(name):
    return name.lower().replace(" ", "_")


def save_image_local(source_path, base_name):
    """
    Saves and converts an image to JPG in the local images directory.
    Returns the new filename.
    """
    if not source_path or not os.path.exists(source_path):
        return None

    try:
        # Sanitize name
        clean_name = re.sub(r"[^a-z0-9_]", "", format_name(base_name))
        image_filename = "{}.jpg".format(clean_name)
        dest_path = os.path.join(IMAGES_DIR, image_filename)

        img = QtGui.QImage(source_path)
        if not img.isNull():
            if not os.path.exists(IMAGES_DIR):
                os.makedirs(IMAGES_DIR)
            img.save(dest_path, "JPG")
            return image_filename
    except Exception as e:
        LOG.error("Failed to save image: {}".format(e))
    return None


def get_icon(file_name):
    """
    Returns a QIcon from the _icons directory.
    """
    if file_name:
        path = os.path.join(ICONS_DIR, file_name)
        if os.path.exists(path):
            return QtGui.QIcon(path)
    LOG.warning("Icon not found: {}".format(file_name))
    return QtGui.QIcon()


def query_gemini(api_key, file_paths):
    """
    Queries Google's Gemini API to categorize and tag rig files from a list of paths.
    """
    if not api_key or not file_paths:
        return None

    model_name = "gemini-2.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"

    system_instruction = """
You are a data organization assistant. I have a list of file paths for 3D Maya rigs.
Your task is to analyze these paths and organize them into a clean JSON dictionary.

Rules:
1.  **Grouping**: Group files that refer to the same character/rig. 
    - Identify the "Main" rig file (usually the cleanest name, e.g., 'Artemis.ma').
    - Any variations (e.g., 'Artemis_game.ma', 'ArtemisMod.ma', 'Artemis_v2.mb') should be listed in an "alternatives" list within the main entry.
    - If you cannot decide which is the main one, pick the shortest or most 'canonical' looking name.
2.  **Keys**: The top-level keys of the JSON should be the Character Name (e.g., "Apollo", "Artemis").
3.  **Metadata Extraction**:
    - "path": The absolute path to the main rig file.
    - "image": Leave as null.
    - "tags": Infer tags based on the name or path context (e.g., 'human', 'male', 'female', 'creature').
    - "collection": General themes, like animals or props are just tags, these shall NOT be collections. This collection name should be short and descriptive, title-cased, and Optional. If no collection can be confidently determined, set it to null. The purpose of this field is to group related rigs into a single collection.
    - "author": Find the author if the path suggests it, or put null if unknown.
    - "link": Find a gumroad or equivalent link if possible, or null.
    - "exists": Set to true.
    - "alternatives": A list of strings containing the full filepaths of all variations found for this rig.
4.  **Output Format**: Return ONLY valid JSON.
    
Expected JSON Structure:
{
    "Apollo": {
        "path": "D:\\...\\Apollo.ma",
        "image": null,
        "tags": ["human", "male"],
        "collection": "Apollo&Artemis",
        "author": "Ramon Arango",
        "link": "https://ramonarango.gumroad.com/l/ArtemisApolloRig",
        "exists": true,
        "alternatives": []
    }
}
"""

    paths_text = "\n".join(file_paths)
    prompt_text = (
        f"Here is the list of NEW file paths to categorize (Limit 50):\n\n{paths_text}\n\nGenerate JSON."
    )
    data = {"contents": [{"parts": [{"text": system_instruction + "\n\n" + prompt_text}]}]}

    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}

    try:
        req = urllib.request.Request(
            url, data=json.dumps(data).encode("utf-8"), headers=headers, method="POST"
        )
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                result = json.loads(response.read().decode("utf-8"))
                candidates = result.get("candidates", [])
                if candidates:
                    raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    # Extract JSON block
                    start = raw_text.find("{")
                    end = raw_text.rfind("}") + 1
                    if start != -1 and end != -1:
                        json_str = raw_text[start:end]
                        return json_str
            else:
                LOG.error(f"Gemini API Error: {response.status}")
                return None
    except urllib.error.URLError as e:
        LOG.error(f"Gemini API Error: {e}")
    except Exception as e:
        LOG.error(f"Gemini Request failed: {e}")
    return None


def check_for_updates(current_version):
    """
    Checks for updates by comparing local version with remote VERSION file.
    Returns: (is_update_available, remote_version)
    """
    remote_url = "https://raw.githubusercontent.com/Alehaaaa/RigsUI/main/VERSION"

    try:
        with urllib.request.urlopen(remote_url, timeout=5) as response:
            if response.status == 200:
                remote_ver = response.read().decode("utf-8").strip()
                if remote_ver != current_version:
                    return True, remote_ver
                return False, remote_ver
    except urllib.error.HTTPError as e:
        if e.code != 404:
            LOG.warning(f"Update check failed for {remote_url}: {e}")
    except Exception as e:
        LOG.warning(f"Failed to check for updates: {e}")

    return False, None
