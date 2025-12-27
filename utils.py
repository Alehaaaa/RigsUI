import os
import re
import logging

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
    LOG.warning("Icon not found: {}".format(path))
    return QtGui.QIcon()
