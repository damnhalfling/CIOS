"""Intelligence patterns — briefing, intelligence (news, explain, write, summarize, translate), personal_memory, history_search, intent_browse, intent_write, todo."""

from __future__ import annotations

import re
from collections.abc import Callable

from cios.core.intent_types import IntentType

RULES: list[tuple[re.Pattern, IntentType, Callable | None, float]] = [
    # --- history search (PT + EN) — MUST be before intent_browse ---
    (
        re.compile(
            r"(?:busca|procura|pesquisa)\s+(?:no\s+|em\s+|nas?\s+)?(?:histórico|historico|conversas?)\s+(?:sobre\s+|por\s+)?(.+)",
            re.IGNORECASE,
        ),
        IntentType.HISTORY_SEARCH,
        lambda m: {"query": m.group(1).strip()},
        0.95,
    ),
    (
        re.compile(
            r"(?:o\s+que|quando)\s+(?:eu\s+)?(?:falei|disse|pedi|fiz)\s+(?:sobre\s+)?(.+)",
            re.IGNORECASE,
        ),
        IntentType.HISTORY_SEARCH,
        lambda m: {"query": m.group(1).strip()},
        0.92,
    ),
    (
        re.compile(
            r"(?:search|find)\s+(?:in\s+)?(?:history|conversations?)\s+(?:about\s+|for\s+)?(.+)",
            re.IGNORECASE,
        ),
        IntentType.HISTORY_SEARCH,
        lambda m: {"query": m.group(1).strip()},
        0.95,
    ),
    (
        re.compile(
            r"(?:what|when)\s+did\s+I\s+(?:say|ask|do)\s+(?:about\s+)?(.+)",
            re.IGNORECASE,
        ),
        IntentType.HISTORY_SEARCH,
        lambda m: {"query": m.group(1).strip()},
        0.92,
    ),
    (
        re.compile(
            r"(?:meu\s+)?histórico\s+(?:de\s+|sobre\s+)?(.+)",
            re.IGNORECASE,
        ),
        IntentType.HISTORY_SEARCH,
        lambda m: {"query": m.group(1).strip()},
        0.90,
    ),
    # --- intent browse (PT + EN) — MUST be before app_launch ---
    # With search query (excludes "pacote/package/arquivo/file" which are other intents)
    (
        re.compile(
            r"(?:pesquis[ae]r?|googl[ae]r?)\s+(?:sobre\s+|por\s+|a?\s*)?(.+)",
            re.IGNORECASE,
        ),
        IntentType.INTENT_BROWSE,
        lambda m: {"query": m.group(1).strip()},
        0.92,
    ),
    (
        re.compile(
            r"(?:buscar?|procurar?)\s+(?:sobre\s+|por\s+|na\s+(?:internet|web|net)\s+)?(?!pacote\b|package\b|arquivo\b|file\b|hist[oó]rico\b|conversas?\b)(.+)",
            re.IGNORECASE,
        ),
        IntentType.INTENT_BROWSE,
        lambda m: {"query": m.group(1).strip()},
        0.88,
    ),
    (
        re.compile(
            r"(?:search|google|look\s+up)\s+(?:for\s+|about\s+)?(?!package\b|file\b|history\b|conversations?\b)(.+)",
            re.IGNORECASE,
        ),
        IntentType.INTENT_BROWSE,
        lambda m: {"query": m.group(1).strip()},
        0.92,
    ),
    # Generic (no query)
    (
        re.compile(
            r"(?:quero|vou|preciso)\s+(?:pesquisar|buscar|procurar|navegar|search|browse)\s+(?:algo|na\s+internet|online|something)",
            re.IGNORECASE,
        ),
        IntentType.INTENT_BROWSE,
        None,
        0.95,
    ),
    (
        re.compile(
            r"(?:I\s+want\s+to|let\s*(?:'s|me))\s+(?:search|browse|look\s+up|google)\s+(?:something|the\s+web|online)",
            re.IGNORECASE,
        ),
        IntentType.INTENT_BROWSE,
        None,
        0.95,
    ),
    # --- intent write (PT + EN) — MUST be before app_launch ---
    (
        re.compile(
            r"(?:quero|vou|preciso)\s+(?:escrever|redigir|criar|write)\s+(?:um?\s+)?(?:documento|texto|carta|relat[oó]rio|document|text|letter|report)",
            re.IGNORECASE,
        ),
        IntentType.INTENT_WRITE,
        lambda m: {"doc_type": "document"},
        0.95,
    ),
    (
        re.compile(
            r"(?:I\s+want\s+to|let\s*(?:'s|me))\s+(?:write|create|draft)\s+(?:a\s+)?(?:document|text|letter|report|essay)",
            re.IGNORECASE,
        ),
        IntentType.INTENT_WRITE,
        lambda m: {"doc_type": "document"},
        0.95,
    ),
    # --- daily briefing / meu dia (PT + EN) ---
    (
        re.compile(
            r"(?:(?:meu|como\s+(?:est[aá]|tá)\s+(?:meu|o))\s+dia|"
            r"daily\s*briefing|morning\s*briefing|"
            r"(?:mostr[ae]|ver|exib[ei]r?)\s+(?:meu\s+)?(?:dia|briefing|planejamento)|"
            r"(?:o\s+que\s+(?:tenho|tem)\s+(?:pra\s+)?hoje)|"
            r"(?:como\s+(?:est[aá]|tá)\s+(?:minha\s+)?(?:agenda|dia))|"
            r"(?:resuma?|resume)\s+(?:meu\s+)?dia)",
            re.IGNORECASE,
        ),
        IntentType.BRIEFING,
        lambda m: {},
        0.95,
    ),
    # --- intelligence: news (PT + EN) ---
    (
        re.compile(
            r"(?:not[ií]cias|news|o\s+que\s+(?:est[aá]\s+acontecendo|aconteceu\s+(?:hoje|no\s+mundo))|"
            r"resum[ao]\s+(?:as\s+)?not[ií]cias|what(?:'s|\s+is)\s+happening|"
            r"headlines|manchetes|novidades\s+(?:do\s+dia|de\s+hoje))",
            re.IGNORECASE,
        ),
        IntentType.INTELLIGENCE,
        lambda m: {"intent": "news"},
        0.90,
    ),
    # --- intelligence: explain (PT + EN) ---
    (
        re.compile(
            r"(?:expli(?:que|ca)|explain|o\s+que\s+[eé]|what\s+is|"
            r"como\s+funciona|how\s+does|me\s+(?:explica|fala\s+sobre)|"
            r"tell\s+me\s+about|define|defina)",
            re.IGNORECASE,
        ),
        IntentType.INTELLIGENCE,
        lambda m: {"intent": "explain"},
        0.85,
    ),
    # --- intelligence: write (PT + EN) ---
    (
        re.compile(
            r"(?:escrev[ea]|write|redigi[ra]|gera?r?|cri[ae]|create|compose|"
            r"fa[cç]a?\s+(?:um|uma)\s+(?:texto|email|mensagem|carta|post)|"
            r"draft\s+(?:a|an)\s+(?:email|message|text|letter|post))",
            re.IGNORECASE,
        ),
        IntentType.INTELLIGENCE,
        lambda m: {"intent": "write"},
        0.85,
    ),
    # --- intelligence: summarize (PT + EN) ---
    (
        re.compile(
            r"(?:resum[aeiou]|summarize|summary|sintetiz[ae]|"
            r"fa[cç]a?\s+(?:um\s+)?resumo|give\s+me\s+a\s+summary)",
            re.IGNORECASE,
        ),
        IntentType.INTELLIGENCE,
        lambda m: {"intent": "summarize"},
        0.88,
    ),
    # --- intelligence: translate (PT + EN) ---
    (
        re.compile(
            r"(?:traduz[aie]?|translate|tradu[cç][aã]o|"
            r"como\s+(?:se\s+)?(?:diz|fala)\s+.+\s+em\s+|"
            r"how\s+(?:do\s+you\s+)?say\s+.+\s+in\s+)",
            re.IGNORECASE,
        ),
        IntentType.INTELLIGENCE,
        lambda m: {"intent": "translate"},
        0.88,
    ),
    # --- Personal Memory (PT + EN) → routes to Intelligence ---
    (
        re.compile(
            r"(?:o\s+qu[ée]\s+)?(?:voc[êe]|vc|tu)\s+(?:sabe|lembra|conhece)\s+(?:sobre|de)\s+mim",
            re.IGNORECASE,
        ),
        IntentType.INTELLIGENCE,
        lambda m: {"intent": "personal_memory"},
        0.95,
    ),
    (
        re.compile(
            r"(?:quem\s+(?:sou\s+eu|eu\s+sou))|(?:me\s+(?:conhece|descreve))",
            re.IGNORECASE,
        ),
        IntentType.INTELLIGENCE,
        lambda m: {"intent": "personal_memory"},
        0.93,
    ),
    (
        re.compile(
            r"(?:what\s+do\s+you\s+know\s+about\s+me|who\s+am\s+i|do\s+you\s+(?:know|remember)\s+me)",
            re.IGNORECASE,
        ),
        IntentType.INTELLIGENCE,
        lambda m: {"intent": "personal_memory"},
        0.93,
    ),
    (
        re.compile(
            r"(?:meus?\s+projetos?|my\s+projects?|quais?\s+(?:meus?|são\s+meus?)\s+projetos?)",
            re.IGNORECASE,
        ),
        IntentType.INTELLIGENCE,
        lambda m: {"intent": "projects"},
        0.92,
    ),
    # --- TODO / Task management (PT + EN) ---
    (
        re.compile(
            r"(?:adiciona(?:r)?|nova|cria(?:r)?|add)\s+(?:uma?\s+)?(?:tarefa|task|todo)[:\s]+(.+)",
            re.IGNORECASE,
        ),
        IntentType.TODO,
        lambda m: {"action": "add", "text": m.group(1).strip()},
        0.95,
    ),
    (
        re.compile(
            r"(?:show|list|display|get)\s+(?:my\s+)?(?:todo|todos|tasks?|task\s*list|pending)",
            re.IGNORECASE,
        ),
        IntentType.TODO,
        lambda m: {"action": "list"},
        0.93,
    ),
    (
        re.compile(
            r"(?:minhas?\s+)?(?:tarefas|tasks|todos|pendências|pendencias)",
            re.IGNORECASE,
        ),
        IntentType.TODO,
        lambda m: {"action": "list"},
        0.90,
    ),
    (
        re.compile(
            r"(?:o\s+que\s+(?:tenho|tem|falta)\s+(?:pendente|pra\s+fazer|fazer)|"
            r"o\s+que\s+falta|(?:quais?\s+(?:são\s+)?(?:minhas?\s+)?pendências)|"
            r"(?:what(?:'s|\s+is)\s+pending|what\s+do\s+i\s+(?:have|need)\s+to\s+do))",
            re.IGNORECASE,
        ),
        IntentType.TODO,
        lambda m: {"action": "list"},
        0.92,
    ),
    (
        re.compile(
            r"(?:marca(?:r)?|completa(?:r)?|feit[ao]|done)\s+(?:a?\s+)?(?:tarefa|task|todo)\s+#?(\d+)",
            re.IGNORECASE,
        ),
        IntentType.TODO,
        lambda m: {"action": "done", "id": int(m.group(1))},
        0.95,
    ),
    (
        re.compile(
            r"(?:remove(?:r)?|deleta(?:r)?|apaga(?:r)?)\s+(?:a?\s+)?(?:tarefa|task|todo)\s+#?(\d+)",
            re.IGNORECASE,
        ),
        IntentType.TODO,
        lambda m: {"action": "remove", "id": int(m.group(1))},
        0.95,
    ),
    (
        re.compile(
            r"(?:próximas?|next|urgentes?|top)\s+(?:tarefas|tasks|todos)",
            re.IGNORECASE,
        ),
        IntentType.TODO,
        lambda m: {"action": "top"},
        0.90,
    ),
]
