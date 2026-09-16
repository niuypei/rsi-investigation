# 模型与 Harness 协同演进：代码 Walkthrough 总索引

核查基线：2026-09-16。范围与 [MODEL_HARNESS_COEVOLUTION.md](../MODEL_HARNESS_COEVOLUTION.md) 的八项工作一致。本轮围绕同一任务串联执行、评价、归因、具体文件/字段修改、候选接纳、训练触发、数据构建、参数更新与下一轮反馈。每份正文都回答 Harness 更新和模型更新之间的双向触发关系。代码入口放在对应动作旁，十项要求的覆盖位置见[核查表](REWRITE_COVERAGE.md)。

**前轮已取得六项工作的官方公开源码；本轮复用这些提交，没有重新克隆。**本轮重新访问 Co-Harness、HASE 论文，并按标题/作者检索代码，仍未找到可确认归属的官方仓库；两份文档因此保留论文协议与实现缺口，未补造源码。

“有源码”与“当前公开入口完整实现论文共同更新”分开判断。已取得源码的项目也存在外部训练依赖、独立实验分支、手工命令衔接或接口缺口。每份文档都明确标注，没有用论文流程补成已运行的调用链。

## 1. 项目、仓库与逐项文档

| 工作 | 官方仓库 / 本地处理 | 代码 Walkthrough | 本次阅读重点 |
|---|---|---|---|
| HarnessX | [Darwin-Agent/HarnessX](https://github.com/Darwin-Agent/HarnessX)；复用 `HarnessX/` | [HARNESSX_CODE_WALKTHROUGH.md](HARNESSX_CODE_WALKTHROUGH.md) | GAIA 真实脚本、可修改配置与 processor；独立训练路径和未连接的协同调度 |
| SIA | [hexo-ai/sia](https://github.com/hexo-ai/sia)；复用 `sia/` | [SIA_CODE_WALKTHROUGH.md](SIA_CODE_WALKTHROUGH.md) | LawBench id=0、下一代 Python 修改、W+H 机制与公开训练模板的连接边界 |
| Continual Harness | [sethkarten/continual-harness](https://github.com/sethkarten/continual-harness)；复用 main 与已有实验 ref | [CONTINUAL_HARNESS_CODE_WALKTHROUGH.md](CONTINUAL_HARNESS_CODE_WALKTHROUGH.md) | 以实验分支串联游戏中编辑、窗口后评分/纠正/训练；main 差异单列 |
| HarnessForge | [mingju-c/HarnessForge](https://github.com/mingju-c/HarnessForge)；前轮克隆 `HarnessForge/` | [HARNESSFORGE_CODE_WALKTHROUGH.md](HARNESSFORGE_CODE_WALKTHROUGH.md) | ToolHop id=161、具体恢复控制逻辑、候选文件生成、轨迹清洗和独立 SFT |
| Co-Harness | 尚未找到可确认官方仓库 | [CO_HARNESS_CODE_WALKTHROUGH.md](CO_HARNESS_CODE_WALKTHROUGH.md) | 按执行、修改、训练及下一轮逐项登记实现缺口 |
| HASE | 尚未找到可确认官方仓库 | [HASE_CODE_WALKTHROUGH.md](HASE_CODE_WALKTHROUGH.md) | 附录片段与完整工程的区别、局部编辑/GRPO/阶段接纳待核查项 |
| ReSkill | [amazon-science/reskill](https://github.com/amazon-science/reskill)；前轮克隆 `reskill/`，含固定 veRL 子模块 | [RESKILL_CODE_WALKTHROUGH.md](RESKILL_CODE_WALKTHROUGH.md) | ScienceWorld 任务、同组技能版本抽样、奖励反馈与策略训练先后关系 |
| MetaClaw | [aiming-lab/MetaClaw](https://github.com/aiming-lab/MetaClaw)；前轮克隆 `MetaClaw/` | [METACLAW_CODE_WALKTHROUGH.md](METACLAW_CODE_WALKTHROUGH.md) | 代理请求、技能版本、数据隔离的实现缺口、云端训练接口、后续采样客户端 |

前三项的对应关系可由本地官方 [HarnessX README](https://github.com/Darwin-Agent/HarnessX/blob/bf5f199ee65034d55db0c536e582f1e7c8abf669/README.md#L44)、[SIA README](https://github.com/hexo-ai/sia/blob/7fd04d07bd2f47a110115674432b73622ebf7455/README.md#L12)、[Continual Harness README](https://github.com/sethkarten/continual-harness/blob/bbab97ad73e460b7cd7c08527d10ced30cc03fbe/README.md#L3) 核实。前轮新克隆的三个地址均由论文正文直接链接：[HarnessForge](https://arxiv.org/html/2606.01779v1)、[ReSkill](https://arxiv.org/html/2606.01619v2)、[MetaClaw](https://arxiv.org/html/2603.17187v1)。

## 2. 固定代码基线

| 本地目录 / 摘录来源 | 本次使用的 commit | 许可证核查 |
|---|---|---|
| `HarnessX/` | `bf5f199ee65034d55db0c536e582f1e7c8abf669` | [MIT](https://github.com/Darwin-Agent/HarnessX/blob/bf5f199ee65034d55db0c536e582f1e7c8abf669/LICENSE#L1) |
| `sia/` | `7fd04d07bd2f47a110115674432b73622ebf7455` | [MIT](https://github.com/hexo-ai/sia/blob/7fd04d07bd2f47a110115674432b73622ebf7455/LICENSE#L1) |
| `continual-harness/` main | `bbab97ad73e460b7cd7c08527d10ced30cc03fbe` | [MIT](https://github.com/sethkarten/continual-harness/blob/bbab97ad73e460b7cd7c08527d10ced30cc03fbe/LICENSE#L1) |
| Continual 实验 ref `feature/generalized-harness` | `2a74aa2bcf17d019844a8b86e3748ed566aede69` | 同仓实验快照；来源与文件清单见专题 |
| `HarnessForge/` | `05b3ecadb3c9a7a938f75129ea22b8f2b36cf289` | 根许可证未找到；内置 LlamaFactory 有自己的许可证 |
| `reskill/` | `a25e2534fcdef182f6684e4d24fa8a916e085ba5` | [Apache-2.0](https://github.com/amazon-science/reskill/blob/a25e2534fcdef182f6684e4d24fa8a916e085ba5/LICENSE#L1) |
| `reskill/verl/` 固定子模块 | `d62da4950573d7a4b7ef2362337952e7ab59e78d` | [Apache-2.0](https://github.com/volcengine/verl/blob/d62da4950573d7a4b7ef2362337952e7ab59e78d/LICENSE#L1) |
| `MetaClaw/` | `922caf3a1cd093fb316e95183a8acc8aa47b3b21` | [MIT](https://github.com/aiming-lab/MetaClaw/blob/922caf3a1cd093fb316e95183a8acc8aa47b3b21/LICENSE#L1) |

原有仓库保留当前工作树；HarnessX 原有架构分析文件保留。三个新主仓采用浅克隆，足够阅读当前快照，不代表取得全部历史。完整 Git 元数据记录在 [repository_manifest.json](repository_manifest.json)。

Continual 的实验源码来自**本地已经存在的 Git ref**，没有替换 main。为使引用能直接打开，将阅读所需文本导出到 `code-snapshots/continual-harness-2a74aa2/`，它是摘录目录，不是完整可运行工作树。Red 历史动作另从 main 自带 ZIP 提取，两个来源明确分开。

## 3. 如何阅读每份流程

先读每份文档的入口、案例与对象定义，再沿完整时序图进入正文。每次转场都说明调用者、触发条件、实参、等待点、返回值和下一分支；方法与具体行为旁附可点击代码行号。独立命令之间明确标出调用者和文件交接，论文流程图不作为代码部署图。

本文的“评价”是对任务结果或运行成本给分；“分析”是解释成败并提出修改；“接纳”是决定保留或撤销候选。三者可能使用不同数据和执行对象，文档不将它们合并成一个“评估器”。任务分数反映模型与 Harness 的共同作用，不能单凭该分数分离两者的贡献。

各文档按真实顺序组织：ReSkill 先处理技能再更新模型；MetaClaw 手动入口先训练再生成技能；Continual Harness 在游戏窗口内编辑、窗口后训练。没有的步骤直接标缺口，不用统一模板补造。

## 4. 横向比较：Harness 怎样被修改和接纳

以下比较由各行专题中的源码支持。SIA 和 HarnessX 的“每轮”指外层实验轮次，ReSkill 指采样后的一次训练步；Continual 的“窗口”指一段限定步数的游戏运行，不能混为同一计数。

| 项目与来源 | 修改触发与分析者 | 修改对象 | 验证与接纳 |
|---|---|---|---|
| [SIA](SIA_CODE_WALKTHROUGH.md) | 非最后一代就调用反馈角色，读取源码、评分和执行记录 | 下一代 Python 程序 | 下一代直接执行；最佳分数只用于总结 |
| [HarnessX](HARNESSX_CODE_WALKTHROUGH.md) | 非最后一轮调用 `MetaAgent` 分析轨迹 | 工具、事件处理组件、参数和提示文件 | 先检查可运行性，再在下一轮跑题并与历史最好结果比较 |
| [HarnessForge](HARNESSFORGE_CODE_WALKTHROUGH.md) | 调用者启动三阶段生成命令 | 候选 Python 包 | 独立代码检查、任务评测和质量/成本筛选 |
| [Continual Harness 实验分支](CONTINUAL_HARNESS_CODE_WALKTHROUGH.md) | 按游戏步数或按需工具调用 `HarnessEvolver` | 提示、子 Agent 配置、技能代码、记忆 | 逐项应用；局部技能回退依赖存在缺口的状态统计 |
| [ReSkill](RESKILL_CODE_WALKTHROUGH.md) | 经验量达标且无版本测试时，分析类生成技能操作 | 提示中的技能文本与触发规则 | 先检查触发率/长度，再在策略持续训练时比较新旧技能成功率 |
| [MetaClaw](METACLAW_CODE_WALKTHROUGH.md) | 会话条件或手动训练后的低成功率条件调用 `SkillEvolver` | 新增技能文档 | 解析去重后直接入库，没有独立性能接纳步骤 |
| [Co-Harness](CO_HARNESS_CODE_WALKTHROUGH.md)、[HASE](HASE_CODE_WALKTHROUGH.md) | 实现不明确 | 只有论文层面的描述 | 待官方源码核查 |

## 5. 横向比较：模型怎样更新并进入下一轮

SFT 是用输入和目标输出进行监督微调；GRPO 是利用同题多次采样的相对奖励进行策略更新。LoRA 是低秩适配参数，不是一种独立奖励算法。

| 项目与来源 | 训练触发、数据与算法 | 下一轮生效及缺口 |
|---|---|---|
| [SIA](SIA_CODE_WALKTHROUGH.md) | 论文实验先修改 Harness、停滞后训练；公开入口固定 focus 分支，weights 生成脚本实现任务、奖励和外部训练调用 | W+H 实验到本地入口的完整映射未定位；不能用 CLI 限制否定实验，也不能把模板当完整训练链 |
| [HarnessX](HARNESSX_CODE_WALKTHROUGH.md) | 独立 Slime/veRL 命令构建采样与奖励，配置 GRPO | GAIA 主循环未接入训练批、新模型产物和联合版本 |
| [HarnessForge](HARNESSFORGE_CODE_WALKTHROUGH.md) | 调用者整理成功轨迹为规划/动作标签，另配 SFT | 模型部署与下一轮选择由外部衔接；配对表不是权重加载器 |
| [Continual Harness 实验分支](CONTINUAL_HARNESS_CODE_WALKTHROUGH.md) | 窗口结束后评分，保留高分输出、纠正低分输出，再做 LoRA SFT | 重启进程加载；最终参数目录选择和跨窗口 Harness 继承存在缺口 |
| [ReSkill](RESKILL_CODE_WALKTHROUGH.md) | 每训练步在技能处理后，用已生成的新旧技能轨迹做 GRPO | 推理前同步新参数；拒绝技能不回滚模型；默认配置和恢复有缺口 |
| [MetaClaw](METACLAW_CODE_WALKTHROUGH.md) | 本例每 5 场景取已完成样本，按整批奖励归一化，调用云端 LoRA 更新 | 替换采样客户端；不是已确认的同题分组 GRPO，技能/训练数据严格隔离未保证 |
| [Co-Harness](CO_HARNESS_CODE_WALKTHROUGH.md)、[HASE](HASE_CODE_WALKTHROUGH.md) | 论文分别描述 SFT、GRPO；具体实现不明确 | 无法核实实际加载与循环 |

## 6. 证据与本轮检查

文档分别标注源码事实、仓内输入或测试、历史运行材料、条件推演和实际局部检查。真实题目加上真实代码只支持控制流解释，不自动组成真实改进日志。

前轮完成过 SIA 评分、HarnessForge 工具评分、ReSkill 技能文件/触发契约等局部检查。本轮将其余七篇按已确认的 SIA 整篇标准重写，并同步索引；复核关键调用与分支、检查引用和代码基线，没有重新运行上述功能检查，也没有运行模型或训练。最新文档检查见 [校验记录](evidence/document_validation.json)。

建议先读 ReSkill，理解已接通的技能/模型更新顺序；再读 MetaClaw 比较异步交互；其余项目按专题正文顺序阅读，并在外部调用或未实现连接处停止推断。

SIA 前轮补查执行过 8 组真实参数解析，本轮将其保留为辅助证据；正文改用 README 中的 W+H 任务 LawBench，补充参考程序、分类评分和具体代码修改位置。[SIA 正文](SIA_CODE_WALKTHROUGH.md)、[既有解析记录](evidence/sia_focus_parser.json)。

SIA 的 W+H 是 README 报告的组合实验设置；CLI 单值限制只描述当前公开入口。实验设置与入口之间的对应关系另见 [SIA 第 1、7–9 节](SIA_CODE_WALKTHROUGH.md)，不能用参数限制否定组合实验，也不能把人工衔接方案当作作者已确认的运行方式。

## 7. 协同触发关系的阅读结论

这八项工作不能统一描述成“Harness 改完便训练，模型训完便修改 Harness”。下表只概括各专题已核查的入口；研究主张和未定位连接以正文为准。

| 工作 | Harness 更新是否触发训练 | 新模型如何反馈到 Harness 修改 |
|---|---|---|
| SIA | 论文实验有先改 Harness 再训练的安排；公开分支之间的自动切换未定位 | 完整实验回接未定位；生成脚本能力不等于框架保证 |
| HarnessX | GAIA 候选检查后只换配置；训练命令独立 | GAIA 主循环未接收训练产物；实验映射待核实 |
| Continual Harness | 训练由窗口结束触发，不要求本窗口编辑成功 | 下一窗口模型产生新动作与轨迹；参数选择和 Harness 继承存在缺口 |
| HarnessForge | 候选筛选不调用训练；调用者连接数据处理与 SFT | 调用者部署新模型并重跑任务，再提供轨迹 |
| ReSkill | 模型每步照常训练；新技能通过后续采样影响训练数据 | 同步权重后继续在新旧技能下采样，结果进入比较与诊断 |
| MetaClaw | 技能新增不立即训练；本例由场景间隔触发 | 新客户端产生后续记录，再触发分析；训练后分析旧批次不算新模型复评 |
| Co-Harness / HASE | 只有论文协议，实际事件与调用关系不明确 | 新权重加载、再采样及候选接纳实现不明确 |

每项结论的类、方法与行号见对应专题，十项要求的检查位置见[核查表](REWRITE_COVERAGE.md)。

SIA 正文保留此前确认版本。其余七篇现已按全篇调用关系改写：五篇源码流程配时序图，Co-Harness/HASE 配标明论文层次的逻辑图。校验包括本地引用、行号、图分支结构、七个仓库的 commit/工作树及 Continual 实验摘录；未执行图形渲染或端到端训练。[本轮校验](evidence/other_projects_call_chain_validation.json)、[此前 SIA 校验](evidence/sia_call_chain_validation.json)。
