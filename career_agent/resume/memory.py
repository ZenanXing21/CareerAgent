"""Small durable preference layer and searchable conversation notes."""

import re


def remember(preferences: list[str], instruction: str) -> list[str]:
    language_request = re.search(r"(?:整个|整份|全篇|全部|简历).{0,12}(?:翻译成|改成|写成|变成|使用).{0,6}(?:英文|中文)|(?:英文|中文).{0,8}简历|translate (?:the )?(?:whole |entire )?resume|resume in english", instruction, re.I)
    if not language_request and not re.search(r"以后|始终|总是|默认|记住|prefer|always", instruction, re.I):
        return preferences
    note = instruction.strip()[:1000]
    # A newer preference about the same language or format supersedes the old one.
    topic = "language" if re.search(r"英文|中文|English|Chinese", note, re.I) else "format" if re.search(r"格式|编号|排版|format", note, re.I) else note[:30]
    kept = [item for item in preferences if not item.startswith(topic + ":")]
    return (kept + [topic + ":" + note])[-20:]


def resume_language(preferences: list[str], instruction: str) -> str | None:
    current = remember(preferences, instruction)
    language = next((item for item in reversed(current) if item.startswith("language:")), "")
    if re.search(r"中文|Chinese", language, re.I):
        return "zh"
    if re.search(r"英文|English", language, re.I):
        return "en"
    return None


def recall(preferences: list[str], history: list[dict[str, str]], instruction: str) -> list[dict[str, str]]:
    terms = set(re.findall(r"[A-Za-z]{3,}|[\u4e00-\u9fff]", instruction.lower()))
    relevant = [entry for entry in history[:-8] if entry.get("role") == "user" and
                len(terms.intersection(re.findall(r"[A-Za-z]{3,}|[\u4e00-\u9fff]", entry.get("content", "").lower()))) >= 2]
    context = []
    if preferences:
        context.append({"role": "system", "content": "Saved user preferences (latest request takes precedence):\n" + "\n".join(preferences)})
    context.extend(relevant[-4:])
    return context + history[-8:]
