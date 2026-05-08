"""Handler for gallery management intents (favorites, delete, albums)."""

import os

from cios.core.executor import Executor
from cios.core.handlers._common import PlanResult
from cios.core.intent_parser import Intent
from cios.core.memory import Memory


def handle_gallery_manage(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Handle gallery management actions: favorite, delete, albums."""
    from cios.skills.gallery_store import get_store

    action = intent.params.get("action", "")
    store = get_store()

    if action == "toggle_favorite":
        return _handle_toggle_favorite(intent, store)
    elif action == "list_favorites":
        return _handle_list_favorites(store)
    elif action == "search_date":
        return _handle_search_date(intent)
    elif action == "search_text":
        return _handle_search_text(intent)
    elif action == "scan_faces":
        return _handle_scan_faces()
    elif action == "list_people":
        return _handle_list_people()
    elif action == "search_person":
        return _handle_search_person(intent)
    elif action == "name_person":
        return _handle_name_person(intent)
    elif action == "identify_face":
        return PlanResult(
            plan_steps=["Identificando rosto"],
            results=[],
            outcome="success",
            summary="",
            data={"gallery_action": "identify_face"},
        )
    elif action == "select_mode":
        return PlanResult(
            plan_steps=["Entrando em modo seleção"],
            results=[],
            outcome="success",
            summary="Modo seleção ativado. Toque nas fotos para selecionar.",
            voice_mode="brief",
            data={"gallery_action": "select_mode"},
        )
    elif action == "find_duplicates":
        return _handle_find_duplicates(store)
    elif action == "edit_rotate":
        return _handle_edit_action(intent, "rotate")
    elif action == "edit_flip":
        return _handle_edit_action(intent, "flip")
    elif action == "share":
        return _handle_share(intent)
    elif action == "show_info":
        return _handle_show_info(intent)
    elif action == "delete":
        return _handle_delete(intent, store)
    elif action == "delete_selected":
        return _handle_delete_selected(intent, store)
    elif action == "undo_delete":
        return _handle_undo_delete(store)
    elif action == "create_album":
        return _handle_create_album(intent, store)
    elif action == "show_album":
        return _handle_show_album(intent, store)
    elif action == "list_albums":
        return _handle_list_albums(store)
    elif action == "add_to_album":
        return _handle_add_to_album(intent, store)
    else:
        return PlanResult(
            plan_steps=["Ação de galeria desconhecida"],
            results=[],
            outcome="failure",
            summary="Não entendi o que fazer com a galeria.",
        )


def _handle_toggle_favorite(intent: Intent, store) -> PlanResult:
    """Toggle favorite on the current/specified file."""
    file_path = intent.params.get("file_path", "")

    if not file_path:
        # Will be resolved by the UI (current image in viewer)
        return PlanResult(
            plan_steps=["Alternando favorito"],
            results=[],
            outcome="success",
            summary="",
            data={"gallery_action": "toggle_favorite"},
        )

    is_fav = store.toggle_favorite(file_path)
    name = os.path.basename(file_path)
    if is_fav:
        summary = f"★ {name} adicionado aos favoritos"
    else:
        summary = f"☆ {name} removido dos favoritos"

    return PlanResult(
        plan_steps=["Alternando favorito"],
        results=[],
        outcome="success",
        summary=summary,
        voice_mode="brief",
    )


def _handle_list_favorites(store) -> PlanResult:
    """List all favorites as a gallery."""
    from cios.skills.media_player import GallerySignal, MediaFile

    favorites = store.list_favorites()

    # Filter to files that still exist
    existing = [f for f in favorites if os.path.isfile(f)]

    if not existing:
        return PlanResult(
            plan_steps=["Buscando favoritos"],
            results=[],
            outcome="success",
            summary="Nenhum favorito ainda. Diga 'favoritar' ao ver uma foto.",
        )

    files = []
    for path in existing:
        ext = os.path.splitext(path)[1].lower()
        from cios.skills.media_player import _ext_to_type

        media_type = _ext_to_type(ext)
        files.append(
            MediaFile(
                path=path,
                name=os.path.basename(path),
                media_type=media_type,
                source="Favoritos",
            )
        )

    signal = GallerySignal(
        source_path="★ Favoritos",
        media_type="image",
        total_count=len(files),
        files=files,
    )
    signal_data = signal.to_dict()

    return PlanResult(
        plan_steps=["Carregando favoritos"],
        results=[],
        outcome="success",
        summary=f"{len(files)} favoritos",
        voice_mode="brief",
        data=signal_data,
    )


def _handle_delete(intent: Intent, store) -> PlanResult:
    """Delete the current file (move to trash)."""
    file_path = intent.params.get("file_path", "")

    if not file_path:
        # Will be resolved by the UI (current image in viewer/gallery)
        return PlanResult(
            plan_steps=["Preparando exclusão"],
            results=[],
            outcome="success",
            summary="",
            data={"gallery_action": "delete_current"},
        )

    entry = store.trash_file(file_path)
    if entry:
        name = os.path.basename(file_path)
        return PlanResult(
            plan_steps=["Movendo para lixeira"],
            results=[],
            outcome="success",
            summary=f"🗑 {name} movido para a lixeira. Diga 'desfazer' para restaurar.",
            voice_mode="brief",
        )
    else:
        return PlanResult(
            plan_steps=["Tentando deletar"],
            results=[],
            outcome="failure",
            summary="Não consegui mover o arquivo para a lixeira.",
        )


def _handle_delete_selected(intent: Intent, store) -> PlanResult:
    """Delete selected files (move to trash)."""
    file_paths = intent.params.get("file_paths", [])

    if not file_paths:
        # Will be resolved by the UI (selected files in gallery)
        return PlanResult(
            plan_steps=["Preparando exclusão em grupo"],
            results=[],
            outcome="success",
            summary="",
            data={"gallery_action": "delete_selected"},
        )

    entries = store.trash_files(file_paths)
    count = len(entries)
    if count > 0:
        return PlanResult(
            plan_steps=[f"Movendo {count} arquivos para lixeira"],
            results=[],
            outcome="success",
            summary=f"🗑 {count} arquivos movidos para a lixeira. Diga 'desfazer' para restaurar.",
            voice_mode="brief",
        )
    else:
        return PlanResult(
            plan_steps=["Tentando deletar"],
            results=[],
            outcome="failure",
            summary="Não consegui mover os arquivos para a lixeira.",
        )


def _handle_undo_delete(store) -> PlanResult:
    """Undo the last trash operation."""
    restored = store.undo_last_trash()
    if restored:
        name = os.path.basename(restored)
        return PlanResult(
            plan_steps=["Restaurando arquivo"],
            results=[],
            outcome="success",
            summary=f"↩ {name} restaurado.",
            voice_mode="brief",
        )
    else:
        return PlanResult(
            plan_steps=["Tentando restaurar"],
            results=[],
            outcome="failure",
            summary="Nada para desfazer.",
        )


def _handle_create_album(intent: Intent, store) -> PlanResult:
    """Create a new album."""
    name = intent.params.get("album_name", "").strip()
    if not name:
        return PlanResult(
            plan_steps=["Criando álbum"],
            results=[],
            outcome="failure",
            summary="Qual nome para o álbum?",
        )

    album = store.create_album(name)
    if album:
        return PlanResult(
            plan_steps=["Criando álbum"],
            results=[],
            outcome="success",
            summary=f"📁 Álbum '{name}' criado.",
            voice_mode="brief",
        )
    else:
        return PlanResult(
            plan_steps=["Criando álbum"],
            results=[],
            outcome="failure",
            summary=f"Já existe um álbum chamado '{name}'.",
        )


def _handle_show_album(intent: Intent, store) -> PlanResult:
    """Show files in an album as a gallery."""
    from cios.skills.media_player import GallerySignal, MediaFile, _ext_to_type

    name = intent.params.get("album_name", "").strip()
    if not name:
        return PlanResult(
            plan_steps=["Abrindo álbum"],
            results=[],
            outcome="failure",
            summary="Qual álbum?",
        )

    album = store.get_album_by_name(name)
    if not album:
        return PlanResult(
            plan_steps=["Buscando álbum"],
            results=[],
            outcome="failure",
            summary=f"Álbum '{name}' não encontrado.",
        )

    paths = store.get_album_files(album.id)
    existing = [p for p in paths if os.path.isfile(p)]

    if not existing:
        return PlanResult(
            plan_steps=["Abrindo álbum"],
            results=[],
            outcome="success",
            summary=f"Álbum '{album.name}' está vazio.",
        )

    files = []
    for path in existing:
        ext = os.path.splitext(path)[1].lower()
        media_type = _ext_to_type(ext)
        files.append(
            MediaFile(
                path=path,
                name=os.path.basename(path),
                media_type=media_type,
                source=album.name,
            )
        )

    signal = GallerySignal(
        source_path=f"📁 {album.name}",
        media_type="image",
        total_count=len(files),
        files=files,
    )
    signal_data = signal.to_dict()

    return PlanResult(
        plan_steps=[f"Abrindo álbum '{album.name}'"],
        results=[],
        outcome="success",
        summary=f"{len(files)} arquivos no álbum '{album.name}'",
        voice_mode="brief",
        data=signal_data,
    )


def _handle_list_albums(store) -> PlanResult:
    """List all albums."""
    albums = store.list_albums()

    if not albums:
        return PlanResult(
            plan_steps=["Listando álbuns"],
            results=[],
            outcome="success",
            summary="Nenhum álbum criado. Diga 'criar álbum [nome]' para começar.",
        )

    lines = []
    for a in albums:
        lines.append(f"📁 {a.name} ({a.file_count} arquivos)")

    summary = "\n".join(lines)
    return PlanResult(
        plan_steps=["Listando álbuns"],
        results=[],
        outcome="success",
        summary=summary,
    )


def _handle_add_to_album(intent: Intent, store) -> PlanResult:
    """Add current file to an album."""
    album_name = intent.params.get("album_name", "").strip()
    file_path = intent.params.get("file_path", "")

    if not album_name:
        return PlanResult(
            plan_steps=["Adicionando ao álbum"],
            results=[],
            outcome="failure",
            summary="Qual álbum?",
        )

    if not file_path:
        # Will be resolved by the UI
        return PlanResult(
            plan_steps=["Adicionando ao álbum"],
            results=[],
            outcome="success",
            summary="",
            data={"gallery_action": "add_to_album", "album_name": album_name},
        )

    album = store.get_album_by_name(album_name)
    if not album:
        # Auto-create album
        album = store.create_album(album_name)
        if not album:
            return PlanResult(
                plan_steps=["Adicionando ao álbum"],
                results=[],
                outcome="failure",
                summary="Não consegui criar o álbum.",
            )

    store.add_to_album(album.id, file_path)
    name = os.path.basename(file_path)
    return PlanResult(
        plan_steps=["Adicionando ao álbum"],
        results=[],
        outcome="success",
        summary=f"{name} adicionado ao álbum '{album.name}'.",
        voice_mode="brief",
    )


def _handle_find_duplicates(store) -> PlanResult:
    """Scan for duplicate images and return results."""
    from cios.skills.duplicates import format_size, scan_duplicates
    from cios.skills.media_player import GallerySignal, MediaFile

    result = scan_duplicates()

    if not result.groups:
        return PlanResult(
            plan_steps=[
                "Escaneando duplicatas",
                f"{result.total_files_scanned} arquivos verificados",
            ],
            results=[],
            outcome="success",
            summary="Nenhuma foto duplicada encontrada.",
        )

    # Build a gallery showing duplicates grouped
    # Each group's files are shown sequentially
    all_files = []
    for group in result.groups:
        for f in group.files:
            all_files.append(
                MediaFile(
                    path=f.path,
                    name=f.name,
                    media_type="image",
                    size_bytes=f.size_bytes,
                    source=f"{'Idêntica' if group.match_type == 'exact' else 'Similar'} ({len(group.files)} cópias)",
                )
            )

    wasted_str = format_size(result.wasted_bytes)
    summary = (
        f"{result.total_duplicates} duplicatas em {len(result.groups)} grupos. "
        f"{wasted_str} podem ser liberados."
    )

    signal = GallerySignal(
        source_path=f"🔍 Duplicatas ({len(result.groups)} grupos)",
        media_type="image",
        total_count=len(all_files),
        files=all_files,
    )
    signal_data = signal.to_dict()

    # Add duplicate metadata for the UI to render group separators
    signal_data["duplicates"] = {
        "groups": [
            {
                "match_type": g.match_type,
                "similarity": g.similarity,
                "file_count": len(g.files),
                "wasted_bytes": g.wasted_size,
                "best_file": g.best_file.path if g.best_file else "",
                "paths": [f.path for f in g.files],
            }
            for g in result.groups
        ],
        "total_duplicates": result.total_duplicates,
        "wasted_bytes": result.wasted_bytes,
        "scan_time_ms": result.scan_time_ms,
    }

    return PlanResult(
        plan_steps=[
            f"Escaneando {result.total_files_scanned} arquivos…",
            f"{result.total_duplicates} duplicatas encontradas",
        ],
        results=[],
        outcome="success",
        summary=summary,
        voice_mode="brief",
        data=signal_data,
    )


def _handle_search_date(intent: Intent) -> PlanResult:
    """Search media files by date."""
    from cios.skills.gallery_search import format_date_range, search_by_date
    from cios.skills.media_player import GallerySignal, MediaFile

    date_query = intent.params.get("date_query", "")
    if not date_query:
        return PlanResult(
            plan_steps=["Buscando por data"],
            results=[],
            outcome="failure",
            summary="De quando? (ontem, esta semana, janeiro, 2024…)",
        )

    result = search_by_date(date_query)

    if not result.files:
        label = format_date_range(date_query)
        return PlanResult(
            plan_steps=[f"Buscando fotos: {label}"],
            results=[],
            outcome="success",
            summary=f"Nenhuma foto encontrada para '{label}'.",
        )

    # Convert to MediaFile for gallery signal
    media_files = []
    for f in result.files:
        media_files.append(
            MediaFile(
                path=f["path"],
                name=f["name"],
                media_type=f.get("media_type", "image"),
                size_bytes=f.get("size_bytes", 0),
                source=format_date_range(date_query),
            )
        )

    label = format_date_range(date_query)
    signal = GallerySignal(
        source_path=f"📅 {label}",
        media_type="image",
        total_count=len(media_files),
        files=media_files,
    )
    signal_data = signal.to_dict()

    return PlanResult(
        plan_steps=[f"Buscando fotos: {label}"],
        results=[],
        outcome="success",
        summary=f"{len(media_files)} arquivos de '{label}'",
        voice_mode="brief",
        data=signal_data,
    )


def _handle_search_text(intent: Intent) -> PlanResult:
    """Search media files by text description (CLIP or filename)."""
    from cios.skills.gallery_search import search_by_text
    from cios.skills.media_player import GallerySignal, MediaFile

    text_query = intent.params.get("text_query", "")
    if not text_query:
        return PlanResult(
            plan_steps=["Buscando por conteúdo"],
            results=[],
            outcome="failure",
            summary="O que procura? (praia, cachorro, família…)",
        )

    result = search_by_text(text_query)

    if not result.files:
        return PlanResult(
            plan_steps=[f"Buscando: {text_query}"],
            results=[],
            outcome="success",
            summary=f"Nenhuma foto encontrada para '{text_query}'.",
        )

    # Convert to MediaFile
    media_files = []
    for f in result.files:
        media_files.append(
            MediaFile(
                path=f["path"],
                name=f["name"],
                media_type=f.get("media_type", "image"),
                size_bytes=f.get("size_bytes", 0),
                source=f"🔍 {text_query}",
            )
        )

    search_type_label = {
        "clip": "IA",
        "filename": "nome",
    }.get(result.search_type, "busca")

    signal = GallerySignal(
        source_path=f"🔍 '{text_query}' (por {search_type_label})",
        media_type="image",
        total_count=len(media_files),
        files=media_files,
    )
    signal_data = signal.to_dict()

    return PlanResult(
        plan_steps=[f"Buscando: {text_query}"],
        results=[],
        outcome="success",
        summary=f"{len(media_files)} resultados para '{text_query}'",
        voice_mode="brief",
        data=signal_data,
    )


def _handle_edit_action(intent: Intent, edit_type: str) -> PlanResult:
    """Handle image edit actions (rotate, flip) — delegates to UI if no file_path."""
    file_path = intent.params.get("file_path", "")

    if not file_path:
        # Delegate to UI (current image in viewer)
        action_map = {
            "rotate": "edit_rotate",
            "flip": "edit_flip",
        }
        return PlanResult(
            plan_steps=["Editando imagem"],
            results=[],
            outcome="success",
            summary="",
            data={"gallery_action": action_map.get(edit_type, edit_type)},
        )

    from cios.skills.image_edit import flip_image, rotate_image

    if edit_type == "rotate":
        degrees = intent.params.get("degrees", 90)
        result = rotate_image(file_path, degrees=degrees)
        if result:
            return PlanResult(
                plan_steps=["Rotacionando imagem"],
                results=[],
                outcome="success",
                summary=f"Imagem rotacionada {degrees}°.",
                voice_mode="brief",
            )
    elif edit_type == "flip":
        direction = intent.params.get("direction", "horizontal")
        result = flip_image(file_path, direction=direction)
        if result:
            return PlanResult(
                plan_steps=["Espelhando imagem"],
                results=[],
                outcome="success",
                summary=f"Imagem espelhada ({direction}).",
                voice_mode="brief",
            )

    return PlanResult(
        plan_steps=["Editando imagem"],
        results=[],
        outcome="failure",
        summary="Não consegui editar a imagem.",
    )


def _handle_share(intent: Intent) -> PlanResult:
    """Share the current file."""
    file_path = intent.params.get("file_path", "")

    if not file_path:
        return PlanResult(
            plan_steps=["Compartilhando"],
            results=[],
            outcome="success",
            summary="",
            data={"gallery_action": "share"},
        )

    from cios.skills.image_edit import share_file

    ok, msg = share_file(file_path)
    return PlanResult(
        plan_steps=["Compartilhando"],
        results=[],
        outcome="success" if ok else "failure",
        summary=msg,
        voice_mode="brief",
    )


def _handle_show_info(intent: Intent) -> PlanResult:
    """Show metadata/EXIF info for the current image."""
    file_path = intent.params.get("file_path", "")

    if not file_path:
        return PlanResult(
            plan_steps=["Mostrando informações"],
            results=[],
            outcome="success",
            summary="",
            data={"gallery_action": "show_info"},
        )

    from cios.skills.image_edit import format_metadata, get_metadata

    meta = get_metadata(file_path)
    if meta:
        return PlanResult(
            plan_steps=["Lendo metadados"],
            results=[],
            outcome="success",
            summary=format_metadata(meta),
        )
    return PlanResult(
        plan_steps=["Lendo metadados"],
        results=[],
        outcome="failure",
        summary="Não consegui ler os metadados da imagem.",
    )


def _handle_scan_faces() -> PlanResult:
    """Scan photos for faces and cluster them."""
    from cios.skills.face_cluster import (
        get_install_instructions,
        is_face_recognition_available,
        scan_and_cluster,
    )

    if not is_face_recognition_available():
        return PlanResult(
            plan_steps=["Verificando dependências"],
            results=[],
            outcome="failure",
            summary=get_install_instructions(),
        )

    result = scan_and_cluster()

    if result.error:
        return PlanResult(
            plan_steps=["Escaneando rostos"],
            results=[],
            outcome="failure",
            summary=result.error,
        )

    if not result.clusters:
        return PlanResult(
            plan_steps=[
                f"Escaneando {result.total_images_scanned} imagens",
                f"{result.total_faces_found} rostos detectados",
            ],
            results=[],
            outcome="success",
            summary="Nenhum grupo de pessoas identificado ainda. Preciso de mais fotos com rostos.",
        )

    people_list = "\n".join(f"  {c.name} ({c.face_count} fotos)" for c in result.clusters)
    summary = (
        f"{result.total_faces_found} rostos em {len(result.clusters)} pessoas:\n"
        f"{people_list}\n\n"
        f"Diga 'fotos do [nome]' para ver as fotos de alguém."
    )

    return PlanResult(
        plan_steps=[
            f"Escaneando {result.total_images_scanned} imagens",
            f"{result.total_faces_found} rostos → {len(result.clusters)} pessoas",
        ],
        results=[],
        outcome="success",
        summary=summary,
    )


def _handle_list_people() -> PlanResult:
    """List all known people (face clusters)."""
    from cios.skills.face_cluster import (
        get_install_instructions,
        is_face_recognition_available,
        list_people,
    )

    if not is_face_recognition_available():
        return PlanResult(
            plan_steps=["Verificando dependências"],
            results=[],
            outcome="failure",
            summary=get_install_instructions(),
        )

    people = list_people()

    if not people:
        return PlanResult(
            plan_steps=["Listando pessoas"],
            results=[],
            outcome="success",
            summary="Nenhuma pessoa identificada. Diga 'escanear rostos' primeiro.",
        )

    lines = [f"  {p.name} ({p.face_count} fotos)" for p in people]
    return PlanResult(
        plan_steps=["Listando pessoas"],
        results=[],
        outcome="success",
        summary=f"{len(people)} pessoas:\n" + "\n".join(lines),
    )


def _handle_search_person(intent: Intent) -> PlanResult:
    """Show photos of a specific person."""
    from cios.skills.face_cluster import (
        get_install_instructions,
        get_person_photos,
        is_face_recognition_available,
    )
    from cios.skills.media_player import GallerySignal, MediaFile

    if not is_face_recognition_available():
        return PlanResult(
            plan_steps=["Verificando dependências"],
            results=[],
            outcome="failure",
            summary=get_install_instructions(),
        )

    name = intent.params.get("person_name", "").strip()
    if not name:
        return PlanResult(
            plan_steps=["Buscando pessoa"],
            results=[],
            outcome="failure",
            summary="De quem? Diga 'fotos do [nome]'.",
        )

    paths = get_person_photos(name)

    if not paths:
        return PlanResult(
            plan_steps=[f"Buscando fotos de {name}"],
            results=[],
            outcome="success",
            summary=f"Nenhuma foto encontrada para '{name}'. "
            f"Diga 'escanear rostos' para detectar pessoas, "
            f"depois 'nomear pessoa de {name}' para atribuir um nome.",
        )

    # Filter to existing files
    existing = [p for p in paths if os.path.isfile(p)]
    if not existing:
        return PlanResult(
            plan_steps=[f"Buscando fotos de {name}"],
            results=[],
            outcome="success",
            summary=f"Fotos de '{name}' não encontradas no disco.",
        )

    files = [
        MediaFile(
            path=p,
            name=os.path.basename(p),
            media_type="image",
            source=f"👤 {name}",
        )
        for p in existing
    ]

    signal = GallerySignal(
        source_path=f"👤 {name}",
        media_type="image",
        total_count=len(files),
        files=files,
    )
    signal_data = signal.to_dict()

    return PlanResult(
        plan_steps=[f"Buscando fotos de {name}"],
        results=[],
        outcome="success",
        summary=f"{len(files)} fotos de {name}",
        voice_mode="brief",
        data=signal_data,
    )


def _handle_name_person(intent: Intent) -> PlanResult:
    """Name a face cluster."""
    from cios.skills.face_cluster import is_face_recognition_available, list_people, name_person

    if not is_face_recognition_available():
        from cios.skills.face_cluster import get_install_instructions

        return PlanResult(
            plan_steps=["Verificando dependências"],
            results=[],
            outcome="failure",
            summary=get_install_instructions(),
        )

    person_name = intent.params.get("person_name", "").strip()
    if not person_name:
        return PlanResult(
            plan_steps=["Nomeando pessoa"],
            results=[],
            outcome="failure",
            summary="Qual nome?",
        )

    # Name the most recent unnamed cluster (or delegate to UI)
    people = list_people()
    unnamed = [p for p in people if p.name.startswith("Pessoa ")]

    if not unnamed:
        return PlanResult(
            plan_steps=["Nomeando pessoa"],
            results=[],
            outcome="failure",
            summary="Nenhuma pessoa sem nome. Escaneie rostos primeiro.",
        )

    # Name the first unnamed cluster
    target = unnamed[0]
    name_person(target.cluster_id, person_name)

    return PlanResult(
        plan_steps=["Nomeando pessoa"],
        results=[],
        outcome="success",
        summary=f"'{target.name}' agora se chama '{person_name}'.",
        voice_mode="brief",
    )
