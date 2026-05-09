"""
기본 Jinja2 HTML → Playwright → PDF 렌더링.
Playwright 미설치 시 fallback_renderer(reportlab)로 자동 폴백.
"""
import logging
import ssl
import tempfile
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domains.action.minutes_pipeline.data_mapper import MinuteFields

logger = logging.getLogger(__name__)

_FONT_STORAGE_DIR = Path(tempfile.gettempdir()) / "workb-fonts"

_FONT_DOWNLOAD_SPECS: list[tuple[str, str, list[str]]] = [
    (
        "NanumGothic",
        "NanumGothic.ttf",
        [
            "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf",
            "https://raw.githubusercontent.com/naver/nanumfont/master/fonts/NanumGothic.ttf",
        ],
    ),
    (
        "NanumGothicBold",
        "NanumGothicBold.ttf",
        [
            "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Bold.ttf",
            "https://raw.githubusercontent.com/naver/nanumfont/master/fonts/NanumGothicBold.ttf",
        ],
    ),
]


def _build_ssl_context() -> ssl.SSLContext:
    """가능하면 certifi 번들을 사용하고, 없으면 시스템 CA를 사용합니다."""
    try:
        import certifi  # type: ignore
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()

def prefetch_fonts() -> bool:
    """PDF 폰트를 캐시 디렉터리에 미리 다운로드합니다."""
    _FONT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    any_success = False
    ssl_ctx = _build_ssl_context()
    for _name, filename, urls in _FONT_DOWNLOAD_SPECS:
        dest = _FONT_STORAGE_DIR / filename
        if dest.exists() and dest.stat().st_size > 10_000:
            any_success = True
            continue
        for url in urls:
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": "workb-backend/1.0 (font-downloader)"}
                )
                with urllib.request.urlopen(req, timeout=30, context=ssl_ctx) as resp:
                    data = resp.read()
                if len(data) > 10_000:
                    dest.write_bytes(data)
                    logger.info("폰트 다운로드 완료: %s (%d bytes)", dest, len(data))
                    any_success = True
                    break
            except ssl.SSLError as exc:
                logger.warning("폰트 다운로드 SSL 실패 (%s): %s", url, exc)
            except Exception as exc:
                logger.warning("폰트 다운로드 실패 (%s): %s", url, exc)
    return any_success


def _get_font_urls() -> tuple[str, str]:
    reg_path = _FONT_STORAGE_DIR / "NanumGothic.ttf"
    bold_path = _FONT_STORAGE_DIR / "NanumGothicBold.ttf"
    if not (reg_path.exists() and reg_path.stat().st_size > 10_000):
        prefetch_fonts()
    reg_url = reg_path.resolve().as_uri() if reg_path.exists() else ""
    bold_url = bold_path.resolve().as_uri() if bold_path.exists() else reg_url
    return reg_url, bold_url


def _md_to_html(text: str) -> str:
    """마크다운 텍스트를 HTML로 변환한다."""
    if not text:
        return ""
    import markdown as _md
    return _md.markdown(text, extensions=["tables", "nl2br"])


def _md_to_html_row(text: str) -> str:
    """결정사항 행용: 앞의 리스트 마커(- / * / 1.)를 제거하고 인라인 마크다운만 변환한다."""
    if not text:
        return ""
    import re
    t = text.strip()
    t = re.sub(r"^[-*]\s+", "", t)
    t = re.sub(r"^\d+\.\s+", "", t)
    import markdown as _md
    html = _md.markdown(t, extensions=["nl2br"])
    # 단일 <p> 래핑 제거
    if html.startswith("<p>") and html.endswith("</p>") and html.count("<p>") == 1:
        html = html[3:-4]
    return html


def _to_renderable_image_url(raw: str) -> str:
    """로컬 경로면 file:// URI로 변환한다."""
    if not raw:
        return ""
    v = raw.strip()
    if v.startswith(("http://", "https://", "file://", "data:")):
        return v
    p = Path(v)
    try:
        return p.resolve().as_uri()
    except Exception:
        return v


def render(fields: "MinuteFields") -> bytes:
    """
    기본 Jinja2 HTML → Playwright → PDF 렌더링.
    Playwright 미설치 시 fallback_renderer로 자동 폴백.
    """
    try:
        from jinja2 import Environment, FileSystemLoader
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("playwright 또는 jinja2 미설치 — reportlab 폴백")
        from app.domains.action.minutes_pipeline import fallback_renderer
        return fallback_renderer.render(fields)

    reg_url, bold_url = _get_font_urls()

    ctx = dict(
        reg_font_url=reg_url,
        bold_font_url=bold_url,
        datetime=fields.datetime,
        dept=fields.dept,
        author=fields.author,
        attendees=fields.attendees,
        agenda_items=_md_to_html(fields.agenda_items),
        discussion_content=_md_to_html(fields.discussion_content),
        decision_rows=[_md_to_html_row(r) for r in fields.decision_rows],
        action_items=_md_to_html(fields.action_items),
        special_notes=_md_to_html(fields.special_notes),
        photo_urls=[_to_renderable_image_url(u) for u in fields.photo_urls if u],
    )

    template_dir = (
        Path(__file__).parent.parent / "templates"
    )
    env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=False)
    html_str = env.get_template("meeting_minutes.html").render(**ctx)

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.set_viewport_size({"width": 794, "height": 1123})
            try:
                page.emulate_media(media="print")
            except Exception:
                pass
            page.set_content(html_str, wait_until="load")
            pdf_bytes: bytes = page.pdf(
                format="A4",
                print_background=True,
                prefer_css_page_size=True,
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            )
            browser.close()
        return pdf_bytes
    except Exception as exc:
        logger.warning("Playwright PDF 렌더링 실패 — reportlab 폴백: %s", exc)
        from app.domains.action.minutes_pipeline import fallback_renderer
        return fallback_renderer.render(fields)


def preview_from_pdf_bytes(
    pdf_bytes: bytes,
    pages: list[int] | None = None,
    dpi: int = 150,
) -> list[bytes]:
    import fitz
    doc = fitz.open("pdf", pdf_bytes)
    mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
    target = pages if pages is not None else list(range(len(doc)))
    result = [doc[i].get_pixmap(matrix=mat, alpha=False).tobytes("png") for i in target]
    doc.close()
    return result


def get_pdf_page_size(pdf_bytes: bytes) -> tuple[float, float]:
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        if doc.page_count > 0:
            r = doc[0].rect
            w, h = float(r.width), float(r.height)
            doc.close()
            return w, h
        doc.close()
    except Exception as exc:
        logger.debug("PDF 크기 조회 실패, 기본값 사용: %s", exc)
    return 595.0, 842.0
