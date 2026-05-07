"""UI helper functions — data loaders for projects, files, services."""

from pathlib import Path


def get_services() -> list[dict]:
    """Get list of listening ports/services."""
    from cios.skills.process_control import list_listening_ports
    return list_listening_ports()


def get_projects() -> list[dict]:
    """Scan common directories for projects."""
    import json as _json

    projects = []
    home = Path.home()
    scan_dirs = [home, home / "projects", home / "dev", home / "code",
                 home / "workspace", home / "repos", Path.cwd()]
    seen = set()
    for d in scan_dirs:
        if not d.is_dir():
            continue
        for child in d.iterdir():
            if not child.is_dir() or child.name.startswith(".") or child in seen:
                continue
            seen.add(child)
            if (child / "package.json").exists():
                try:
                    pkg = _json.loads((child / "package.json").read_text())
                    name = pkg.get("name", child.name)
                except Exception:
                    name = child.name
                projects.append({"name": name, "path": str(child), "type": "node"})
            elif (child / "requirements.txt").exists() or (child / "pyproject.toml").exists():
                projects.append({"name": child.name, "path": str(child), "type": "python"})
    return projects[:20]


def get_directories() -> list[dict]:
    """Get key user directories with item counts."""
    home = Path.home()
    dirs = [
        ("📥", "Downloads", home / "Downloads"),
        ("🖥️", "Desktop", home / "Desktop"),
        ("📄", "Documentos", home / "Documents"),
        ("🖼️", "Imagens", home / "Pictures"),
        ("🎵", "Música", home / "Music"),
        ("🎬", "Vídeos", home / "Videos"),
    ]
    result = []
    for icon, name, path in dirs:
        if path.is_dir():
            try:
                count = sum(1 for f in path.iterdir() if not f.name.startswith("."))
            except PermissionError:
                count = 0
            result.append({"icon": icon, "name": name, "path": str(path), "count": count})
    return result
