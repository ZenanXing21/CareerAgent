from io import BytesIO

from docx import Document

from career_agent import CandidateIntakeDraft, EducationDraft
from career_agent.resume.emphasis import emphasis_styles, matching_terms
from career_agent.resume.exporter import render_resume_docx


def test_jd_overlap_marks_only_existing_terms_and_word_runs() -> None:
    resume = CandidateIntakeDraft(candidate_id="emphasis-test", name="Test User",
        email="test@example.com", phone="13800000000",
        education=EducationDraft(school="Example University", major="Computer Science", degree="BSc"),
        skills=["Python", "RAG"]).build_resume()
    resume = resume.model_copy(update={"educations": [resume.educations[0].model_copy(
        update={"description": "Built RAG search with Python."})]})
    jd = "岗位要求：熟悉 Python 和 RAG，能够设计检索系统。" * 5
    terms = matching_terms(resume, jd)
    styles = emphasis_styles(resume, terms)
    assert "Python" in styles["educations.0.description"]["emphasis"]
    document = Document(BytesIO(render_resume_docx(resume, field_styles=styles)))
    paragraphs = [*document.paragraphs, *(p for table in document.tables for row in table.rows for cell in row.cells for p in cell.paragraphs)]
    paragraph = next(p for p in paragraphs if "Built RAG search with Python." in p.text)
    assert any(run.bold and "Python" in run.text for run in paragraph.runs)
    assert any(not run.bold and "Built" in run.text for run in paragraph.runs)
