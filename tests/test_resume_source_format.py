import base64
from io import BytesIO

from docx import Document

from career_agent.web.app import IntakeAttachment, _decode_attachment


def test_word_upload_keeps_headings_bullets_and_bold_source() -> None:
    document = Document()
    document.add_heading("Projects", level=1)
    paragraph = document.add_paragraph(style="List Bullet")
    paragraph.add_run("Built ")
    paragraph.add_run("RAG").bold = True
    paragraph.add_run(" search")
    output = BytesIO()
    document.save(output)
    attachment = IntakeAttachment(
        filename="resume.docx",
        data_url="data:application/vnd.openxmlformats-officedocument.wordprocessingml.document;base64,"
                 + base64.b64encode(output.getvalue()).decode(),
    )

    text, image = _decode_attachment(attachment)
    assert image is None
    assert text == "## Projects\n• Built **RAG** search"
