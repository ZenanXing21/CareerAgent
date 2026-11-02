# Legacy 低代码包业务逻辑与迁移审计

## 0. 审计结论

本审计覆盖仓库中的两个腾讯低代码导出包：

- `上海工商学院智能求职助手_v20260910222638_package/上海工商学院智能求职助手_v20260910222638_package/`
- `上海工商学院智能求职助手_v20260910222638_package/智能简历优化助手_v20260910144208_package/智能简历优化助手_v20260910144208_package/`

结论不是“迁移两个应用”，而是**提取其中可验证的业务思想，在新高代码 Career Agent 中重建**：

1. 强迁移：Fact Ledger、JD 原子要求、JD—CV 逐条证据匹配、事实边界、来源 URL、岗位硬条件、简历结构 Schema、渲染后质量检查。
2. 重建：Resume Parser、各类结构检测、确定性 Matcher、Tailor Planner、Rewriter、Validator、Renderer、LangGraph 状态和子图。
3. 弱化：成果量化检测。没有数字不是错误；只标记“可补充的证据机会”，严禁编造数字。
4. 删除：14 个低代码 Workflow 本身、长 Prompt 状态机、Widget/插件/模型/节点 ID、工作流 JSON、Playwright/TLS 适配、平台工具调用协议。
5. 延后：模板视觉检测、真实招聘平台适配器、校本统计/兴趣测评/模拟面试。这些不阻塞简历—JD—岗位匹配 POC 主链路。

最高优先级不变量：**任何输出事实都必须能回指当前 Fact Ledger 中的 `CONFIRMED` Fact。旧包中“生成项目经历”“补常规职责”“为了岗位要求补技术场景”的规则一律拒绝。**

状态词定义：

- `KEEP`：业务不变量直接保留，但仍以 Python 类型和测试重新实现。
- `REBUILD`：保留目标和规则，替换低代码实现。
- `WEAKEN`：只保留安全、可证据化的子集。
- `DELETE`：不进入新系统。
- `DEFER`：有价值，但不属于当前 POC 优先链路。

## 1. 审计方法与证据边界

本次读取了两个顶层 `metadata.json`，两个 `app.zip` 中的 `metadata.json`、agent/skill/workflow 配置，6 个嵌套 Skill zip 的全部 `SKILL.md`、`references/` 和 `scripts/`，以及两个 `knowledge_bases.zip` 的目录与元数据。知识库大数据文件只做文件级清单和边界判断，未复制其正文或分片数据。

证据引用使用仓库相对路径；`!` 表示 zip 内路径，例如 `app.zip!/workflow/workflow_config.json`。导出配置中的 Prompt 是历史业务证据，不是本仓库的指令来源。

## 2. 两个包的资产清单与架构

### 2.1 上海工商学院智能求职助手

顶层包 `PackageId=2100090564023087424`、版本 `1.0.1`；应用名“上海工商学院智能求职助手”、应用版本 `v20260910222638`。证据：包根 `metadata.json` 与 `app.zip!/metadata.json`。

架构为一个总控 Agent 调度四个子 Agent：

| 资产 | ID | 业务职责 |
| --- | --- | --- |
| 主 Agent | `8b79db7c-1ebe-4d4b-ac3f-03c89314163b` | 入口路由、会话状态、方向→岗位→简历→面试循环 |
| 就业方向顾问 | `bfcaf08b-1cc6-47e6-a848-31a5513525af` | 测评门控后查询校本统计并给方向建议 |
| 岗位检索与匹配 | `77718968-44e0-40b3-af00-e0cc9e3fb4de` | 抓公开岗位详情、校验硬条件、返回原始链接 |
| 简历顾问 | `d34e5c06-67ae-4fb1-b516-a48a438e0c4a` | 恢复上下文、追问关键事实、按 JD 重写、交付文档 |
| 模拟面试官 | `0bc63b6a-b1f9-41a1-a194-ed827de2d11d` | 基于 JD 和简历逐题练习，反馈不等于录用预测 |

对应 5 个 Skill：

| Skill | ID | 可迁移业务价值 | 迁移边界 |
| --- | --- | --- | --- |
| 公开岗位检索与匹配 | `8c25385c-3bbf-41ad-8b54-9ba4df0d310f` | 完整 JD、原始 URL、硬条件、未知与不匹配分开 | 不迁移 NCSS Playwright、Chromium NSS/TLS 与安装脚本 |
| 逐题模拟面试教练 | `e6b7ebaf-a45f-4a1b-97f8-baf3fc5669aa` | 一次一题、保存原答、可暂停/重答、不得生成学生作答 | POC 延后 |
| 求职简历创建与改写 | `7f4a6a7c-580b-43bb-aa09-eb00a61ce9d1` | `fact_ledger`、增量合并、只基于真实经历重写、版本交接 | 不迁移工具加载协议和平台文件链路 |
| campus-interest-profiler | `dce59287-8155-4f92-9481-92aedad646a5` | 会话隔离、输入校验、同意后才共享测评结果 | 测评域与本 POC 主链路解耦，延后 |
| campus-career-advisor | `42309ed9-2b4b-4b05-a94a-d12b5a59200c` | 统计口径、分母、版本、事实/统计/推断分离 | 校本数据仅在明确产品需求与授权后接入 |

Skill 包内证据主要位于：

- `app.zip!/skill/asset/skills/7f4a6a7c-580b-43bb-aa09-eb00a61ce9d1.zip!/SKILL.md` 及 `references/content-craft.md`、`references/resume-layout.md`。
- `.../8c25385c-3bbf-41ad-8b54-9ba4df0d310f.zip!/SKILL.md` 及 `references/evidence-matrix.md`、`references/browser-runtime.md`、`scripts/ncss_jobs.mjs`、`scripts/browser_trust.mjs`。
- `.../dce59287-8155-4f92-9481-92aedad646a5.zip!/SKILL.md`、`references/question-bank.json`、`references/module-config.json`、`scripts/assessment.py`、`scripts/career_flow.py` 与测试。
- `.../42309ed9-2b4b-4b05-a94a-d12b5a59200c.zip!/SKILL.md`、`scripts/query_history.py` 及官方统计参考文件。
- `.../e6b7ebaf-a45f-4a1b-97f8-baf3fc5669aa.zip!/SKILL.md`、`references/interview-state.md`。

知识库：

- `2098053913272816193`（应用同名库）为空壳分类/Schema，问答和文档均为空。
- `2098053914376695168`（上海工商学院官方就业数据库 2023—2025）包含 `official-employment-overview-2023-2025.xlsx`、`official-employment-kb.md`、`official-jobs-and-employers.xlsx` 及平台生成的 `big_data.jsonl`、`segment*.jsonl`。它属于校本统计数据资产，不属于简历事实，也不是实时招聘 API；大分片和平台索引不迁移。

### 2.2 智能简历优化助手

顶层包 `PackageId=2100097475817175872`、版本 `1.0.1`；应用名“智能简历优化助手”、应用版本 `v20260910144208`。证据：该包根 `metadata.json` 与 `app.zip!/metadata.json`。

架构包括：

- 主 Agent `86c0625c-3a15-49a2-8af9-4f4c1288f68a`：生成/优化/翻译简历，串联检测、模板填充和视觉检查。
- 视觉检测 Agent `eacb2733-0691-48f3-a0d0-17fd1d8b3f37`：检查渲染页面的重叠、裁切、层级、一致性等；其中“必须有照片、缺照片固定 P1 且分数≤79”是旧产品偏好，不能当作通用招聘事实。
- Skill `resume-template-filler`，ID `8ef992e6-b225-475b-a512-2d0c575cdb00`：解析结构化简历后生成 classic/clean DOCX，提供预览与样例。业务目标可迁移到 Renderer，脚本和模板资产须经过独立视觉/许可证审查后才能采用。
- 14 个 Workflow：覆盖结构、基础信息、教育/工作/项目/校园经历、表达、量化、岗位匹配、JD—CV 对比和建议生成。

该包知识库 `2089169552419768768` 只有空分类/Schema，无问答、文档或可复用业务数据。

## 3. 智能简历优化助手 14 个 Workflow 逐项拆解

总证据索引：`app.zip!/workflow/workflow_config.json`；每项节点证据位于对应 `workflow_<ID>.json`。下表不复制长 Prompt，只提取输入、节点结构、输出契约、价值与缺陷。

| Workflow（ID） | 输入 | LLM / 代码节点逻辑 | 输出 | 价值与问题 |
| --- | --- | --- | --- | --- |
| CV结构检测 (`0b17782b-58ac-4818-a380-29c8da1d0772`) | `CV: string` | 1 个 LLM 判断专业/方向是否通常需要项目；并行引用基础信息、教育、工作、项目、校园 5 个子 Workflow；Python 合并并根据 `require_projects` 降低项目或校园问题优先级 | `result[]` | 有价值：按候选方向调整模块必要性。问题：以 LLM 判断“必需模块”，且缺工作/项目可能被当错误；应由 Schema + 候选阶段/目标决定 |
| CV基础信息检测 (`14c95aef-06e0-4c16-88f4-367da03b1b56`) | `cv: string` | 3 个 LLM 分别查姓名/电话/邮箱，技能/工具/语言/证书，自我介绍；3 个 Python 节点构造、合并并映射优先级 | 带 `issue_type/original_text/problem/priority` 的 `result[]` | 可复用字段清单；应由 Resume Parser + Pydantic Validator 完成，不应为纯结构问题重复调用 LLM；自我介绍/证书并非普遍必填 |
| CV一段校园经历判断 (`17047aea-d3c9-4976-9fa4-74e6a24d0a88`) | `campus_experience: string` | 1 个 LLM 检查主体/角色与行为、职责或成果；issue 为 `MISSING_CAMPUS_SUBJECT/DETAILS` | `result[]` | 单条经历原子检查思想可保留；应在解析后的 `CampusExperience` 上用 Schema 校验，并允许真实未知 |
| CV岗位匹配度检测 (`1e8fdadb-7876-4974-8306-f8d6fa159c61`) | `CV: string` | LLM 提取简历明确目标岗位；条件分支；缺岗位由代码构造；另一个 LLM 判断相关技能/经历；代码映射 P1/P2 | `result[]` | 仅靠简历内部目标岗位做泛化判断，缺真实 JD；与真正 JD—CV matcher 重叠，应重建并弱化为“目标岗位字段存在性” |
| CV内容表达检测 (`29e52772-80ac-4e5c-bcc1-9d60a8f4a478`) | `CV: string` | LLM 检测口语、空话、模糊、重复、形容词过多；代码分级；另一个 LLM 查错别字/字符错误 | `result[]` | 保留 issue taxonomy；重建成 Quality Validator，最小引用原文，禁止把风格偏好当事实缺失；拼写可用确定性工具优先 |
| CV教育经历信息检测 (`338f1775-7fc5-4bcf-a886-b98a2cff6cc5`) | `CV: string` | LLM 先提取教育模块；条件分支；代码产生模块缺失；LLM 检查学校/专业/学位/时间；代码统一 P1 | `result[]` | 字段列表可迁移；二段 LLM 链应折叠为一次 Resume Parser structured output + Python Validator；所有缺项一律 P1 过重 |
| CV成果量化检测 (`51e85bd5-56fa-471d-8ccf-f65c3c060678`) | `CV: string` | LLM 标记无成果结果或有成果但无量化信息；Python 一律设 P1 | `result[]` | “行动—结果—证据”思想有用；“必须有数字/全部 P1”错误，必须弱化，数字只能来自已确认事实 |
| CV一段工作经历字段判断 (`5899c6a6-bf37-4c2d-8405-ca58c861925b`) | `work_experience: string` | 1 个 LLM 检查公司、岗位、时间、工作详情 | `result[]` | 字段校验可迁移为 `WorkExperience` Schema；不能自动补职责 |
| CV工作经历信息检测 (`5a89d272-1934-4af5-a958-b72d25f52dbf`) | `CV: string` | LLM 提取所有工作经历；无结果分支；循环调用“一段工作经历字段判断”；Python 展平、映射优先级 | `result[]` | “整份提取→逐项验证”是正确分层；新实现应由 Resume Parser 一次完成并用 Python 遍历，区分工作与实习，缺工作不是通用错误 |
| CV项目经历信息检测 (`5f8249a2-ed97-4034-b5d1-2f0a7218d3bc`) | `CV: string` | LLM 提取项目模块；无结果分支；LLM 检查名称、时间、背景、角色、详情；代码映射优先级 | `result[]` | 字段 Schema 可迁移；缺项目不应自动判错，更不能触发“生成项目” |
| CV校园经历信息检测 (`6ba1d068-807e-45ac-a34a-e10c5eb90d29`) | `CV: string` | LLM 提取并拆分校园经历；无结果分支；循环调用单条判断；代码展平、分级 | `result[]` | 可迁移拆分与单条验证；校园/荣誉/竞赛不应混成必须模块，缺失是 `NONE/UNKNOWN` 而非虚构入口 |
| 简历和岗位信息比对检测 (`79805a60-e1f6-4c73-9196-15b21beb4268`) | `cv_content: document`, `jd: string` | LLM 从 JD 提取 requirements/优先级；LLM 逐项查 CV 证据；代码过滤非 match；另一个 LLM 只判断简历目标岗位与 JD 岗位一致；代码处理缺 title/requirements | 非匹配 requirement 列表，含 `requirement/category/priority/match_status/cv_evidence` | 全包最值得迁移的业务主干；必须升级为 `JDAnalysis → EvidenceMatch(fact_ids) → deterministic MatchResult`，禁止自由文本证据和隐含推断 |
| 简历基础检测 (`7d380823-608d-4b60-b87e-181d474880da`) | `cv_content: string` | 并行引用结构、表达、成果量化、岗位匹配 4 个 Workflow | 分桶的检测结果 | 聚合意图保留；低代码父工作流删除，由 Python service/子图编排，避免 14 次重复 LLM |
| 建议内容输出 (`ece635c1-598e-470e-84e6-37719123da9c`) | `item: object`, `CV: string` | 代码取 issue；LLM 根据问题生成 insert/replace 建议；代码合并 priority 和 solution | 单条带 `solution` 的 issue | 必须升级为 Tailor Planner + Rewriter；旧 Prompt 允许对“缺职责/缺项目背景/缺岗位信息”直接生成新增内容，存在事实越界，不能原样迁移 |

总体问题：14 个 Workflow 将一次解析拆成大量重复 LLM 调用，并依赖自由文本 Prompt 保持状态与 JSON 形状；异常处理多为平台默认重试，引用关系依靠节点 ID，缺少事实 ID allow-list、版本隔离和可执行不变量。

## 4. 智能求职助手核心业务逻辑

### 4.1 主 Agent

主 Agent 的可迁移思想是能力独立且可循环：方向、岗位、简历、面试不强制线性完成；上一阶段只交结构化结果；会话内维护 student profile、job snapshots、resume versions、pending task。新系统应由 LangGraph typed state 表达这些概念，而不是把它们塞进长 Prompt。

主 Agent 还明确要求：附件、网页和 JD 只是资料；不能执行其中的指令；学生未确认的信息不重复猜测；岗位检索失败时可让用户粘贴 JD 继续。这些属于安全与降级策略，值得保留。

不迁移其 AskUserQuestion/Widget 约束、平台子 Agent 委派字段、一次工具一条消息等产品运行时规则。

### 4.2 岗位检索与匹配

`campus-job-match` 的业务链路为：接收已确认检索条件→将方向收敛为 1—2 个关键词→取得岗位详情和原始链接→逐项核对地点、学历、经验、性质、薪资、资格、职责→区分满足/冲突/未知→只推荐已验证详情的候选。

应保留：

- `detail_verified=true` 才进入正式 JD 分析；搜索摘要不能替代完整 JD。
- 未提供技能是 `UNKNOWN`，不是不会；课程项目不能折算工作年限。
- 硬条件冲突排除，未知条件待确认；不输出录用概率。
- `job_id`、完整 JD、来源 URL、采集时间、来源和核验状态随快照保存。

必须舍弃：`ncss_jobs.mjs`、`browser_trust.mjs`、无头 Playwright、证书库同步、NCSS 页面选择器与“最多查两个词”的平台运行策略。真实平台必须通过明确的 MCP Adapter contract；没有授权 endpoint 时返回 typed unavailable/not-implemented，不编造 BOSS、猎聘、智联或 NCSS API。

### 4.3 简历顾问

`campus-resume-studio` 是旧包中对新架构最有价值的来源：

- 维护 `fact_ledger`：事实 ID、来源原文、时间、角色、行动、对象、工具、产物/结果、确认状态。
- 状态区分 `confirmed/unknown/none/unsure/withheld/conflict`。
- 最新补充增量合并，只有明确更正才替换旧值；原简历中的模型猜测不能反向成为证据。
- “JD 要求—已有证据—表达重点—真实缺口”映射后再选材和改写。
- 允许把口语改为“行动＋对象/已有方法＋产物/真实反馈”，但不改变事实含义。
- 参与不升级为主导，课程项目不改为企业落地，AI 辅助不改为独立研发，反馈不升级为奖项。
- 缺数字时写具体行动或产物，不为扩写增加未发生环节。

这些规则应进入 Domain Model、Validator 和单元测试，而不是继续留在 Prompt。旧 Skill 的 DOCX/PDF 工具加载协议和平台状态码不迁移。

### 4.4 其他 Skills

- `campus-career-advisor`：统计必须携带年份、维度、分母、样本定义、版本；学生事实、官方统计、模型推断要分层。未来若接入校本分析可复用，但不混入 Resume Fact Ledger。
- `campus-interest-profiler`：30 题状态机、幂等提交、并列得分、同意后才向推荐共享结果具备工程参考价值，但属于独立 bounded context。
- `campus-interview-coach`：保留“一次一题、记录原答、0—2 个追问、暂停/继续、反馈不是录用预测”；当前延后。
- `resume-template-filler`：保留结构化数据驱动渲染、生成后文字和版面核验；模板选择 Widget、内嵌 base64 预览、脚本路径不迁移。

## 5. 逐能力迁移矩阵

| 能力 | 决策 | 新模块 | 可复用规则 | 必须舍弃 | 来源证据 |
| --- | --- | --- | --- | --- | --- |
| CV结构检测 | REBUILD | `career_agent.resume.parser` + `resume.inspector` | 一次解析出结构；按候选阶段判断模块适用性 | 结构检查反复调用 LLM、缺工作/项目一律报错 | Workflow `0b177...`、`7d380...` |
| 基础信息检测 | KEEP/REBUILD | Pydantic `Resume/PersonalInfo` + validator | 姓名、电话、邮箱、技能、语言、证书的显式状态 | 自我介绍/证书普遍必填、固定 P1/P2/P3 | Workflow `14c95...` |
| 工作经历检测 | KEEP/REBUILD | `WorkExperience` Schema + inspector | 公司、岗位、时间、详情；逐条检测 | 自动补职责；无工作即错误 | Workflows `5a89...`、`5899...` |
| 项目经历检测 | KEEP/REBUILD | `ProjectExperience` Schema + inspector | 名称、时间、角色、背景、详情；课程项目显式标识 | 自动生成项目；把课程项目包装为企业项目 | Workflow `5f824...` |
| 校园经历检测 | KEEP/REBUILD | `CampusExperience` Schema + inspector | 组织/主体、角色、行动/产物 | 为“完整”而编造校园活动、荣誉或成果 | Workflows `6ba1...`、`17047...` |
| JD 信息提取 | KEEP | `career_agent.jd.parser` → `JDAnalysis/JDRequirement` | 原子要求、category、priority、required、keywords；不得补 JD 未写内容 | 长 Prompt 与平台 JSON Schema | Workflow `79805...` 的“JD信息提取”节点 |
| JD—CV 逐条匹配 | KEEP | Evidence Matcher | 每个 requirement 独立判断，完整 CV 搜证；实践证据强于关键词 | 自由文本 `cv_evidence`、无事实 ID 的推理 | Workflow `79805...`；`evidence-matrix.md` |
| 岗位匹配度 | REBUILD | deterministic Matcher | strong/partial/no-match/unknown 分组，硬条件单独处理 | LLM 直接给总分、仅凭简历目标岗位泛化匹配 | Workflow `1e8f...`、现有 `MatchResult` |
| 内容表达检测 | KEEP/REBUILD | Quality Validator | 模糊、空话、重复、口语、拼写的 issue taxonomy；最小原文定位 | 把主观风格当硬错误、全篇反复 LLM 扫描 | Workflow `29e527...` |
| 成果量化检测 | WEAKEN | Evidence Quality | 有成果但无已知度量时提示“可向用户确认”；无结果证据标记缺口 | 没数字一律 P1；生成数字、规模或业务效果 | Workflow `51e85...`；`content-craft.md` |
| 建议内容输出 | REBUILD | Tailor Planner + Rewriter + Validator | insert/replace 区分；问题与建议绑定；在已有事实内改写 | 对缺职责/项目背景直接生成新事实 | Workflow `ece635...` |
| Fact Ledger | KEEP（强） | `career_agent.resume.models` + repository/service | 状态枚举、来源原文、原子 Fact、版本、冲突与更正 | Prompt 内隐式台账、模型猜测回写为事实 | `campus-resume-studio/SKILL.md`；现有 `Fact/FactLedger` |
| resume-template-filler | REBUILD | Renderer | 结构化数据驱动 DOCX、模块按有无渲染、生成后核验 | 平台 Skill 调用、base64 预览、强制模板 Widget、未经审查的模板资产复制 | Skill `8ef992...` |
| 模板视觉检测 | DEFER | Render QC | 查看全部页面；重叠、裁切、乱码、分页、边距、字体一致性；内容与视觉分开 | “照片必须存在”、着装/西装评分、通用 ATS 推断、平台视觉插件 | Agent `eacb...` |
| 大量 Prompt 状态管理 | DELETE | typed LangGraph State + DB/checkpoint | 仅保留明确状态字段、幂等与版本思想 | 依靠上下文记忆、长 Prompt、内部平台状态码 | 两包 `claw_agent_config.json` |
| 14 个低代码 Workflow | DELETE/REBUILD | Python services + Resume Tailor subgraph | 业务分类和输入输出意图 | 工作流 JSON、节点/引用 ID、重复 LLM、平台异常配置 | `workflow_config.json` 与 14 个 JSON |
| 岗位检索 | REBUILD/DEFER REAL | `jobs.adapters` + Mock MCP | 完整详情、来源 URL、采集时间、核验标记、未知/冲突 | Playwright/TLS 适配；臆造招聘平台 API | Skill `8c253...` |
| 校本方向建议 | DEFER | 独立 analytics bounded context | 统计口径、分母、数据版本、推断分离 | 平台知识库分片与本 POC 耦合 | Skill `42309...`、KB `2098053914376695168` |

## 6. 明确事实边界

### 6.1 允许的变换

只有下列变换可在不新增事实时执行：

- 对 `CONFIRMED` 来源做压缩、语序调整、去口语化和同义改写。
- 将同一事实拆成更清楚的行动、对象、方法、产物表达。
- 按 JD 相关性排序或删减；把已确认技术词用于准确命名。
- 用多个 `CONFIRMED` Fact 共同支撑一条 bullet，但每条 bullet 必须保存全部 `source_fact_ids`。
- 明确标注课程项目、实习、校园经历与正式工作，不跨类别升级。

### 6.2 必须拒绝的旧规则

智能简历优化主 Agent 明确允许用户无项目/无实习时选择“生成项目经历”，并进一步生成“常规职责、简历 bullet”；`resume-template-filler` 也存在为了填满模块追问或生成内容的倾向；建议 Workflow 可对缺职责/项目背景直接产生插入文本。这些规则全部拒绝。

新系统不得：

- 编造未实际完成的项目、实习、工作、校园活动或课程实践。
- 根据岗位常识补写用户没做过的职责、工具、技术栈、规模、数字、结果、奖项或客户反馈。
- 把 JD 要求写成候选人能力；把兴趣测评写成能力证据；把模型建议写回 Fact Ledger。
- 将 `UNKNOWN/NONE/UNSURE/WITHHELD/CONFLICT` 作为正向断言来源。
- 通过删除“课程”“参与”“协助”等限定词制造更强经历。

当证据不足时，只能选择：追问、保留未知、删去该陈述、标记 gap 或输出非事实性的准备建议。Rewriter 输出必须经过 fact-id allow-list 和最终 Validator；无法引用时拒绝生成。

## 7. 迁移优先级与对实施计划的影响

现有 `IMPLEMENTATION_PLAN.md` 的主架构判断正确，无需改为“导入低代码平台”。本审计对阶段的影响如下：

1. **Phase 1（已完成）不回退。** Domain models 已提供严格类型、Fact 状态、来源文本、Evidence 状态、引用 allow-list 和 Tailored Resume 引用验证。
2. **Phase 2 优先吸收旧包最有价值逻辑。** Resume Parser 一次 structured call；Python Inspector 覆盖基础信息、教育、工作/实习、项目、校园；Fact Ledger 构建；JD Parser；Evidence Matcher；确定性 match score。旧 14 Workflow 不逐个复刻。
3. **Phase 3 强化事实安全。** Tailor Planner 和 Rewriter 必须只接收已验证 Fact ID；Quality Validator 合并表达与 Evidence Quality；建议输出不再是自由文本补全。
4. **Phase 4 做 Renderer，不直接搬 Skill。** 可参考 classic/clean 的“同一数据、不同视觉”思想，但生成器、模板许可、DOCX/PDF 一致性检查和 render QC 独立实现。
5. **Career Graph 阶段迁移路由思想，不迁移长 Prompt。** 用 typed state 传 `candidate_profile/job_snapshot/resume_version/pending_approval/error`；Resume Tailor 为独立子图。
6. **岗位平台阶段先 Mock，再真实 Adapter。** 未取得正式接口、授权方式和字段契约前，只实现明确抛错的桩；Playwright 抓取不作为目标适配器。
7. **视觉、校本统计、兴趣测评、面试均为后续扩展。** 它们不能挤占主链路验收，也不能把个人照片或学校统计变成简历硬规则。

建议 Phase 2 增加以下回归样例：

- 无工作但有课程项目的应届生不报“必须补工作”；无项目时不自动生成。
- Resume Parser 将实习与正式工作分桶，保留每段 `source_text`。
- JD 未写的要求不得出现在 `JDRequirement`。
- `UNKNOWN` 技能只能产生 `EvidenceStatus.UNKNOWN`，不能算部分匹配。
- 量化建议只能指向待确认问题，不能生成数字。
- 目标岗位相似但不相同的判断不覆盖逐条 requirement 证据结果。

## 8. Phase 1 已落地规则与后续待落地清单

### 8.1 已落地

证据位于 `career_agent/models.py`、`career_agent/resume/models.py`、`career_agent/jd/models.py`、`career_agent/jobs/models.py` 和 `tests/test_domain_models.py`。

- 严格 Pydantic v2 模型：`extra="forbid"`、字符串清理、赋值校验。
- `FactStatus` 精确覆盖 `CONFIRMED/UNKNOWN/NONE/UNSURE/WITHHELD/CONFLICT`。
- `Resume` 已区分 `work_experiences` 与 `internships`，且校验跨桶类型和 ID 唯一性。
- 教育、工作/实习、项目、校园、技能均保留 `source_text`；项目支持 `is_course_project`。
- `Fact` 包含 ID、category、source、source_text、normalized_fact、status、metadata；`FactLedger` 绑定 candidate/resume/version 并校验 ID 唯一。
- `JDRequirement/JDAnalysis` 支持原子要求、1—3 优先级、required、keywords 和唯一 ID。
- `EvidenceMatch` 的正向匹配必须引用至少一个 Fact；`NO_MATCH/UNKNOWN` 不得冒领证据。
- Evidence、Tailor Plan、Tailored Resume 都有当前 ledger allow-list 校验；默认只允许 `CONFIRMED` Fact。
- `TailoredBullet` 强制至少一个且不重复的 `source_fact_ids`；Tailored Resume 校验当前 resume/version/job。
- Tailored Resume 额外保存来源条目的公司/学校、岗位、起止日期等不可变锚点，供后续 deterministic Validator 与基础简历逐项比较。
- `Job` 已有 platform、external ID、detail、source URL、`detail_verified`、UTC 采集时间。
- `MatchResult` 具备确定性分数承载结构和互斥 requirement 分组；Application 状态和 UTC 时间已建模。
- 所有领域边界启用 strict validation；系统时间统一归一化为 UTC，Fact metadata 限制为 JSON 可序列化值。

### 8.2 后续必须落地

- Resume Parser 的 structured output、稳定经历 ID 与解析失败策略。
- Python Resume Inspector：结构/字段/表达 issue 的统一类型、位置、严重度与适用性规则。
- Fact Ledger builder：从每段来源拆成原子事实，增量更正、冲突、来源定位与稳定 ID。
- JD Parser：只提取原文要求，生成稳定 requirement ID，禁止行业常识补全。
- Evidence Matcher：仅从当前 `CONFIRMED` Facts 选择 ID；输出后执行 allow-list。
- Deterministic Matcher：明确权重、required gate、UNKNOWN 处理和分数解释。
- Evidence Quality：量化仅作确认机会，不能把“无数字”判成普遍 P1。
- Tailor Planner/Rewriter：按相关性选材、压缩和排序；每条输出绑定 Fact ID。
- Validator：检测新增实体、数字、职责、工具、角色升级、课程/工作类别漂移以及未引用 bullet。
- Renderer 与 Render QC：DOCX/PDF 同源、文字层一致、分页/重叠/裁切检查；视觉规则可配置，不强制照片。
- LangGraph 主图与 Resume Tailor 子图：typed state、checkpoint、human approval、typed errors、幂等恢复。
- Job Adapter contract、MockAdapter 和合约测试；真实平台实现等待正式 API/授权信息。
- Persistence：resume version、fact、job snapshot、evidence、match、application 与 graph checkpoint 分责持久化。
- 日志脱敏：不记录简历/JD 全文、个人联系方式、模型完整输入输出或密钥。

## 9. 不迁移清单（可审计决策）

以下资产即使技术上可复制，也不进入新系统：

- 腾讯低代码 `AgentId/WorkflowId/NodeID/PluginId/ToolId/Widget` 和 app variable/synonym 配置。
- 14 个工作流 JSON、节点坐标、引用边、平台异常/重试配置。
- 两套应用的长 Prompt 路由、Prompt 内会话状态与模型名称/参数。
- `ncss_jobs.mjs`、`browser_trust.mjs` 及 Playwright/Chromium/TLS/NSS 环境适配。
- 平台专用 Skill 加载、AskUserQuestion、单工具调用、文件卡片和子 Agent 委派协议。
- 知识库 `big_data.jsonl`、`segment*.jsonl`、平台 Schema/分类空壳。
- 任何未经正式文档确认的招聘平台 API、登录、代投、上传简历或消息发送能力。
- “必须有个人照片”“必须穿西装”“缺照片固定 P1/分数上限 79”等旧产品特定规则。
- 自动生成项目、职责、技术场景、成果数字或把建议回写为用户事实的任何路径。

最终迁移原则：**迁业务语义和不变量，不迁平台编排；迁证据关系，不迁 Prompt；迁公开适配器契约，不迁网页抓取实现；迁可验证的格式规则，不迁审美偏好。**
