"""Apply layout requests without asking a model to regenerate the full resume JSON."""

import re

from career_agent.resume.editor import normalize_section_order

LABELS = {
    "summary": ("个人总结", "自我评价", "summary"),
    "education": ("教育经历", "教育背景", "education"),
    "work": ("工作经历", "工作经验", "work experience"),
    "internship": ("实习经历", "internship"),
    "experience": ("项目经历", "项目经验", "projects"),
    "campus": ("校园经历", "校园活动", "campus"),
    "skills": ("专业技能", "技术技能", "skills"),
}


def requested_section_removal(message: str) -> str | None:
    """Recognize an explicit request to remove a whole resume section."""
    target = r"(?<!教育)(?<!工作)(?<!实习)(?<!校园)(?<!项目)经历(?:这个|那一块|这一块|模块|栏目|部分)?|项目经历|项目经验"
    action = r"删掉|删除|全删|整个删|去掉|移除|不要|不保留"
    whole = rf"(?:{action}).{{0,14}}(?:{target})|(?:{target}).{{0,14}}(?:{action})"
    scope = r"整个|整块|全部|所有|全删|那一块|这一块|这个模块|模块|栏目|板块|整栏"
    return "experience" if re.search(whole, message) and re.search(scope, message) else None


def requested_format(message: str, current_order: list[str], current_template: str) -> tuple[list[str], str] | None:
    if not re.search(r"格式|排版|版式|模板|布局|顺序|排序|放前|放后|置顶|置底|layout|format", message, re.I):
        return None
    template = current_template
    if re.search(r"极简|简洁|简约|minimal", message, re.I):
        template = "minimal"
    elif re.search(r"经典|传统|规整|classic", message, re.I):
        template = "classic"
    elif re.search(r"现代|modern", message, re.I):
        template = "modern"
    positions = []
    for key, labels in LABELS.items():
        index = min((match.start() for label in labels if (match := re.search(re.escape(label), message, re.I))), default=None)
        if index is not None:
            positions.append((index, key))
    positions.sort()
    order = normalize_section_order(current_order)
    if len(positions) >= 2 and re.search(r"顺序|排序|依次|按照|按此", message):
        named = [key for _, key in positions]
        order = normalize_section_order(named + [key for key in order if key not in named])
    elif len(positions) == 1:
        key = positions[0][1]
        if re.search(r"放前|提前|置顶|最前|第一", message):
            order = normalize_section_order([key] + [item for item in order if item != key])
        elif re.search(r"放后|置底|最后", message):
            order = normalize_section_order([item for item in order if item != key] + [key])
    return order, template
