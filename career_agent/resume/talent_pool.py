"""Durable, owner-scoped facts collected from the user's resume sessions."""

from __future__ import annotations

import re

from career_agent.resume.models import Resume


def _key(kind: str, value: str) -> str:
    return kind + ":" + re.sub(r"\s+", " ", value.strip()).casefold()


def add_fact(pool: dict, kind: str, value: str, session_id: str, source: str) -> bool:
    value = value.strip()
    if not value or len(value) > 1000:
        return False
    key = _key(kind, value)
    if key in pool.setdefault("deleted", []):
        return False
    facts = pool.setdefault("facts", {})
    item = facts.setdefault(key, {"kind": kind, "text": value, "sources": []})
    provenance = {"session_id": session_id, "source": source}
    if provenance not in item["sources"]:
        item["sources"].append(provenance)
        return True
    return False


def collect_resume(pool: dict, resume: Resume, session_id: str) -> None:
    for skill in resume.skills:
        add_fact(pool, "skill", skill.name, session_id, "resume")
    for collection in (resume.work_experiences, resume.internships,
                       resume.project_experiences, resume.campus_experiences):
        for entry in collection:
            if entry.description:
                add_fact(pool, "experience", entry.description, session_id, "resume")


def collect_user_message(pool: dict, message: str, session_id: str) -> None:
    if re.search(r"(?:JD|岗位要求|招聘要求|职位要求)", message, re.I):
        return
    for match in re.finditer(r"(?:我会|我擅长|我掌握|我熟悉|我用过|我的技能(?:是|有)?)\s*[:：]?\s*([^。；;\n]{2,100})", message):
        for value in re.split(r"[、，,和及/]", match.group(1)):
            add_fact(pool, "skill", value, session_id, "user_message")


def delete_fact(pool: dict, kind: str, value: str) -> bool:
    key = _key(kind, value)
    existed = pool.setdefault("facts", {}).pop(key, None) is not None
    if key not in pool.setdefault("deleted", []):
        pool["deleted"].append(key)
    return existed


def relevant_facts(pool: dict, jd: str, limit: int = 12) -> list[dict]:
    if not jd.strip():
        return []
    scored = []
    for item in pool.get("facts", {}).values():
        text = item["text"]
        tokens = re.findall(r"[A-Za-z0-9+#]{3,}|[\u4e00-\u9fff]{2,}", text)
        score = sum(len(token) for token in tokens if token.casefold() in jd.casefold())
        if score:
            scored.append((score, item))
    return [item for _, item in sorted(scored, key=lambda pair: pair[0], reverse=True)[:limit]]
