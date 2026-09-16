# F01 代码深入分析：组件怎样衔接，Harness 怎样修改并生效

核查日期：2026-09-16。本文完成原 [F01/F08 walkthrough](../../OPENJIUWEN_F01_F08_CODE_WALKTHROUGH.md) 的 F01 前三轮：A1–A3 执行、A3–A5 评分与改写、A6 验收与安装。代码基线为 agent-core `13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff`、jiuwenswarm `f29c060cee90aef10e46b2a3646fe3628f60ea7c`；源码工作树保持不变。Swarm 声明的 core 依赖为另一个提交，本文的跨仓连接是静态源码映射，未联调这两个版本。[依赖声明](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/pyproject.toml#L20)

**F01 的控制主线在编排器：它拿当前 Harness 执行案例，接收评测引用，再调用分析器、假设编译器和改进器，最后自行决定候选筛选与发布。** 改进器生成的是插件文件；运行 Agent 是否采用它，还要经过单独的安装与加载。每个交接点在后文给出调用方法、输入/输出、文件路径和异常去向。[core 主循环](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L216)、[独立安装入口](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/server/rsi/rsi_handlers.py#L209)

本文区分三类依据：**源码控制流**、**仓内测试的预设与断言**、**本轮实际执行的有限局部检查**。未运行真实模型、AgentServer、安装操作或整条优化流程。没有同一次 run 的完整证据时，不把独立测试拼成一次成功演进记录。

## 1. 阅读导航与贯穿案例

<!-- NAVIGATION_TABLE -->

### 1.1 同一个例子，以及它的证据边界

仍沿用“生成结构化报告，遗漏 `currency`，尝试新增 `schema_check` Skill”的案例。**原型测试只有 `case_a: Create a structured report` 和预设的未校验字段诊断**；销售金额、报告文件、实际工具动作与新 Skill 正文是教学补充。本次还读取了其他独立测试来固定接口预期，它们各自的输入和模型替身会单独说明。[原型测试](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/tests/unit_tests/rsi/test_analyzer_optimizer_handoff.py#L32)、[原教学案例](../../OPENJIUWEN_F01_HARNESS_ITERATION.md)

以下是沿真实数据契约补全的**教学数据集结构**，本次没有提交给服务或创建运行任务：

```json
[
  {
    "case_id": "case_a",
    "input": "读取 orders.json 和 report_schema.json，汇总 amounts，生成 report.json；currency 从当前输入读取，提交前确认落盘报告满足 schema。",
    "assets": ["orders.json", "report_schema.json"],
    "reference": {
      "rubric": [
        "report.json 包含 total、currency，字段及类型满足 report_schema.json。",
        "total 等于 orders.json 中 amounts 的和。"
      ],
      "expected_artifacts": ["report.json"]
    }
  }
]
```

`orders.json` 教学值为 `{"currency":"CNY","amounts":[10,20]}`；schema 要求数值 total 与字符串 currency。H0 假定写出 `{"total":30}`；H1 若有效，应通过重读、校验、修复得到 `{"total":30,"currency":"CNY"}`。数据集的 assets 是相对路径列表，物化时复制；任务 Agent 只取得公共附件与 task input，Judge 另读 reference。`expected_artifacts` 决定要收集的产物，存在这个字段本身不会执行 JSON Schema 校验。[附件协议](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/data_loader/case_files.py#L31)、[公共附件投递](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/data_loader/case_files.py#L126)、[指定产物收集](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/case_runner.py#L358)

身份统一规则：本例走 Swarm 默认单包创建入口，Harness refs 的角色键为 `validation_harness`；原型单测的 `solver` 保留为测试原值。源码没有把前者自动改名为后者。后文展示原测试时会保留 solver；展示本例生产接口的教学计划时使用 validation_harness，不能把二者误接成同一次运行。[物化默认角色](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/materializer.py#L182)、[角色原样读取](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/member_optimizer/loader.py#L282)

### 1.2 先看全部组件交接，再展开每条边

| 阶段 | 调用者 → 接收者 | 最重要的交接物 |
|---|---|---|
| 固定输入 | Handlers → TaskService → Materializer/ModelResolver | task_id、私有数据集/Harness快照、三份模型配置、profile |
| 启动 | TaskService → Worker task_id队列 → 后台执行Task | CREATED→QUEUED→RUNNING；另有EngineEvent队列 |
| 进入core | Worker → HarnessEngineAdapter → HarnessProvider → Orchestrator | RsiTaskView→HarnessEngineRequest→IterativeSingleHarnessRequest；Provider加载profile |
| 执行与评分 | Orchestrator → TeamEvaluator → CaseRunner → Backend / Judger | refs路径→角色字典→DeepAgent；执行结果→产物/轨迹→JudgeResult→eval_ref路径 |
| 诊断与编译 | Orchestrator → Analyzer；随后调用假设编译函数 | eval_ref→issues/analysis_ref→optimization_hypotheses.yaml |
| 改写文件 | Orchestrator → MemberOptimizer → Planner / Executor / Verifier | 假设→plan→模型file_writes→动作副本/整合副本→candidate refs |
| 验收 | Orchestrator → 同一套Evaluator；读取分数及使用证据 | 局部gate→provisional→full筛选→必要时selected_full→best |
| 发布与回传 | Orchestrator复制best；Provider读state；Worker更新任务 | published_harness_refs_path、publication_status、EngineResult；事件另走队列 |
| 安装 | 另一次install请求 → Installer → AgentManager → facade → DeepAdapter | 发布包→独立安装副本→instance.load_plugin→active/history |
| 后续继承 | 新Agent初始化 / 新建优化Task分别读取active | 一个加载运行包；另一个重新冻结成任务私有baseline |

这张表的每条边都在第2–5章展开。最容易遗漏的是：Analyzer 和 Optimizer 大量返回**引用文件的路径**，由编排器读回；它们不是各自运行完后自行调用下一组件。Skill 的 `file_writes` 是模型响应数据，真正写磁盘的是 Executor 的 Python 代码。[分析后调用改进器](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L450)、[实际文件写入](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/member_optimizer/action_executor.py#L868)
