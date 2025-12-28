import os
import re
import json
import logging
import urllib.request
import urllib.error
import ssl

try:
    from PySide6 import QtGui
except ImportError:
    from PySide2 import QtGui

from . import TOOL_TITLE

# -------------------- Logging --------------------
LOG = logging.getLogger(TOOL_TITLE)


# -------------------- Constants --------------------
MODULE_DIR = os.path.dirname(os.path.abspath(__file__))

IMAGES_DIR = os.path.join(MODULE_DIR, "images")
ICONS_DIR = os.path.join(MODULE_DIR, "_icons")


# -------------------- Utils --------------------
def format_name(name):
    return name.lower().replace(" ", "_")


def setting_bool(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value.lower() == "true"
    return bool(value)


def apply_path_replacements(path, replacements):
    """
    Applies a list of (find, replace) tuples to a path.
    Normalizes slashes and path consistency.
    """
    if not path or not replacements:
        return path

    # Normalize slashes for consistent replacement
    path = os.path.normpath(path).replace("\\", "/")

    for find_str, rep_str in replacements:
        if not find_str:
            continue

        # Normalize the find string as well to ensure it matches the path format
        f_norm = os.path.normpath(find_str).replace("\\", "/")
        r_norm = os.path.normpath(rep_str).replace("\\", "/")

        if f_norm in path:
            path = path.replace(f_norm, r_norm)

    return os.path.normpath(path)


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


def query_ai(endpoint, model, api_key, file_paths, custom_url=None):
    """
    Queries an AI API to categorize and tag rig files from a list of paths.
    """
    if not api_key or not file_paths:
        return None

    # Define payload formatters and response parsers for each endpoint style
    def open_ai_payload(sys, p, mod):
        return {
            "model": mod,
            "messages": [{"role": "system", "content": sys}, {"role": "user", "content": p}],
            "response_format": {"type": "json_object"},
        }

    def open_ai_parse(res):
        choices = res.get("choices", [])
        return choices[0].get("message", {}).get("content", "") if choices else ""

    def gemini_payload(sys, p, mod):
        return {"contents": [{"parts": [{"text": sys + "\n\n" + p}]}]}

    def gemini_parse(res):
        candidates = res.get("candidates", [])
        return candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "") if candidates else ""

    def claude_payload(sys, p, mod):
        return {
            "model": mod,
            "max_tokens": 4096,
            "system": sys,
            "messages": [{"role": "user", "content": p}],
        }

    def claude_parse(res):
        content = res.get("content", [])
        if content and isinstance(content, list):
            return content[0].get("text", "")
        return ""

    # Endpoint configuration mapping
    config = {
        "Gemini": {
            "url": "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent".format(model),
            "headers": {"Content-Type": "application/json", "x-goog-api-key": api_key},
            "payload": gemini_payload,
            "parse": gemini_parse,
        },
        "ChatGPT": {
            "url": "https://api.openai.com/v1/chat/completions",
            "headers": {"Content-Type": "application/json", "Authorization": "Bearer {}".format(api_key)},
            "payload": open_ai_payload,
            "parse": open_ai_parse,
        },
        "Grok": {
            "url": "https://api.x.ai/v1/chat/completions",
            "headers": {"Content-Type": "application/json", "Authorization": "Bearer {}".format(api_key)},
            "payload": open_ai_payload,
            "parse": open_ai_parse,
        },
        "Claude": {
            "url": "https://api.anthropic.com/v1/messages",
            "headers": {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            "payload": claude_payload,
            "parse": claude_parse,
        },
        "OpenRouter": {
            "url": "https://openrouter.ai/api/v1/chat/completions",
            "headers": {
                "Content-Type": "application/json",
                "Authorization": "Bearer {}".format(api_key),
                "HTTP-Referer": "https://github.com/Alehaaaa/RigsUI",
                "X-Title": "RigsUI",
            },
            "payload": open_ai_payload,
            "parse": open_ai_parse,
        },
        "Custom": {
            "url": custom_url,
            "headers": {"Content-Type": "application/json", "Authorization": "Bearer {}".format(api_key)},
            "payload": open_ai_payload,
            "parse": open_ai_parse,
        },
    }

    cfg = config.get(endpoint)
    if not cfg or not cfg["url"]:
        LOG.error("Invalid AI configuration for: {}".format(endpoint))
        return None

    url, headers = cfg["url"], cfg["headers"]
    payload_fn, parse_fn = cfg["payload"], cfg["parse"]

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
        "Here is the list of NEW file paths to categorize (Limit 50):\n\n{}\n\nGenerate JSON.".format(
            paths_text
        )
    )

    payload = payload_fn(system_instruction, prompt_text, model)

    try:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
        )
        context = ssl._create_unverified_context()
        with urllib.request.urlopen(req, context=context) as response:
            if response.status == 200:
                result = json.loads(response.read().decode("utf-8"))
                raw_text = parse_fn(result)

                if raw_text:
                    start = raw_text.find("{")
                    end = raw_text.rfind("}") + 1
                    if start != -1 and end != -1:
                        return raw_text[start:end], None
            else:
                LOG.error("AI API Error ({}): {}".format(endpoint, response.status))
                return None, "AI API Error ({}): {}".format(endpoint, response.status)
    except Exception as e:
        LOG.error("AI Request failed ({}): {}".format(endpoint or url, e))
        return None, "AI Request failed ({}): {}".format(endpoint or url, e)


def get_ai_models(url, headers=None):
    """
    Fetches available models from the provided URL.
    """
    if not url:
        return []

    try:
        req = urllib.request.Request(url, headers=headers or {}, method="GET")
        context = ssl._create_unverified_context()
        with urllib.request.urlopen(req, context=context) as response:
            if response.status == 200:
                result = json.loads(response.read().decode("utf-8"))
                # Handle varied API response keys (Gemini: 'models', OpenAI: 'data')
                items = result.get("models") or result.get("data") or []
                models = []
                for item in items:
                    name = item.get("name") or item.get("id")
                    if name:
                        models.append(name.split("/")[-1])
                return sorted(list(set(models)))
    except Exception as e:
        LOG.error("Failed to fetch models from {}: {}".format(url, e))

    return []


def check_for_updates(current_version):
    """
    Checks for updates by comparing local version with remote VERSION file.
    Returns: (is_update_available, remote_version)
    """
    remote_url = "https://raw.githubusercontent.com/Alehaaaa/RigsUI/main/VERSION"

    try:
        context = ssl._create_unverified_context()
        with urllib.request.urlopen(remote_url, timeout=5, context=context) as response:
            if response.status == 200:
                content = response.read()
                try:
                    remote_ver = content.decode("utf-8").strip()
                except UnicodeDecodeError:
                    remote_ver = content.decode("utf-16").strip()

                if remote_ver != current_version:
                    return True, remote_ver
                return False, remote_ver
    except urllib.error.HTTPError as e:
        if e.code != 404:
            LOG.warning("Update check failed for {}: {}".format(remote_url, e))
    except Exception as e:
        LOG.warning("Failed to check for updates: {}".format(e))

    return False, None
