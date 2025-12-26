import os
import sys
import argparse
import datetime

# Configuration
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
VERSION_FILE = os.path.join(PROJECT_ROOT, "VERSION")
CHANGELOG_FILE = os.path.join(PROJECT_ROOT, "CHANGELOG.md")


def read_version():
    if not os.path.exists(VERSION_FILE):
        return "0.0.0"
    with open(VERSION_FILE, "r") as f:
        return f.read().strip()


def write_version(v):
    with open(VERSION_FILE, "w") as f:
        f.write(v)


def update_changelog(new_version):
    """Adds a new entry to CHANGELOG.md"""
    if not os.path.exists(CHANGELOG_FILE):
        return

    today = datetime.date.today().isoformat()
    header = "## [{}] - {}".format(new_version, today)

    with open(CHANGELOG_FILE, "r") as f:
        content = f.read()

    # Look for the first existing version header or "Changelog" title
    lines = content.splitlines()
    insert_idx = -1
    for i, line in enumerate(lines):
        if line.startswith("## ["):
            insert_idx = i
            break

    # If no versions found, append after description?
    # Or just insert after the main title usually line 2 or 3.
    if insert_idx == -1:
        # Default fallback: insert after the first non-empty line
        insert_idx = 4

    new_section = [
        "",
        header,
        "### Changed",
        "- Bumped version to {}".format(new_version),
    ]

    lines[insert_idx:insert_idx] = new_section

    with open(CHANGELOG_FILE, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("Updated CHANGELOG.md")


def main():
    parser = argparse.ArgumentParser(description="Bump version number")
    parser.add_argument("part", choices=["major", "minor", "patch"], help="Part of version to bump")
    args = parser.parse_args()

    current_v = read_version()
    # Simple semantic version parser (X.Y.Z)
    try:
        parts = list(map(int, current_v.split(".")))
    except ValueError:
        print("Error: VERSION file contains non-numeric version '{}'".format(current_v))
        sys.exit(1)

    if args.part == "major":
        parts[0] += 1
        parts[1] = 0
        parts[2] = 0
    elif args.part == "minor":
        parts[1] += 1
        parts[2] = 0
    elif args.part == "patch":
        parts[2] += 1

    new_v = ".".join(map(str, parts))

    write_version(new_v)
    print("Version bumped: {} -> {}".format(current_v, new_v))

    update_changelog(new_v)


if __name__ == "__main__":
    main()
