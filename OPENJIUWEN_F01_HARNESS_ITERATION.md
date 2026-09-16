# F01：一个“生成结构化报告”的 Harness，具体怎样演进

核查日期：2026-09-15；agent-core 基线 `13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff`。本文只讲同一个 Harness、同一个失败及其修复。各组件的完整定位另见[代码与测试参考](OPENJIUWEN_F01_CODE_REFERENCE.md)。

代码阅读顺序见 [F01 / F08 特性入口与 Walkthrough 计划](OPENJIUWEN_F01_F08_CODE_WALKTHROUGH.md)。2026-09-16 已补充 [组件衔接与源码深入分析](OPENJIUWEN_F01_DEEP_DIVE.md)，并据此收紧本文的角色、接纳及安装表述。

**案例性质：基于项目真实机制的教学推演，不是一次已完成的运行报告。** 项目测试确实给出“生成结构化报告时遗漏字段，把写文件成功误当成校验通过 → 增加 schema_check Skill”的诊断与计划交接。下面的销售数据、工具调用轨迹、评分条目和 Skill 正文，是为解释这一机制补全的示例；没有把它们当作项目实测结果。[案例原型](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/tests/unit_tests/rsi/test_analyzer_optimizer_handoff.py#L32)

## 1. 先确定这个 Harness 要干什么、有哪些工具

任务是：

> 读取 orders.json，汇总 amounts，生成 report.json。结果必须满足 report_schema.json：包含数值 total 和字符串 currency；currency 从输入读取。

为便于阅读，用 `/case` 代表本次任务的独立工作目录，`/harness/H0` 代表旧插件包；它们是示意路径。公开给任务 Agent 的两个输入如下：

```json
// /case/orders.json
{"currency":"CNY","amounts":[10,20]}
```

```json
// /case/report_schema.json
{
  "type":"object",
  "required":["total","currency"],
  "properties":{
    "total":{"type":"number"},
    "currency":{"type":"string"}
  }
}
```

期望交付的文件内容为 `{"total":30,"currency":"CNY"}`。上述文件标题行是展示注释，不属于实际 JSON 内容。

H0 采用 F01 默认原生宿主：一个 DeepAgent 对象、一个模型、文件/命令工具，以及基础 Rails。插件包暂时没有 schema_check Skill。它已经能读写文件，只是尚未加入本例的“提交前重读校验”规程。

| 本例会用到的 Tool | 精确名称和参数 | 谁调用、做什么 |
|---|---|---|
| 读文件 | `read_file({"file_path":"绝对路径"})` | 任务模型读取输入、schema 和实际产物 |
| 写新文件 | `write_file({"file_path":"绝对路径","content":"完整文件内容"})` | 任务模型生成报告 |
| 修改已有文件 | `edit_file({"file_path":"绝对路径","old_string":"旧片段","new_string":"新片段"})` | 任务模型补齐发现的缺失字段；修改前须读取已有文件 |
| 执行校验 | `bash({"command":"命令","workdir":"/case","timeout":30})` | 任务模型调用 Python 做确定性检查 |
| 读取选中的 Skill | `SkillTool.invoke({"skill_name":"schema_check","relative_file_path":"SKILL.md"})` | H1 任务开始时由 RSI Rail 内部调用，读取新规程 |

这些是项目实际提供的工具和参数。普通非容器 F01 宿主由 `RSISysOperationRail` 注册前四类；Skill 由另一条 Rail 管理。它们是宿主进程内的对象；bash 执行的命令可产生子进程，模型通过配置的外部服务调用。[工具注册](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/runtime_adapters.py#L73)、[文件工具参数](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/harness/prompts/tools/filesystem.py#L249)、[bash 参数](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/harness/prompts/tools/bash.py#L285)、[宿主装配](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/case_backend.py#L173)

## 2. H0 第一次执行：工具都成功了，任务却失败了

假设第一次轨迹如下。表中的“文件内容”是工具读取或写入的业务内容，省略 ToolOutput 包装和读取时附加的行号。

| 步骤 | 发起者与操作 | 看到或产生的内容 |
|---|---|---|
| 1 | 任务模型调用 `read_file`，读 `/case/orders.json` | amounts 为 10、20；currency 为 CNY |
| 2 | 任务模型调用 `read_file`，读 `/case/report_schema.json` | 必须同时有 total、currency |
| 3 | 任务模型计算后调用 `write_file` | 实际写入 `/case/report.json`：`{"total":30}` |
| 4 | write_file 返回写入成功 | 只证明文件写入完成 |
| 5 | 任务模型直接结束 | 回答“报告已生成并检查完成” |

这里没有工具报错。失败出在**读过要求后仍漏写 currency，且提交前没有检查落盘文件**。H0 的内层循环可以在模型不再要求工具调用时结束；文件写入成功不会自动触发 schema 业务校验。[ReAct 执行循环](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/core/single_agent/agents/react_agent.py#L2740)、[write_file 返回内容](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/harness/tools/filesystem.py#L1401)

这个失败对应项目测试明确描述的机制：`a successful write is not schema conformance`。但上述五步轨迹是本文推演，项目没有提供这次销售报告任务的真实轨迹。[原测试的失败机制与决策契约](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/tests/unit_tests/rsi/test_analyzer_optimizer_handoff.py#L32)

## 3. 评分器怎样判断 H0 失败

为本例显式选择项目的 `llm_as_judge` 评分方式，并定义两个等权检查项：

| 评分项 | 本次观察 | 项分 |
|---|---|---:|
| 报告能按 schema 交付：total/currency 齐全且类型正确 | 缺 currency | 0 |
| total 等于输入 amounts 的和 | 30 = 10 + 20 | 1 |

Judge 有自己的只读工具，包括 `read_file`、`list_dir`、`glob`、`grep`。它读取评测工作区里的实际产物和评分依据，检查缺失字段；不能只采信任务模型说“已检查”。项目有独立测试验证 Judge 读取真实产物而非信任完成声明。[Judge 工具装配](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/judger/judge_runtime.py#L26)、[读取产物测试](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/tests/system_tests/rsi/test_evaluator_agent_live.py#L73)

若 Judge 按上述事实返回两项分 0、1，程序计算：

```text
连续分 = (0 + 1) / 2 = 0.5
默认通过阈值 = 0.8
passed = false
正式 case.score = 0
```

**模型给逐项判断及证据，Python 计算总分并应用阈值。** 这里 0.5 和 0 是示例按真实规则推导的值，不是运行测量值。评分结果保留缺失 currency 的说明、产物依据和连续分，供下一步分析使用。[计算规则](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/judger/scoring.py#L144)、[正式分与阈值](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/judger/llm_as_judge.py#L160)

## 4. 分析器怎样把“缺 currency”变成“改 Harness 的哪一处”

分析器收到这个案例的任务要求、结果文件、评分拆分、执行轨迹和 H0 的现有 Skill 信息。它可以在隔离证据工作区用读取/搜索工具核查：

1. 输入已经提供 currency，任务不是因缺少信息而失败。
2. 任务模型读过 schema，因此不是“没有读到文件”。
3. write_file 确实写出了缺字段的报告。
4. 轨迹中没有提交前重读或校验报告的操作。

基于这些证据，可提出一个待验证的修改假设：**给生成结构化产物的任务加上提交前重读、对照 schema、发现问题后修复的 Skill。** 一次失败还不能证明这是唯一根因；候选是否有效必须靠重跑判断。

项目的诊断交接测试已经包含下列契约。这里保留它的关键字段，用中文解释含义：[诊断和改进计划交接](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/tests/unit_tests/rsi/test_analyzer_optimizer_handoff.py#L32)

```yaml
target_ref: member_harness.solver.skill
failure_mode: unchecked_serialization
wrong_decision: 未重新打开产物就提交
required_action: 写完结构化产物后重新打开，逐字段对照声明的 schema
activation_phase: pre_submission
acceptance_observable: 重新打开的产物符合 schema
scope_boundary: 不修改无关字段
```

**分析器不重新给任务打分。** 它输出“为什么失败、建议在哪个表面改变什么行为”的假设。随后程序把假设与这个案例绑定，计算摘要，传给改进器，防止规划时悄悄把“必须重读校验”换成较弱目标。[诊断输入与运行](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluation_result_analyzer/analyzer.py#L509)、[诊断 Agent 的工具装配](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluation_result_analyzer/agent_runtime.py#L74)、[假设编译](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/member_optimizer/hypothesis.py#L25)

## 5. 改进器具体修改哪些文件

沿这个问题可构造如下教学动作。`skill/add` 和 `skills/schema_check/SKILL.md` 来自上述项目测试，测试的计划草稿也是预设，并非真实Planner模型输出。下面按Swarm默认生产入口使用`role=validation_harness`；前节诊断契约中的`solver`是原型测试的原值，同一次生产运行应使用refs中的实际角色，对应`member_harness.validation_harness.skill`。[计划草稿与约束绑定](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/tests/unit_tests/rsi/test_analyzer_optimizer_handoff.py#L115)、[生产默认角色](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/materializer.py#L182)

```yaml
action_id: add_check
role: validation_harness
action_group: skill
operation: add
target_path: skills/schema_check/SKILL.md
declared_write_paths:
  - skills/schema_check/SKILL.md
  - skills/skills.yaml
```

实际文件操作由 Executor 在 H0 的目录副本中完成：

```text
H0 插件包                       H1 候选插件包
harness_config.yaml             harness_config.yaml
                                skills/
                                  skills.yaml
                                  schema_check/
                                    SKILL.md
```

改进模型生成完整文件内容；执行器检查路径和格式后写入，再同步注册清单。为使本例可理解，下面给出一份**教学用候选正文**，并非项目某次生成的原始产物：

```markdown
---
name: schema_check
description: Validate newly generated structured files against their declared schema before submission.
---
# Structured Artifact Verification

## Decision Capsule
- 生成结构化文件后，提交前必须用 read_file 重新读取实际落盘文件。
- 按任务提供的 schema 检查必填字段、字段类型；按本次输入检查关键值。
- 发现缺失或错误时，用 edit_file 或 write_file 修复，再重新读取并验证。
- 可用 bash 执行确定性检查；未通过时不得声称已验证成功。
- write_file 成功只证明写入完成。字段和值必须来自当前任务，不能写死案例答案。

## Decision Rule
只有实际产物满足任务契约，才能报告验证通过。

## Procedure
1. 读取当前任务的输入与 schema。
2. 生成产物，重新读取产物，并逐项检查。
3. 修复发现的问题，重复检查；无法完成时明确报告失败。

## Verification
保存实际检查的内容或命令结果，使交付声明能追溯到落盘产物。
```

对应注册文件是：

```yaml
# skills/skills.yaml
skills:
  - skills/schema_check
```

这轮持久化的修改是 **SKILL.md 中的执行规程及其注册项**。报告中的 currency 由重跑任务时的 Agent 补齐；改进器产出的 H1 则能把同一规程提供给后续相关任务。

文件写入后，Verifier 检查 Skill 元数据、目录/注册关系和包的可加载性；如果格式或路径错误，则修文件再检查。它不会因此宣布销售报告已经生成正确，任务效果留给下一步。[完整文件写入](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/member_optimizer/action_executor.py#L868)、[清单同步](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/member_optimizer/plugin_manifest.py#L55)、[包检查](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/member_optimizer/verification.py#L1126)

## 6. 用 H1 重跑同一任务：新增规程在哪一步生效

候选评测创建使用 H1 的任务 Agent。任务开始时，`RSISkillUseRail` 内部调用 `ListSkillTool`，输入任务文字。**如果它选中 schema_check**，Rail 再调用：

```python
SkillTool.invoke({
    "skill_name": "schema_check",
    "relative_file_path": "SKILL.md"
})
```

随后 Rail 将上述 Decision Capsule 放进本次会话的活跃指令。这里的选择/读取是 Rail 发起的内部动作，不是要求求解模型必须自主发一个 list_skill 调用。是否选中和投递都有记录；选择失败不等于候选已经生效。[选择与读取](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/runtime_adapters.py#L237)、[活跃指令投递](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/runtime_adapters.py#L177)

现在看新增规程可能怎样改变同一个任务。为了突出检查环节，假设模型第一次写报告时仍遗漏 currency：

| 步骤 | H1 的具体操作 | 结果 |
|---|---|---|
| 1 | Rail 选中 schema_check，并读取 SKILL.md | “写完后重读校验”进入模型上下文 |
| 2 | `read_file` 读 orders.json 和 report_schema.json | 获得同一组输入和要求 |
| 3 | `write_file` 写 report.json | 初次仍为 `{"total":30}` |
| 4 | **新增：** `read_file({"file_path":"/case/report.json"})` | 看见实际文件缺 currency |
| 5 | **新增：** 对照 schema，决定修复 | 需要从本次输入取 CNY，补上必填字段 |
| 6 | **新增：** 调用下方 edit_file | 报告变为 `{"total":30,"currency":"CNY"}` |
| 7 | **新增：** 重新读取，并通过 bash 执行确定性检查 | 检查必填字段、类型、求和及币种 |
| 8 | 仅在检查通过后结束 | 提交实际满足要求的报告 |

第 6 步的具体工具参数是：

```python
edit_file({
    "file_path": "/case/report.json",
    "old_string": "\"total\":30",
    "new_string": "\"total\":30,\"currency\":\"CNY\""
})
```

第 7 步可以通过 bash 运行以下 Python 逻辑。它是**本例的任务内检查**，不等同于后续独立 Judge 评分；下面只针对已定义的两种字段类型，并非通用 JSON Schema 校验器：

```python
import json
from pathlib import Path

orders = json.loads(Path("/case/orders.json").read_text())
schema = json.loads(Path("/case/report_schema.json").read_text())
report = json.loads(Path("/case/report.json").read_text())

assert all(field in report for field in schema["required"])
assert type(report["total"]) in (int, float)
assert isinstance(report["currency"], str)
assert report["total"] == sum(orders["amounts"])
assert report["currency"] == orders["currency"]
print("report check passed")
```

**这个修改通过改变模型看到的执行规程来影响后续工具选择。它不是程序强制新增了一个必经的校验状态。** 模型仍可能忽略 Skill、选错工具或检查错误，所以需要实际轨迹和候选复评来验证；不能从这份教学轨迹推出系统已经成功。[Skill 投递实现](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/runtime_adapters.py#L177)

## 7. 怎样判定 H1 值得留下

如果 H1 实际交付了上述完整报告，且 Judge 依据产物把两项都评为 1，则同一规则得到：

| 对照 | H0 的示例结果 | H1 达到预期时 |
|---|---|---|
| report.json | total=30，缺 currency | total=30，currency=CNY |
| 连续分 | 0.5 | 1.0 |
| 正式 case.score | 0 | 1 |
| schema_check 投递证据 | 无此 Skill | 应有，并发生在本次任务起作用的阶段 |

这仍只是候选的目标案例验收。F01 的真实控制器还检查：

1. 原失败目标的正式分必须提高；没有执行错误或其他阻断证据。
2. 声明的新增 Skill 必须有对应的调用/投递证据，不能只在磁盘上存在。
3. epoch结束先用原数据集做full复评，逐候选判断目标是否通过、能力使用证据是否满足；被保留候选记accepted。若部分移除，则从epoch基线重组，再做selected_full整集复评。
4. 对最终selected整版另判断：正式均分不得降低，历史已通过案例不能丢失；满足才升级best，否则回退版本选择。候选accepted仍可能同时出现promotion_applied=false。
5. 结束时发布函数检查是否存在accepted gate，然后复制当前best；因此published不保证发布了本轮候选，也不单独证明比初始H0改善。

本例没有虚构其他案例的成绩，因此不能仅凭示例中的 0→1 宣布整版已验收。这里也没有独立未见测试集的泛化证明。[目标接纳](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L1374)、[整轮筛选](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L761)、[整版比较](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L3237)

发布之后，Swarm调用方另行请求`rsi.harness.install(task_id)`。安装器复制独立安装版本，先广播给本进程缓存Agent进行热加载，成功返回后再提交active；新Agent另外读取active，下一次优化任务又会把选中的源包冻结为私有baseline。这几步可能分别失败，不能只凭active存在证明每个实例已加载。若后续任务确实使用新Skill，即使amounts换成7、8，规程仍要求按当前输入重读校验，不会把30写成固定答案。[发布](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L3916)、[安装顺序](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/harness_activation.py#L804)、[新Agent恢复](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/server/runtime/agent_adapter/interface_deep.py#L7271)、[下一任务复制](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/materializer.py#L177)

## 8. 将这一例子的完整过程连起来

```text
同一个报告任务，使用 H0
  read_file 输入/schema → write_file → 直接结束
  实际产物缺 currency
        ↓
Judge：读取产物，给出缺字段证据；示例正式分 0
        ↓
Analyzer：核查已读要求但未重读产物，提出“提交前 schema 校验”的修改假设
        ↓
Planner：选择 skill/add，目标 skills/schema_check/SKILL.md
        ↓
Executor：复制 H0，写 SKILL.md，登记 skills.yaml → Verifier 检查候选包
        ↓
同一个报告任务，使用 H1
  Rail 投递新 Skill
  read_file 输入/schema → write_file → read_file 重读
  → edit_file 补字段 → bash 校验 → 检查通过后结束
        ↓
Judge 按相同规则重新评分 → 控制器检查目标改善与 Skill 使用证据
        ↓
full筛选候选 → 必要时重组并做selected_full → 全局best判定
        ↓
按条件复制best发布 → 显式安装：先热加载、后提交active
        ↓
后续Agent加载 / 下一优化任务冻结baseline，分别继承
```

在这次推演中，Harness 演进留下的是“以后怎样生成和检查结构化文件”的规程。任务 Agent 在重跑时用原有工具执行这份规程。模型权重没有因此训练；是否真的形成上述行为，需要一次真实执行来检验。

项目现有测试支持“该类诊断怎样进入 skill/add 计划”和相关组件行为，但本例的完整销售任务尚未运行。当前没有把它声明成真实演进成功记录；已有真实组件测试、历史作者说明与未覆盖的部分保留在[代码与测试参考](OPENJIUWEN_F01_CODE_REFERENCE.md)。
