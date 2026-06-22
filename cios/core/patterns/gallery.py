"""Gallery patterns — face/people, date search, content search, duplicates, edit, favorites, albums."""

from __future__ import annotations

import re

from cios.core.intent_types import IntentType

RULES: list[tuple[re.Pattern, IntentType, callable | None, float]] = [
    # --- gallery manage: face/people (PT + EN) — MUST be before intent_media ---
    (
        re.compile(
            r"(?:mostr[ae]r?|show|ver)\s+(?:as\s+|my\s+)?(?:(?:fotos?|photos?|imagens?|images?)\s+)?(?:por\s+pessoa|by\s+person|por\s+rosto|by\s+face)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "list_people"},
        0.95,
    ),
    (
        re.compile(
            r"(?:fotos?|imagens?|photos?|images?)\s+(?:do|da|de|of|with)\s+([A-Z\u00C0-\u024F][a-z\u00C0-\u024F]+(?:\s+[A-Z\u00C0-\u024F][a-z\u00C0-\u024F]+)?)",
            re.UNICODE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "search_person", "person_name": m.group(1).strip()},
        0.92,
    ),
    (
        re.compile(
            r"(?:quem\s+(?:é|são)|who\s+(?:is|are))\s+(?:essa?|this|na\s+foto|in\s+the\s+photo)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "identify_face"},
        0.90,
    ),
    (
        re.compile(
            r"(?:escanear?|scan|detectar?|detect)\s+(?:os?\s+)?(?:rostos?|faces?|pessoas?|people)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "scan_faces"},
        0.95,
    ),
    (
        re.compile(
            r"(?:nomear?|name|chamar?|call)\s+(?:essa?\s+|this\s+)?(?:pessoa|person|rosto|face)\s+(?:de\s+)?(.+)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "name_person", "person_name": m.group(1).strip()},
        0.95,
    ),
    # --- gallery search: by date (PT + EN) — MUST be before intent_media ---
    (
        re.compile(
            r"(?:fotos?|imagens?|photos?|images?)\s+(?:de|da|do|from|desta|deste|dessa|desse)\s+(ontem|hoje|yesterday|today|esta\s+semana|this\s+week|este\s+m[eê]s|this\s+month)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "search_date", "date_query": m.group(1).strip()},
        0.95,
    ),
    (
        re.compile(
            r"(?:fotos?|imagens?|photos?|images?)\s+(?:desta|dessa)\s+(semana)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "search_date", "date_query": "esta semana"},
        0.95,
    ),
    (
        re.compile(
            r"(?:fotos?|imagens?|photos?|images?)\s+(?:deste|desse)\s+(m[eê]s)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "search_date", "date_query": "este mês"},
        0.95,
    ),
    (
        re.compile(
            r"(?:fotos?|imagens?|photos?|images?)\s+(?:de|from|do|da)\s+(janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro|january|february|march|april|may|june|july|august|september|october|november|december)(?:\s+(?:de\s+)?(\d{4}))?",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {
            "action": "search_date",
            "date_query": (m.group(1) + (" " + m.group(2) if m.group(2) else "")).strip(),
        },
        0.95,
    ),
    (
        re.compile(
            r"(?:fotos?|imagens?|photos?|images?)\s+(?:de|from|do|da)\s+(\d{4})",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "search_date", "date_query": m.group(1)},
        0.90,
    ),
    (
        re.compile(
            r"(?:fotos?|imagens?|photos?|images?)\s+(?:dos?|das?|from\s+the)\s+[uú]ltimos?\s+(\d+)\s+(?:dias?|days?)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "search_date", "date_query": f"últimos {m.group(1)} dias"},
        0.95,
    ),
    (
        re.compile(
            r"(?:photos?|images?)\s+from\s+(?:the\s+)?last\s+(\d+)\s+days?",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "search_date", "date_query": f"last {m.group(1)} days"},
        0.95,
    ),
    # --- gallery search: by content/text (PT + EN) — MUST be before intent_media ---
    (
        re.compile(
            r"(?:fotos?|imagens?|photos?|images?)\s+(?:com|with|de|do|da|que\s+(?:tem|t[eê]m|have))\s+(.+)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "search_text", "text_query": m.group(1).strip()},
        0.90,
    ),
    (
        re.compile(
            r"(?:fotos?|imagens?|photos?|images?)\s+(?:na|no|in|at|em)\s+(.+)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "search_text", "text_query": m.group(1).strip()},
        0.88,
    ),
    # --- gallery manage: duplicates (PT + EN) — MUST be before intent_media ---
    (
        re.compile(
            r"(?:mostr[ae]r?|show|ver|encontrar?|find|buscar?)\s+(?:as\s+|my\s+)?(?:fotos?\s+)?(?:repetid[ao]s?|duplicad[ao]s?|duplicates?|iguais)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "find_duplicates"},
        0.95,
    ),
    (
        re.compile(
            r"(?:limpar?|clean|remover?|remove)\s+(?:as\s+)?(?:fotos?\s+)?(?:repetid[ao]s?|duplicad[ao]s?|duplicates?|iguais)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "find_duplicates"},
        0.95,
    ),
    (
        re.compile(
            r"(?:fotos?|imagens?|photos?|images?)\s+(?:repetid[ao]s?|duplicad[ao]s?|duplicates?|iguais)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "find_duplicates"},
        0.90,
    ),
    # --- gallery manage: edit actions (PT + EN) ---
    (
        re.compile(
            r"(?:girar?|rotacionar?|rotate|turn)\s+(?:a\s+)?(?:foto|imagem|image|photo)(?:\s+(?:90|180))?",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "edit_rotate", "degrees": 90},
        0.95,
    ),
    (
        re.compile(
            r"(?:espelhar?|flip|inverter?)\s+(?:a\s+)?(?:foto|imagem|image|photo)(?:\s+(?:horizontal|vertical))?",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "edit_flip", "direction": "horizontal"},
        0.95,
    ),
    (
        re.compile(
            r"(?:compartilhar?|share|enviar?|send)\s+(?:a?\s+)?(?:essa?\s+|this\s+)?(?:foto|imagem|image|photo|arquivo|file)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "share"},
        0.95,
    ),
    (
        re.compile(
            r"(?:info|informa[cç][oõ]es?|metadata|exif|detalhes?|details?)\s+(?:da?\s+)?(?:foto|imagem|image|photo)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "show_info"},
        0.95,
    ),
    # --- gallery manage: list favorites (PT + EN) — MUST be before toggle ---
    (
        re.compile(
            r"(?:mostr[ae]r?|show|ver|list)\s+(?:as\s+|my\s+|minhas?\s+)?(?:favorit[ao]s|favorites|starred)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "list_favorites"},
        0.95,
    ),
    # --- gallery manage: toggle favorite (PT + EN) ---
    (
        re.compile(
            r"(?:favorit[ae]r?|favorite|★)\s*(?:essa?|this|a\s+foto|the\s+photo|a\s+imagem|the\s+image)?",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "toggle_favorite"},
        0.95,
    ),
    # --- gallery manage: select mode (PT + EN) ---
    (
        re.compile(
            r"(?:selecionar?|select)\s+(?:fotos?|photos?|imagens?|images?|arquivos?|files?|tudo|all)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "select_mode"},
        0.95,
    ),
    (
        re.compile(
            r"(?:delet[ae]r?|delete|apagar?|remover?|remove|excluir?)\s+(?:essa?|this|a\s+foto|the\s+photo|a\s+imagem|the\s+image)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "delete"},
        0.95,
    ),
    (
        re.compile(
            r"(?:delet[ae]r?|delete|apagar?|remover?|remove|excluir?)\s+(?:as\s+)?(?:selecionad[ao]s?|selected)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "delete_selected"},
        0.95,
    ),
    # --- gallery manage: undo delete (PT + EN) ---
    (
        re.compile(
            r"(?:desfazer?|undo|restaurar?|restore)\s+(?:a?\s+)?(?:exclus[aã]o|dele[cç][aã]o|delete|last)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "undo_delete"},
        0.95,
    ),
    # --- gallery manage: albums (PT + EN) ---
    (
        re.compile(
            r"(?:criar?|create|novo)\s+(?:um?\s+)?[aá]lbum\s+(.+)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "create_album", "album_name": m.group(1).strip()},
        0.95,
    ),
    (
        re.compile(
            r"(?:mostr[ae]r?|show|ver|abr[aie]r?|open)\s+(?:o\s+)?[aá]lbum\s+(.+)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "show_album", "album_name": m.group(1).strip()},
        0.95,
    ),
    (
        re.compile(
            r"(?:mostr[ae]r?|show|ver|list[ae]r?)\s+(?:os?\s+|meus?\s+)?[aá]lbuns",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "list_albums"},
        0.95,
    ),
    (
        re.compile(
            r"(?:adicionar?|add|colocar?|put)\s+(?:no|in|ao)\s+[aá]lbum\s+(.+)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "add_to_album", "album_name": m.group(1).strip()},
        0.95,
    ),
]
