"""Content Viewer — Lightweight reader for URLs and PDFs.

Extracts readable text from web pages and PDF files without
rendering HTML or spawning heavy browser processes.

Supports:
- Web URLs → fetches page, extracts article text (reader mode)
- Local PDF files → extracts text per page
- Plain text / markdown passthrough
"""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def fetch_url_content(url: str) -> tuple[str, str]:
    """Fetch a URL and extract readable text content.

    Returns (title, content) as markdown-ish text.
    Lightweight: no JS rendering, just HTML parsing.
    """
    try:
        import requests
        from bs4 import BeautifulSoup

        headers = {
            "User-Agent": "CIOS/2.0 (reader mode)",
            "Accept": "text/html,application/xhtml+xml",
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract title
        title = ""
        if soup.title:
            title = soup.title.get_text(strip=True)

        # Remove noise elements
        for tag in soup(
            ["script", "style", "nav", "footer", "header", "aside", "iframe", "noscript"]
        ):
            tag.decompose()

        # Try to find main content area
        content_area = (
            soup.find("article")
            or soup.find("main")
            or soup.find(attrs={"role": "main"})
            or soup.find("div", class_=re.compile(r"content|article|post|entry|body", re.I))
            or soup.body
        )

        if not content_area:
            return title or url, "Não foi possível extrair conteúdo desta página."

        # Extract text with basic structure
        lines = []
        for element in content_area.find_all(
            ["h1", "h2", "h3", "h4", "p", "li", "blockquote", "pre", "code"]
        ):
            tag = element.name
            text = element.get_text(strip=True)
            if not text:
                continue

            if tag == "h1":
                lines.append(f"\n# {text}\n")
            elif tag == "h2":
                lines.append(f"\n## {text}\n")
            elif tag in ("h3", "h4"):
                lines.append(f"\n### {text}\n")
            elif tag == "li":
                lines.append(f"• {text}")
            elif tag == "blockquote":
                lines.append(f"> {text}")
            elif tag in ("pre", "code"):
                lines.append(f"```\n{text}\n```")
            else:
                lines.append(text)

        content = "\n".join(lines)

        # Trim if too long
        if len(content) > 15000:
            content = content[:15000] + "\n\n[… conteúdo truncado]"

        return title or url, content

    except ImportError:
        return url, "Erro: bibliotecas requests/beautifulsoup4 não instaladas."
    except Exception as e:
        logger.warning("Failed to fetch URL %s: %s", url, e)
        return url, f"Erro ao acessar: {e}"


def read_pdf_content(path: str) -> tuple[str, str]:
    """Extract text from a PDF file.

    Returns (title, content) with page markers.
    """
    try:
        import fitz  # pymupdf

        file_path = Path(path).expanduser()
        if not file_path.exists():
            return path, f"Arquivo não encontrado: {path}"

        doc = fitz.open(str(file_path))
        title = doc.metadata.get("title", "") or file_path.stem

        pages = []
        for i, page in enumerate(doc):
            text = page.get_text("text").strip()
            if text:
                pages.append(f"── Página {i + 1} ──\n{text}")

        doc.close()

        content = "\n\n".join(pages)

        if len(content) > 20000:
            content = content[:20000] + "\n\n[… conteúdo truncado]"

        if not content:
            return title, "PDF sem texto extraível (pode ser escaneado/imagem)."

        return title, content

    except ImportError:
        return path, "Erro: pymupdf não instalado. Instale com: pip install pymupdf"
    except Exception as e:
        logger.warning("Failed to read PDF %s: %s", path, e)
        return path, f"Erro ao ler PDF: {e}"


def detect_content_type(reference: str) -> str:
    """Detect if a reference is a URL, PDF path, or plain text.

    Returns: 'url', 'pdf', or 'text'
    """
    if reference.startswith(("http://", "https://")):
        return "url"
    if reference.lower().endswith(".pdf") or "/pdf/" in reference.lower():
        return "pdf"
    if Path(reference).expanduser().exists() and Path(reference).suffix.lower() == ".pdf":
        return "pdf"
    return "text"


def open_content(reference: str) -> tuple[str, str]:
    """Open any content reference and return (title, readable_text).

    Handles URLs, PDFs, and plain text.
    """
    content_type = detect_content_type(reference)

    if content_type == "url":
        return fetch_url_content(reference)
    elif content_type == "pdf":
        return read_pdf_content(reference)
    else:
        return "Conteúdo", reference
