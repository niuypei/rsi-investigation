# F01 / F08：特性入口与代码 Walkthrough 计划

核查日期：2026-09-16。这是一份阅读路线，按“入口 → 具体案例 → 状态变化 → 更新产物 → 后续生效”组织。F01 前三轮的实现分析已完成，见 [F01 深入分析](OPENJIUWEN_F01_DEEP_DIVE.md)；已做有限评分函数与取消传播检查，未运行服务、模型或仓内 pytest。

代码基线：agent-core `13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff`；jiuwenswarm `f29c060cee90aef10e46b2a3646fe3628f60ea7c`。Swarm 固定的 core 依赖与此本地快照不同，跨仓路线表示静态调用映射，不代表该组合已联调通过。[依赖声明](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/pyproject.toml#L20)

## 1. 先收藏这些入口

| 特性 | 从使用方看入口 | 从核心实现看入口 | 首次阅读要找什么 |
|---|---|---|---|
| **F01：单 Harness 优化** | [RSI method 分发表](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/server/rsi/rsi_handlers.py#L27)：`rsi.task.create`、`rsi.training.start`、`rsi.harness.install` | [`SingleHarnessIterativeOptimizationOrchestrator.run`](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L181)；实际调度主干在 [`_run`](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L216) | 一个失败案例怎样最终变成新的插件文件和发布引用 |
| **F08：在线模型适配** | [在线示例 `_run`](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/examples/jiuwenrl_online/run_jiuwenswarm_online_rl.py#L189)：start Task → Agent → stop → reward → 可选 train | [服务装配 `build_app_from_config`](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/agent_evolving/agent_rl/online/service.py#L398)、[API 注册 `build_rl_service_app`](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/agent_evolving/agent_rl/online/service.py#L57)、[`TrainingRunner.start`](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/agent_evolving/agent_rl/online/training_runner.py#L473) | 一次交互怎样成为固定训练批中的样本，并关联父 LoRA 和新版本 |

F01 中的 `rsi.training.start` 启动 Harness 优化任务；F08 的 `/v1/rl/training/runs` 创建模型训练 Run。二者不是同一个训练入口。F08 的 AIGW 是外部模型网关，Swarm 的渠道 Gateway 是另一个组件；本轮只核查到 AIGW 的客户端和部署契约。[F01 启动](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/services.py#L458)、[F08 训练 API](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/agent_evolving/agent_rl/online/service.py#L190)、[AIGW 边界](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/docs/dev/online-rl-service-operations.md#L3)

## 2. F01：沿“报告缺字段 → 新增 schema_check”阅读

贯穿问题沿用 [F01 报告生成案例](OPENJIUWEN_F01_HARNESS_ITERATION.md)：Agent 写完报告便提交，遗漏必填字段；尝试新增“重读、校验、修复”Skill。销售数据与完整轨迹属于教学推演；下面的代码和测试说明真实机制，不将独立测试拼成同一次实验。

详细阅读已按组件衔接展开为：[请求与执行](OPENJIUWEN_F01_DEEP_DIVE.md?plain=1#L63)、[证据与评分](OPENJIUWEN_F01_DEEP_DIVE.md?plain=1#L333)、[诊断与文件修改](OPENJIUWEN_F01_DEEP_DIVE.md?plain=1#L425)、[验收与安装](OPENJIUWEN_F01_DEEP_DIVE.md?plain=1#L658)。每段给出调用方式、实际输入/返回值、文件交接与失败分支。

### 2.1 外部调用到引擎的最短路径

```text
Swarm AgentServer 进程内
  rsi.task.create → RsiTaskService.create：固定输入和 Harness 基线
  rsi.training.start → RsiTaskService.start：入队
    → RsiWorker._execute_task：异步任务
    → HarnessEngineAdapter.build_request / run：对象调用
    → HarnessProvider.run / _run：构造 core 请求与配置
    → SingleHarnessIterativeOptimizationOrchestrator.run / _run
        → 评测 → 分析 → 生成文件 → 复评/选择 → 发布

另一次显式调用
  rsi.harness.install → RsiHarnessInstaller.install
    → 本 AgentServer 内的 Agent 对象加载发布包 → 更新 active
```

这条图中的 Adapter、Provider、Worker 和编排器不是各自独立的服务进程；评测模型服务、任务工具产生的子进程另有边界。

| 站点 | 点击打开，按箭头读 | 本站只回答的问题 / 跟踪对象 |
|---|---|---|
| **A1 请求与排队** | [handler](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/server/rsi/rsi_handlers.py#L146) → [`RsiTaskService.create`](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/services.py#L124) / [`start`](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/services.py#L458) → [`RsiWorker._execute_task`](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/worker.py#L288) | 输入何时复制？start 做训练还是排队？跟踪 task_id、dataset、源 Harness 路径 |
| **A2 跨仓桥接与主循环** | [`HarnessEngineAdapter.build_request`](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/harness_adapter.py#L97) → [`HarnessProvider._run`](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/harness_provider.py#L203) → [`IterativeSingleHarnessRequest`](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L94) → [`_run`](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L216) | 如何形成 dataset_files、harness_refs_path、output_dir？区分 run、epoch、batch；先标出 evaluate/analyze/optimize/gate 的调用点 |
| **A3 真正执行任务与评分** | [`CaseRunner.execute`](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/case_runner.py#L66) → [`SingleHarnessExecutionBackend.execute`](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/case_backend.py#L108) → [Skill 投递](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/runtime_adapters.py#L237)；返回后看 [LLM Judge](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/judger/llm_as_judge.py#L160) | H0/H1 如何被 load_plugin？read/write 等工具从哪来？落盘产物、trace、score、passed 分别是什么？本例显式选择 llm_as_judge，默认方法另见配置 |
| **A4 失败如何变成修改要求** | [`EvaluationResultAnalyzer.analyze`](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluation_result_analyzer/analyzer.py#L2938) → [`DiagnosisAgentStrategy.analyze`](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluation_result_analyzer/analyzer.py#L2411) → [`compile_optimization_hypotheses`](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/member_optimizer/hypothesis.py#L25) | “缺 currency”如何归因为未校验？跟踪 evidence、target_ref、decision_contract、target_case_ids；哪些是模型假设，哪些由程序固定？ |
| **A5 改哪个文件，谁落盘** | [`MemberOptimizer.optimize`](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/member_optimizer/optimizer.py#L155) → [Planner.create_plan](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/member_optimizer/action_planner.py#L628) → [Executor.execute_action](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/member_optimizer/action_executor.py#L704) → [写文件](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/member_optimizer/action_executor.py#L868) → [Verifier.verify](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/member_optimizer/verification.py#L1126) | 跟踪 skill/add、target_path、file_writes、skills.yaml、candidate refs；不要把计划中的“成功”当成文件已合法或任务已改善 |
| **A6 接纳、发布与安装** | [`_candidate_gate`](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L1180) → [实际接纳条件](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L1374) → [epoch 筛选](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L761) → [`_ensure_final_publication`](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L3916) → [`RsiHarnessInstaller.install`](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/harness_activation.py#L583) | 目标改善→provisional→epoch retained/accepted→promotion_applied/best→published→active怎样衔接？为什么accepted不保证升级best？哪个包最终加载？ |

如果 A1/A2 想继续确认运行对象从哪来，再看 [`AgentWebSocketServer._get_rsi_handlers`](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/server/agent_ws_server.py#L10529)。第一次阅读无需从整个 AgentServer 顶部开始。

A6 的安装后半段按以下位置续读：[`_install_unlocked`](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/harness_activation.py#L708) → [`broadcast_rsi_harness_change`](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/server/runtime/agent_manager.py#L1506) → [Adapter 实际 load_plugin](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/server/runtime/agent_adapter/interface_deep.py#L7374)。再对照 [新 Agent 恢复 active](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/server/runtime/agent_adapter/interface_deep.py#L7271) 与 [新优化任务选择源 Harness](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/server/agent_ws_server.py#L10594)，区分“运行 Agent 用新版”和“下一次优化以新版为基线”。

### 2.2 配套测试：用来固定预期，不替代生产调用链

| 阅读位置 | 测试锚点 | 看哪几行最有用 |
|---|---|---|
| A3 | [空 H0 与 verify_patch 加载测试](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/tests/unit_tests/rsi/test_runtime_adapters.py#L24) | 两个包的文件、load_plugin 调用、SkillTool 返回；模型是替身且不求解任务 |
| A4 | [结构化报告诊断 → schema_check 计划](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/tests/unit_tests/rsi/test_analyzer_optimizer_handoff.py#L32) | 预设诊断、真实假设编译、计划约束绑定；直接对应本次贯穿案例的原型 |
| A5 | [完整 Skill 的一次生成与写入](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/tests/unit_tests/rsi/test_member_optimizer.py#L3824) | 替身模型返回 file_writes，真实执行器落盘并注册；正文生成结果是预设 |
| A6 | [keep/drop 整轮筛选测试](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/tests/unit_tests/rsi/test_single_harness_iterative.py#L2276) | 先看最终断言，再读两个替身和run调用；full_calls只计full，过滤后另有selected_full整集复评；这些是测试定义，本轮未执行 |

F01 读完要能填写这一行，不必先记住全部类名：

```text
task_id / case_id
→ source Harness + result/trace + score
→ issue + hypothesis
→ action + file_writes + candidate Harness
→ candidate gate + epoch best
→ published_harness_refs_path
→ installation_id + active.runtime_path
```

## 3. F08：沿“GOOD/BAD 四次反馈 → 一批训练 → 新 LoRA”阅读

贯穿负载使用仓内系统测试：两次 `TRAINING_GOOD` 各给 reward 1，两次 `TRAINING_BAD` 各给 reward 0。这是已有测试定义，本轮未运行。先用它理解样本和版本，细节解释见 [F08 专题](OPENJIUWEN_F08_ONLINE_MODEL_ADAPTATION.md)。

### 3.1 入口与当前断点

```text
调用方脚本 → AIGW（外部服务进程）
  → RL Service（core 提供的 FastAPI 进程）
      start Task / capture before-after / reward
      → CapturePipeline、TaskRegistry（对象）→ Redis（服务进程）
      → 显式 POST training/runs
      → TrainingRunner.start → asyncio Task 执行 _execute
          → 调用执行器 train(...)
              当前默认 PPO 工厂选中的对象没有此方法：这里中断

后续组件另外阅读，不能当作当前 PPO 已走通：
  PPO Ray 训练组件 / SFT 子进程
    → LoRARepository 发布文件
    → AIGWLoRAClient 激活请求 → 外部 AIGW / vLLM
```

| 站点 | 点击打开，按箭头读 | 本站只回答的问题 / 跟踪对象 |
|---|---|---|
| **B1 调用方与 API** | [示例 `_run`](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/examples/jiuwenrl_online/run_jiuwenswarm_online_rl.py#L189) → [start_task](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/agent_evolving/agent_rl/online/service.py#L123)、[reward_task](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/agent_evolving/agent_rl/online/service.py#L178)、[start_training_run](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/agent_evolving/agent_rl/online/service.py#L190) | 谁创建 Task、谁给 reward、谁触发训练？跟踪 session_id、rl_task_id；区分公开 AIGW 与 loopback Service |
| **B2 服务装配** | [`main`](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/agent_evolving/agent_rl/online/service.py#L524) → [`create_app`](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/agent_evolving/agent_rl/online/service.py#L506) → [`build_app_from_config`](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/agent_evolving/agent_rl/online/service.py#L398) | Pipeline、样本存储、执行器和 Runner 如何连接？特别看 PPO/SFT 存储分支及工厂选择 |
| **B3 从调用到训练样本** | [before/after 回调 API](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/agent_evolving/agent_rl/online/service.py#L214) → [`CapturePipeline.before`](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/agent_evolving/agent_rl/online/capture_pipeline.py#L73) / [`after`](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/agent_evolving/agent_rl/online/capture_pipeline.py#L110) → [`_build_sample`](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/agent_evolving/agent_rl/online/capture_pipeline.py#L252) → [`submit_reward`](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/agent_evolving/agent_rl/online/capture_pipeline.py#L170) | 找出 messages、prompt/response IDs、response_logprobs、policy_version、judge.score；理解一条 sample 不等于整个 Agent Task |
| **B4 固定批次与父版本** | [`TrainingRunRecord`](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/agent_evolving/agent_rl/online/training_runner.py#L94) → [`TrainingRunner.start`](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/agent_evolving/agent_rl/online/training_runner.py#L473) → [`claim`](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/agent_evolving/agent_rl/online/training_runner.py#L206) / [Redis 领取事务](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/agent_evolving/agent_rl/online/training_runner.py#L276) | parent 何时固定？哪些 sample_ids 被领取？policy_versions 计数为什么不等于“按 parent 过滤样本”？ |
| **B5 执行训练与接口断点** | [`TrainingRunner._execute`](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/agent_evolving/agent_rl/online/training_runner.py#L597) → [工厂 PPO 分支](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/agent_evolving/agent_rl/online/core/factory.py#L63) → [被选中的 PPOTrainingExecutor](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/agent_evolving/agent_rl/online/backends/rl/trainer.py#L23)；再对照 [另一同名类的 train](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/agent_evolving/agent_rl/online/scheduler/ppo_executor.py#L142) | 精确确认谁调用 train、实际对象有没有 train；对照类不是已经接通的生产路径。之后再读 [SFT.train](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/agent_evolving/agent_rl/online/backends/sft/trainer.py#L211)，检查 parent 是否被使用 |
| **B6 发布、激活与失败状态** | [`LoRARepository.publish`](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/agent_evolving/agent_rl/storage/lora_repo.py#L56) → [Runner 记录 trained / 激活](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/agent_evolving/agent_rl/online/training_runner.py#L627) → [`AIGWLoRAClient.activate`](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/agent_evolving/agent_rl/online/lora_client.py#L66)；补读 [`recover`](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/agent_evolving/agent_rl/online/training_runner.py#L575) | 本地 latest、run.status、网关 active 为什么是三个状态？训练失败、激活失败和重启分别保留什么？ |

B5 必须同时记下两个已经确认的限制：默认 PPO 服务装配有接口缺口；SFT 虽有 train 接口，却没有使用传入的 active parent LoRA，且使用独立样本队列。阅读到 Ray/veRL 实现时，要把“已有后端组件”与“当前生产入口能到达”分开。

### 3.2 配套测试与第二遍选读

| 用途 | 入口 | 阅读重点 |
|---|---|---|
| 看具体用户负载 | [GPU 系统测试的 train_and_measure](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/tests/system_tests/agent_evolving/agent_rl/online/real_training_harness.py#L550) | 四次 marker/reward、调用 training/runs、参数和概率检查、新 Task 策略；其 [测试开关](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/tests/system_tests/agent_evolving/agent_rl/online/test_jiuwenswarm_training_e2e.py#L10) 默认需显式启用 |
| 理解固定批次 | [test_start_claims_fixed_batch_and_reuses_active_run](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/tests/unit_tests/agent_evolving/agent_rl/online/test_training_runner.py#L204) | 谁被领取、再次 start 返回什么；使用测试替身 |
| 理解发布与激活分开 | [训练成功先标 trained](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/tests/unit_tests/agent_evolving/agent_rl/online/test_training_runner.py#L313)、[激活失败保留产物](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/tests/unit_tests/agent_evolving/agent_rl/online/test_training_runner.py#L433) | 先看断言，再回到 Runner 的状态转移；不能将它们当成真实 GPU 运行 |
| 理解另一 PPO 接口 | [parent → repository version 测试](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/tests/unit_tests/agent_evolving/agent_rl/online/test_ppo_executor.py#L63) | 先看 import：测的是 scheduler 中的同名类；train_batch 被替换，不证明生产工厂正确 |
| 第二遍进入训练算法 | [PPOBatchEngine](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/agent_evolving/agent_rl/online/backends/rl/ppo_engine.py#L122)、[token/logprob 转换](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/agent_evolving/agent_rl/rl_trainer/verl_converter.py#L112) | 在服务编排与数据身份读清后，再看 batch 张量、Ray 调用和导出；不把它画成绕过接口断点的已连通路径 |

F08 读完应能跟踪：

```text
session_id → rl_task_id + policy_lora_name
→ sample_id + tokens/logprobs + policy_version + reward
→ training_run_id + sample_ids + parent_lora_name/path
→ TrainingArtifact.lora_name/path + repository.latest
→ activation(expected_lora_name=parent) → AIGW.active
```

## 4. 我们按这六轮进行 Walkthrough

每轮围绕一个问题读代码，建议约 30–60 分钟；这是阅读节奏建议。顺序已排好，后面的细节等前一轮对象与状态明确后再展开。

| 轮次 | 范围与顺序 | 本轮具体问题 | 读完留下什么 |
|---|---|---|---|
| **1** | **F01 A1 → A2 → A3 的宿主执行部分** | 用户提交报告任务后，源 Harness 何时固定，哪个对象创建 Agent，read/write 工具如何出现？ | 一张从 API 到任务工具的调用表；标明进程、对象、协程和输入路径 |
| **2** | **F01 A3 评分 → A4 → A5** | report.json 缺字段，怎样得到 score/issue/hypothesis，怎样写成 schema_check/SKILL.md？ | 对齐一次“产物证据 → 诊断 → action → file_writes”的字段；明确教学推演与测试预设 |
| **3** | **F01 A6 与 keep/drop 测试** | 新 Skill 局部有效却在全量失败时怎样处理？published 与 active 如何区分？ | H0 → candidate → best → published → installed 的状态表及拒绝/回退条件 |
| **4** | **F08 B1 → B2 → B3** | GOOD/BAD 四次任务怎样留下 token、logprob、版本和 reward？ | 一条完整 sample 的字段来源表；画清 AIGW 与 RL Service 的边界 |
| **5** | **F08 B4 → B5 → B6** | 一批样本如何固定 parent、进入训练和激活？当前断在哪里？ | 批次、父版本、产物、激活的状态表；列清 PPO/SFT 实现差异和失败保留状态 |
| **6** | **F01 与 F08 对照** | 能否追溯“哪个 Harness + 哪个模型”产生某批样本，并联合验收/回滚？ | 基于已经读过的字段和调用点，列出已存在连接、未找到的连接、待设计接口 |

### 待办清单

- [x] 固定代码快照，定位两条特性主入口。
- [x] 将入口、关键函数、测试和状态字段串成可点击阅读路线。
- [x] 第 1 轮：F01 从用户请求到 Harness 执行；已完成静态深读与组件交接图。
- [x] 第 2 轮：F01 从失败证据到实际文件修改；已完成字段转换、文件差异与有限评分检查。
- [x] 第 3 轮：F01 验收、发布、安装与跨轮继承；已完成条件/状态/失败路径分析，未执行真实安装。
- [ ] 第 4 轮：F08 在线交互与训练样本。
- [ ] 第 5 轮：F08 训练执行、版本激活及断点。
- [ ] 第 6 轮：两条链的协同接口对照。

起步时同时打开四个位置即可：[F01 请求入口](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/server/rsi/rsi_handlers.py#L27)、[F01 主循环](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L216)、[F08 调用方示例](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/examples/jiuwenrl_online/run_jiuwenswarm_online_rl.py#L189)、[F08 服务装配](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/agent_evolving/agent_rl/online/service.py#L398)。第一轮从 F01 请求入口开始。
