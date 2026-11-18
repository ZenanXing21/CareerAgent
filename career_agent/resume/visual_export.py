"""Export the browser preview with Chromium's print renderer."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import shutil
import subprocess
import tempfile

from docx import Document
from docx.shared import Inches, Pt


def _browser() -> str:
    for path in (
        shutil.which("chrome"), shutil.which("chromium"), shutil.which("msedge"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ):
        if path and Path(path).is_file():
            return str(path)
    raise RuntimeError("未找到 Chrome 或 Edge，无法生成与预览一致的下载文件")


def visual_pdf(preview_html: str, stylesheet: str) -> bytes:
    if len(preview_html) > 8_000_000 or "resume-paper" not in preview_html:
        raise ValueError("简历预览内容无效")
    with tempfile.TemporaryDirectory(prefix="resume-print-") as directory:
        folder = Path(directory)
        source = folder / "resume.html"
        target = folder / "resume.pdf"
        html = (
            '<!doctype html><html><head><meta charset="utf-8"><style>'
            + stylesheet
            + "\n@page{size:794px 1122px;margin:0}html,body{width:794px;margin:0;padding:0;background:#fff!important}"
              ".resume-paper{width:794px!important;max-width:none!important;min-height:0!important;margin:0!important;"
              "box-shadow:none!important;break-after:auto!important;print-color-adjust:exact;-webkit-print-color-adjust:exact}"
              ".resume-paper,.resume-paper *{font-family:'Noto Sans CJK SC','Microsoft YaHei',Arial,sans-serif!important}"
              ".resume-paper:not(.layout-sidebar) .entry-heading{display:flex!important}"
              ".resume-paper:not(.layout-banner):not(.layout-sidebar){padding:36px 46px 32px!important}"
              ".resume-paper.layout-banner .resume-paper-header{min-height:132px!important;padding:22px 44px 18px!important}"
              ".resume-paper.layout-banner .resume-sections,.resume-paper.layout-sidebar .resume-sections{padding:20px 44px 26px!important}"
              ".resume-paper .resume-sections{display:block!important}"
              ".resume-paper .editable-section{break-inside:auto!important;padding-top:0!important;padding-bottom:0!important;margin:0!important}"
              ".resume-paper .editable-section+.editable-section{margin-top:var(--resume-section-spacing,18px)!important}"
              ".resume-paper .resume-entry{break-inside:auto!important;margin-bottom:6px!important}"
              ".resume-paper .resume-section-title{break-after:avoid!important;margin-bottom:8px!important}"
              ".resume-paper .entry-heading{break-after:avoid!important}"
              ".resume-paper .entry-description{margin-top:6px!important}"
              ".resume-paper .resume-entry p{margin:0 0 5px!important}"
              ".resume-paper .entry-primary,.resume-paper .entry-identity h3{"
              "font-family:'Noto Sans CJK SC','Microsoft YaHei',Arial,sans-serif!important;"
              "font-weight:700!important;line-height:1.5!important}"
              ".resume-section-controls,.resume-entry-actions,.drag-hint,.section-drag-handle{display:none!important}"
              "[contenteditable]{outline:0!important}"
            + '</style></head><body>' + preview_html + '</body></html>'
        )
        source.write_text(html, encoding="utf-8")
        subprocess.run([
            _browser(), "--headless=new", "--disable-gpu", "--disable-javascript",
            "--no-sandbox", "--disable-extensions", "--user-data-dir=" + str(folder / "profile"),
            "--no-pdf-header-footer", "--print-to-pdf=" + str(target), source.as_uri(),
        ], capture_output=True, timeout=60, check=True)
        if not target.exists():
            raise RuntimeError("浏览器未生成 PDF")
        return target.read_bytes()


def visual_docx(pdf_bytes: bytes) -> bytes:
    import pymupdf

    document = Document()
    section = document.sections[0]
    section.page_width = Inches(8.27)
    section.page_height = Inches(11.69)
    section.top_margin = section.bottom_margin = Inches(0)
    section.left_margin = section.right_margin = Inches(0)
    pages = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    for index, page in enumerate(pages):
        if index:
            document.add_page_break()
        picture = BytesIO(page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False).tobytes("png"))
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.space_before = paragraph.paragraph_format.space_after = Pt(0)
        paragraph.add_run().add_picture(picture, width=Inches(8.25))
    output = BytesIO()
    document.save(output)
    return output.getvalue()
