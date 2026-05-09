"""
ReportLab 기반 회의록 PDF 생성 — Playwright 미설치 시 폴백.
"""
import io
import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domains.action.minutes_pipeline.data_mapper import MinuteFields

logger = logging.getLogger(__name__)

_FONT_STORAGE_DIR = Path(tempfile.gettempdir()) / "workb-fonts"

_FONT_REGULAR = "NanumGothic"
_FONT_BOLD = "NanumGothicBold"
_FONT_REGISTERED = False

_SYSTEM_FONT_CANDIDATES: list[tuple[str, str, str | None]] = [
    ("NanumGothic", "/Library/Fonts/NanumGothic.ttf", "/Library/Fonts/NanumGothicBold.ttf"),
    ("AppleGothic", "/System/Library/Fonts/Supplemental/AppleGothic.ttf", None),
    ("AppleGothic", "/System/Library/Fonts/AppleGothic.ttf", None),
    ("NanumGothic", "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
     "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"),
    ("NotoSansCJK", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", None),
    ("NotoSansCJK", "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc", None),
]


def _ensure_fonts() -> tuple[str, str]:
    global _FONT_REGULAR, _FONT_BOLD, _FONT_REGISTERED
    if _FONT_REGISTERED:
        return _FONT_REGULAR, _FONT_BOLD

    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfbase.pdfmetrics import registerFontFamily

        reg_path = _FONT_STORAGE_DIR / "NanumGothic.ttf"
        bold_path = _FONT_STORAGE_DIR / "NanumGothicBold.ttf"

        if reg_path.exists() and reg_path.stat().st_size > 10_000:
            try:
                pdfmetrics.registerFont(TTFont("NanumGothic", str(reg_path)))
                bold_name = "NanumGothic"
                if bold_path.exists() and bold_path.stat().st_size > 10_000:
                    pdfmetrics.registerFont(TTFont("NanumGothicBold", str(bold_path)))
                    bold_name = "NanumGothicBold"
                registerFontFamily("NanumGothic", normal="NanumGothic", bold=bold_name,
                                   italic="NanumGothic", boldItalic=bold_name)
                _FONT_REGULAR = "NanumGothic"
                _FONT_BOLD = bold_name
                _FONT_REGISTERED = True
                return _FONT_REGULAR, _FONT_BOLD
            except Exception as exc:
                logger.warning("임시 폰트 디렉터리 등록 실패: %s", exc)

        for reg_name, sys_reg, sys_bold in _SYSTEM_FONT_CANDIDATES:
            if not Path(sys_reg).exists():
                continue
            try:
                pdfmetrics.registerFont(TTFont(reg_name, sys_reg))
            except Exception:
                continue
            bold_name = reg_name
            if sys_bold and Path(sys_bold).exists():
                try:
                    pdfmetrics.registerFont(TTFont(reg_name + "Bold", sys_bold))
                    bold_name = reg_name + "Bold"
                except Exception:
                    pass
            registerFontFamily(reg_name, normal=reg_name, bold=bold_name,
                               italic=reg_name, boldItalic=bold_name)
            _FONT_REGULAR = reg_name
            _FONT_BOLD = bold_name
            _FONT_REGISTERED = True
            logger.info("시스템 폰트 등록: %s (%s)", reg_name, sys_reg)
            return _FONT_REGULAR, _FONT_BOLD

    except Exception as exc:
        logger.warning("폰트 등록 중 예외: %s", exc)

    logger.warning("한글 폰트 없음 — Helvetica 대체 (한글 깨짐)")
    _FONT_REGULAR = "Helvetica"
    _FONT_BOLD = "Helvetica-Bold"
    _FONT_REGISTERED = True
    return _FONT_REGULAR, _FONT_BOLD


def render(fields: "MinuteFields") -> bytes:
    """ReportLab으로 기본 회의록 PDF를 생성합니다 (Playwright 폴백)."""
    try:
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        )
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.colors import black, HexColor
    except ImportError as exc:
        raise ImportError("reportlab이 필요합니다. pip install reportlab") from exc

    font_reg, font_bold = _ensure_fonts()

    A4_W, A4_H = 595.28, 841.89
    MARGIN = 40.0
    CONTENT_W = A4_W - 2 * MARGIN
    GRAY = HexColor("#C0C0C0")

    def _lbl(text: str, size: float = 9.0) -> Paragraph:
        return Paragraph(text, ParagraphStyle(
            "lbl", fontName=font_bold, fontSize=size,
            leading=size * 1.35, textColor=black,
        ))

    def _val(text: str, size: float = 8.5) -> Paragraph:
        return Paragraph(
            (text or "").replace("\n", "<br/>"),
            ParagraphStyle(
                "val", fontName=font_reg, fontSize=size,
                leading=size * 1.45, textColor=black, wordWrap="CJK",
            ),
        )

    LW = 55.0
    RW = CONTENT_W - LW

    # 1. 메타 테이블 (회의일시/부서/작성자/참석자)
    mc = [55.0, 145.0, 32.0, 75.0, 38.0, CONTENT_W - 55.0 - 145.0 - 32.0 - 75.0 - 38.0]
    meta = Table([
        [_lbl("회의일시"), _val(fields.datetime, 8),
         _lbl("부서"), _val(fields.dept, 8),
         _lbl("작성자"), _val(fields.author, 8)],
        [_lbl("참석자"), _val(fields.attendees, 8), "", "", "", ""],
    ], colWidths=mc, rowHeights=[20, 18])
    meta.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, black),
        ("LINEBELOW", (0, 0), (-1, 0), 0.4, GRAY),
        ("LINEBEFORE", (1, 0), (1, 0), 0.4, GRAY),
        ("LINEBEFORE", (2, 0), (2, 0), 0.4, GRAY),
        ("LINEBEFORE", (3, 0), (3, 0), 0.4, GRAY),
        ("LINEBEFORE", (4, 0), (4, 0), 0.4, GRAY),
        ("LINEBEFORE", (5, 0), (5, 0), 0.4, GRAY),
        ("SPAN", (1, 1), (5, 1)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))

    def _section(col_widths: list, rows: list, extra: list | None = None) -> Table:
        t = Table(rows, colWidths=col_widths)
        cmds = [
            ("LINEABOVE", (0, 0), (-1, 0), 0.75, black),
            ("LINEBELOW", (0, -1), (-1, -1), 0.4, GRAY),
            ("LINEBEFORE", (0, 0), (0, -1), 0.4, GRAY),
            ("LINEAFTER", (-1, 0), (-1, -1), 0.4, GRAY),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        if extra:
            cmds.extend(extra)
        t.setStyle(TableStyle(cmds))
        return t

    # 2. 회의안건
    agenda = _section([LW, RW], [[_lbl("회의안건"), _val(fields.agenda_items)]], extra=[
        ("LINEBEFORE", (1, 0), (1, -1), 0.4, GRAY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (1, 0), (1, -1), 40),
    ])

    # 3. 회의내용 (내용 / 비고)
    DISC_W = round(RW * 0.765)
    BIGO_W = RW - DISC_W
    content_tbl = Table([
        [_lbl("회의내용"), _lbl("내용", 8), _lbl("비고", 8)],
        ["", _val(fields.discussion_content), _val("")],
    ], colWidths=[LW, DISC_W, BIGO_W], rowHeights=[16, None])
    content_tbl.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), 0.75, black),
        ("LINEBELOW", (0, -1), (-1, -1), 0.4, GRAY),
        ("LINEBEFORE", (0, 0), (0, -1), 0.4, GRAY),
        ("LINEAFTER", (-1, 0), (-1, -1), 0.4, GRAY),
        ("LINEBEFORE", (1, 0), (1, -1), 0.4, GRAY),
        ("LINEBEFORE", (2, 0), (2, -1), 0.4, GRAY),
        ("LINEBELOW", (1, 0), (2, 0), 0.4, GRAY),
        ("SPAN", (0, 0), (0, 1)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("VALIGN", (0, 0), (0, 1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (1, 1), (2, -1), 50),
    ]))

    # 4. 결정사항 (내용 / 진행일정)
    DEC_W = round(RW * 0.695)
    SCHED_W = RW - DEC_W
    dec_lines = [r for r in fields.decision_rows if r.strip()]
    n_rows = max(4, len(dec_lines))
    dec_data = [[_lbl("결정사항"), _lbl("내용", 8), _lbl("진행일정", 8)]]
    for i in range(n_rows):
        dec_data.append(["", _val(dec_lines[i] if i < len(dec_lines) else ""), _val("")])
    n = len(dec_data) - 1
    dec_cmds = [
        ("LINEABOVE", (0, 0), (-1, 0), 0.75, black),
        ("LINEBELOW", (0, -1), (-1, -1), 0.4, GRAY),
        ("LINEBEFORE", (0, 0), (0, -1), 0.4, GRAY),
        ("LINEAFTER", (-1, 0), (-1, -1), 0.4, GRAY),
        ("LINEBEFORE", (1, 0), (1, -1), 0.4, GRAY),
        ("LINEBEFORE", (2, 0), (2, -1), 0.4, GRAY),
        ("LINEBELOW", (1, 0), (2, 0), 0.4, GRAY),
        ("SPAN", (0, 0), (0, n)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for r in range(1, n + 1):
        dec_cmds.append(("LINEBELOW", (1, r), (2, r), 0.4, GRAY))
    dec = Table(dec_data, colWidths=[LW, DEC_W, SCHED_W], rowHeights=[16] + [None] * n)
    dec.setStyle(TableStyle(dec_cmds))

    # 5. 특이사항
    notes = _section([LW, RW], [[_lbl("특이사항"), _val(fields.special_notes)]], extra=[
        ("LINEBEFORE", (1, 0), (1, -1), 0.4, GRAY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (1, 0), (1, -1), 60),
    ])

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=(A4_W, A4_H),
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
    )
    doc.build([
        Paragraph("회의록", ParagraphStyle(
            "title", fontName=font_bold, fontSize=24, leading=32, textColor=black,
        )),
        Spacer(1, 14),
        meta,
        Spacer(1, 8),
        agenda,
        Spacer(1, 8),
        content_tbl,
        Spacer(1, 8),
        dec,
        Spacer(1, 8),
        notes,
    ])
    buf.seek(0)
    return buf.read()
