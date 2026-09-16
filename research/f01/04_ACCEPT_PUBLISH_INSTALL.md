# F01 A6：候选验收、整轮选择、发布与安装

核查日期：2026-09-16。本文是源码与已有测试的静态核查；未运行项目 pytest、模型、服务或安装操作。基线沿用主 walkthrough：agent-core `13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff`，jiuwenswarm `f29c060cee90aef10e46b2a3646fe3628f60ea7c`。已读取适用的 [agent-core/AGENTS.md](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/AGENTS.md)。跨仓调用是这两个本地快照的静态映射，不代表依赖组合已联调。

这段链条必须拆成五个判定：**局部 gate 改善 → epoch 内候选保留 → 整版提升为 best → best 复制为 publication → 安装并更新 active/live 实例**。其中 `gate.accepted` 与 `checkpoint.promotion_applied` 是不同变量；发布复制的是 best，安装加载的是发布包的独立副本。

## 1. 调用边界与运行对象

| 相邻调用 | 实际衔接方式 | 传递的身份与结果 |
|---|---|---|
| `MemberOptimizer` 返回 → `_candidate_gate` | 同一 orchestrator 协程中 `await`，非新服务 | `optimized_harness_refs_path`、member 状态、从 plan 提取的 capabilities、source eval、analysis ref |
| gate → `_run` | 返回 dict，再由 `_run` 改成 provisional | `primary_gate_accepted` 保存初判；`current_refs` 暂转向候选 |
| `_run` → epoch `_evaluate` | `await` 对整个 `all_cases` 评测；可配置 full concurrency | `evaluations/eNNN/full/eval_ref.yaml`；必要时另有 `selected_full` |
| epoch → publication | 同步 Python 文件函数，不是发布服务或外部回调 | `state.best_harness_refs_path` → 独立发布副本及稳定 refs |
| `rsi.harness.install` → installer | 同步 handler 返回协程；`handle_async` 检测 awaitable 并 await | task_id；installer 内 `asyncio.Lock` 串行化安装/回退 |
| installer → AgentManager → facade → DeepAdapter → DeepAgent | 各层依次 await；包复制、hash、active 文件写入仍是同步文件操作 | `runtime_path`、`installation_id`、DeepAgent `LoadRecord` |

证据：[gate 调用与初判](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L570)、[全量评测入口](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L761)、[结束时发布](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L964)、[异步 handler](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/server/rsi/rsi_handlers.py#L104)、[安装 handler](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/server/rsi/rsi_handlers.py#L209)、[安装锁](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/harness_activation.py#L578)。

对象由 composition root 注入：`RsiServiceContext` 创建 `RsiHarnessInstaller(store, adapter_for_task, agent_manager, activation_store=...)`；AgentServer 随后通过 `context.bind_harness_installer(self._agent_manager)` 绑定本进程已有 manager。因此 install 面向该 manager 缓存的实例，不是集群范围广播。[Context 构造](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/context.py#L58)、[绑定方法](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/context.py#L141)、[AgentServer 装配](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/server/agent_ws_server.py#L10581)

## 2. 局部 gate：不是“平均分涨了就接纳”

### 2.1 输入与短路

`_candidate_gate` 先检查源 eval 是否有 `status=error` 案例；有则 `inconclusive`。member 状态必须为 `success` 或 `partial_success`；候选 refs 路径必须与本次修改前 refs 不同，否则直接 rejected。这里“不相同”比较的是 refs 路径，不是文件内容 hash。[短路条件](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L1209)

目标集合 `T` 来自 capabilities 的 target case IDs，与当前 batch case IDs 取交集；缺少目标时回落到 source 中未通过的案例，再必要时回落到 batch。候选评测只传目标案例的原始 case dict；source target score 从已有 source eval 提取。它没有在此重跑 H0，也不评测非目标案例。诊断中的 task acceptance contract 在 gate 中另外读取，未将诊断要求追加给求解任务。[目标集合](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L1230)、[原任务输入与评测](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L1258)

candidate 目标若 `status=skipped` 或 `metadata.infrastructure_skip=true`，返回 `inconclusive`，不是业务失败。[skip 条件](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L1278)、[skip 字段定义](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L2895)

### 2.2 可核对的公式

记 source/candidate 正式 case score 为 `s_i` / `c_i`；未找到该 case score 时此处 `.get(..., 0.0)` 按 0 比较。`F = T − passing(source)`，`δ = candidate_min_target_behavior_delta`，默认 `δ=0.0`。

```text
target_improved = F 非空
                  AND 对每个 i∈F，c_i > s_i + δ
                  AND 对每个 i∈T，c_i ≥ s_i

local accepted = candidate 无 status=error
                AND target_improved
                AND 没有缺失的 expected Tool 调用
                AND 没有缺失的 expected Skill 调用/投递
                AND 没有失败的 machine evidence
```

`>` 是严格大于。检查的是每一个失败目标，平均 target delta 只是记录值。native signal、native dimension delta 和 verifier 局部进展保留为诊断数据，不能替代正式 score 改善；所以 verifier 有进展而正式分未变，仍可 rejected，并进入局部修复分析。A6 本身没有固定的“0.8 通过阈值”：通过集合对 `llm_as_judge` 优先读取显式 passed；其他情形要求非 failed/error/skipped 且 score ≥ 1.0。Judge 的阈值属于 A3 评分协议。[δ 默认值](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/config/config.py#L170)、[逐目标公式](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L1374)、[native 诊断字段](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L1529)、[通过集合](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L3061)

machine evidence 专指每个 result 的 `evaluation.metadata.artifact_runtime_evidence.observations` 中 status 为 failed/error 的观察；不是任意 warning 都拒绝。若候选失败但没有 execution error，gate 还会 await Analyzer，传入 source/candidate verifier delta、patch excerpt、实际 capability 使用情况，并保存 `candidate_failure_analysis_ref`；这份分析供后续修复，不是重新打分。[machine evidence](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L3845)、[失败再分析](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L1486)

### 2.3 Skill “确实使用”的证据与时间窗口

| 证据 | gate 实际读取什么 | 不能推出什么 |
|---|---|---|
| Rail 自然任务起始投递 | `result.json → metadata.execution.skill_triggers[]` 中 `delivered is True` 与非空 `selected_skill_name` | 不证明模型执行了 Skill 正文的每条规则 |
| 显式 Skill 调用 | adapter trace、其 `behavior_trace.normalized_trace_path`、`trajectory_dir/*.jsonl` 中成功完成的 skill tool 调用及 skill_name 参数 | 只有计划调用、文字提及或失败调用不计入 |
| 默认 activation window | 截至首个成功持久化编辑的窗口；起始投递可直接计入 | 任务结束后才读 Skill 不满足这个局部窗口 |
| `post_diagnosis` / `pre_submission` | 改用 later-edit 收集：成功使用后还须出现成功持久化编辑；起始投递仅在轨迹存在成功编辑时计入该窗口 | activation_phase 字符串不是一台程序强制状态机，也不是严格证明在语义上的“诊断后/提交前” |

局部 missing 检查只针对 `action_group=skill/tool`、`operation=add/modify`、非空 runtime_name；按 capability 的每个 target 分别查证。Skill 名称比较会小写化并将 `-` 归一成 `_`。成功工具调用要求 tool step、非空名字、非空 call_result、无 error，并排除结构化失败状态；later-edit 判定只是时序资格，源码也明确不证明因果关系。[使用证据来源](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L2942)、[起始投递字段](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L3023)、[局部窗口与晚阶段](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L2959)、[missing 检查](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L3760)、[later-edit 收集](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/trajectory_usage.py#L55)、[成功工具判定](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/trajectory_usage.py#L217)

局部通过之后，`_run` 将返回时的 accepted 状态转为 `provisional`，记录原始 `primary_gate_accepted`/reason，并把 `current_refs` 暂设为候选。后续 batch 可在这份累积候选上继续优化；此时 state.best 尚未升级。局部未通过有机会沿 candidate 继续 repair，但这个本地修复工作树与正式 current/best 分开。[provisional 转移](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L594)、[修复分支](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L649)

## 3. epoch 内保留与整版 best 是两道门

### 3.1 先在累积候选的 full 结果中决定每个 gate 是否保留

`_select_gate_from_epoch_checkpoint` 逐候选检查：目标没有 error/machine-evidence 失败；每个目标都属于 full 的 passing 集合；声明的 Skill/Tool 在对应 target 上有成功使用/投递证据。prompt 跳过调用检查。这里读取的是全轨迹成功使用集合，**没有重新执行局部 gate 的 pre-edit / later-edit 窗口检查**；此处的 capability 遍历也没有局部 missing 函数的 add/modify 过滤。不要把两个函数描述成完全相同的一套验收。[epoch 候选筛选](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L3150)

部分候选保留、部分移除时，从 epoch 起始的安全基线重新复制包，再顺序应用保留 capability 的 add/modify/remove，重建注册清单并校验可加载性；不是简单沿用后面那个已包含被拒绝字节的累积快照。产物位于 `run/epoch_selections/eNNN/`，先写 `.filter_tmp` 再替换；失败时删除临时目录并抛错。[过滤重组入口](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L3294)、[基线复制与能力应用](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L3312)、[注册同步与替换](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L3388)

只要 `selected_refs != current_refs`，就对**过滤后的整包再次整集评测**到 `selected_full`；随后 refs 的 `checkpoint_filter` 标记 `post_checkpoint_replay_performed=true` 与对应 selected eval。未过滤则直接复用 full。[过滤后复评](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L848)

### 3.2 再决定 selected 整版能否成为 best

`_globally_promotable` 对最终 selected eval 执行两个条件：

```text
mean(selected 的数值 case.score) ≥ previous_best_score − 1e−9
passing(previous_best_eval) ⊆ passing(selected_eval)
```

若旧 best score/ref 不存在，对应条件跳过。均值函数只平均数值 score，缺少数值的记录不进入分母；这不是另有权重的指标。此函数没有额外的全局 error/machine-evidence 一票否决；目标相关阻断已在候选筛选时处理，非目标结果还受到均值与旧通过集保护约束。不要擅自补写为“整集任何案例都必须通过”。[全局两条件与 epsilon](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L3237)、[均值定义](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L2529)

| 状态字段 | 什么时候改变 | 语义 |
|---|---|---|
| `gate.primary_gate_accepted` | 局部 gate 返回时 | 目标局部改善 |
| `gate.status=provisional` | 局部通过后立即 | 暂进入本 epoch 累积工作版本 |
| `gate.accepted/status=accepted` | full 对该候选的 selection.retained 为真 | 该候选在 full 上被保留；**独立于整版 promotion** |
| `checkpoint.promotion_applied` | selected 满足全局两条件 | 整个 selected 包能升级 best |
| `state.best_*` | promotion 为真；另有无候选初始分数 seed 分支 | 指向被提升整包及其自己的 eval |
| `current/working_harness_refs_path` | epoch 结束统一回写为 best | 不让未提升累积候选成为下 epoch 起点 |
| `checkpoint.status=filtered` | 做了部分保留重组 | 描述筛选方式，不保证 promotion 成功 |

全局失败时 current/best/retained_case_ids 回到 epoch 起始状态，但 gate 仍按 selection 的结果写 accepted/rejected；其 `epoch_checkpoint_outcome.promotion_applied` 可为 false。report 的 accepted_candidate_count 也是数这种 accepted gate，不能当“装入 best 的候选数”。[提升与回退](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L889)、[gate 最终状态与 epoch 结束指针](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L925)、[报告计数](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L3878)

### 3.3 最小数值推演：accepted 但 best 不变

以下为**按条件构造的静态推演，不是测试运行或销售报告实测**。假定旧 best 为 H0，两个案例 A/B 的正式分为 0/1，均值 0.5，passing={B}；候选 C 只以 A 为目标，局部 A:0→1，Skill 证据齐全。full 时 C 的 A/B 为 1/0，均值仍为 0.5。

1. 局部 gate accepted，随后 provisional。
2. full 中目标 A 通过且 Skill 使用证据存在，因此 selection.retained=true，gate 最终 accepted。
3. 均值条件通过，但旧通过案例 B 丢失：promotion=false，reason=`protected_case_regressed`。
4. best/current 回到 H0；gate 的 `epoch_checkpoint_outcome.promotion_applied=false`；epoch node adopted=false。
5. publication 函数见到 accepted gate 后可继续运行，但复制的是 H0 这个 best，而不是 C。故 published 本身不保证比初始 H0 改善。

第 5 步是 `_ensure_final_publication` 的直接控制流推论：入口只要求有 accepted gate，未额外要求至少有一次 successful promotion，也未比较 best 与 source 的包内容。已有多 epoch 测试验证“后续全局退化时仍发布先前 best”；上述“首轮 accepted 但只发布 H0”的最小组合本轮未执行。[发布前提](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L3916)、[读取 best 源](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L3942)、[已有退化测试](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/tests/unit_tests/rsi/test_single_harness_iterative.py#L4932)

## 4. keep/drop 测试逐步落在哪里

`test_epoch_checkpoint_keeps_effective_skill_and_prunes_failed_skill_once` 使用真实 orchestrator、两个测试替身和临时文件；这不是生产模型成功演进的证明。本轮只读测试，未运行。

| 阶段 | 替身预设 / 真实控制逻辑 | 可观察产物 |
|---|---|---|
| H0 | baseline 包只有 `skills/baseline`；数据 case_keep/case_drop，batch_size=1 | baseline refs |
| batch keep | optimizer 复制当前包，新增 keep_skill；evaluator 以“相应目录存在”为 passed 条件 | keep 的 score=1 与伪造 delivered=true metadata；局部暂通过 |
| batch drop | 在累积包再新增 drop_skill；局部目录存在仍给 score=1 | 两个 Skill 都在候选包中 |
| `full` | evaluator 特意令 case_drop 失败，case_keep 成功 | keep retained，drop removed；这是测试预设，非模型测量 |
| filter | 真实过滤器从 epoch 起点重组，只保留 keep，baseline 注册也保留 | `epoch_selections/e001` |
| `selected_full` | 对过滤包再次评测；drop 目录已无，drop 仍失败 | 最终整版分来自这次复评 |
| publication | 真实 publication 复制 best | skills.yaml 恰为 baseline + keep，drop 目录不存在 |

测试断言 `evaluator.full_calls == 1` 的计数器只在 `output_dir.name == "full"` 时增加，**不计 selected_full**；同一测试明确断言过滤后 replay=true。因而“full 一次”不能解读成“总共只有一次整集复评”。[替身生成文件](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/tests/unit_tests/rsi/test_single_harness_iterative.py#L2279)、[替身评分与计数](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/tests/unit_tests/rsi/test_single_harness_iterative.py#L2338)、[配置与真实 orchestrator 调用](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/tests/unit_tests/rsi/test_single_harness_iterative.py#L2418)、[最终断言](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/tests/unit_tests/rsi/test_single_harness_iterative.py#L2441)

还应并读三项控制流测试：selected 从 2/3 退到 1/3 时回退旧 best；filtered selected 达 5/6 时 best/eval 必须指向 selected_full；selected 均值追平旧 2/3 但丢失旧通过案例时拒绝提升。这些分数均为测试 evaluator 预设。[均值退化](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/tests/unit_tests/rsi/test_single_harness_iterative.py#L4932)、[正确 selected 提升](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/tests/unit_tests/rsi/test_single_harness_iterative.py#L4983)、[旧通过案例保护](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/tests/unit_tests/rsi/test_single_harness_iterative.py#L5039)

## 5. 发布留下什么，stage 又代表什么

无 accepted gate 时，state 的 published refs 清空，publication_status=`not_published_no_improvement`，任务仍可 completed。存在 accepted gate 时，复制 best 的每个 role 包到 `run/published/current/<role_key>/`（先 `.publish_tmp`），有 manifest 时先验证，再替换 destination。稳定 refs 写入 `run/member_optimizations/current_harness_refs.yaml`；包含 `published_from_harness_refs_path`、`published_best_score`、role 映射与 `promotion_status=published`。然后才把 state status 设 completed、写 state/report。这是本地文件发布，没有自动调用 Swarm install。[未发布分支](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L3919)、[包复制](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L3948)、[current 路径布局](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/member_optimizer/path_layout.py#L62)、[published refs 字段与写入](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L3993)、[最终完成写入](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L964)

已有 published ref 若合法、ref 与所指包都在 output_dir 内且目录存在，publication 函数可直接复用；这条早退没有再做与最新 best 内容相等的 hash 比对。其设计主要服务 completed run 恢复时确保已有 publication。[复用前提](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L3927)、[completed resume](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L268)

`NodeStageEvent` 是现有 epoch node 的过程通知，不是版本晋升证书：

- `generate.candidate/done` 仅说明生成调用结束；后面才有 gate。
- `evaluate.case.N` 的 status 映射评测 case 的 running/passed/failed/error/skipped；`evaluate.parallel/done` 只说明 completed_cases==total_cases，不代表全部通过。
- `analyze.failures/done` 说明分析返回；`source.reuse/done` 说明复用证据，不是又调用了一次模型。
- 最终 `EventNode.adopted` 直接来自 `checkpoint.promotion_applied`；全局未提升且 checkpoint 非 rejected 时节点可为 UNCHANGED，score 在 selected/evaluated 不一致时为 null。progress.iteration 数 completed epochs，progress.score 为 best_score。

证据：[stage payload](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/events_translate.py#L41)、[generate](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/events_translate.py#L103)、[analysis](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/events_translate.py#L132)、[复用 stage](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/events_translate.py#L22)、[epoch node](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/events_translate.py#L203)、[progress](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/events_translate.py#L166)。

core `emit` 会 await 注入的 on_event，异常不吞；在 Swarm 实际接线中这个回调是 Worker `_sink(queue)`，其 async 函数执行 `queue.put_nowait(event)` 即返回，消费者是另外创建的 asyncio task。因此 await emit 表示完成入队，不表示 WebSocket 客户端已经收到。队列满可从回调抛异常；普通执行结束会 join 队列，取消时丢弃待消费事件以释放 worker。持久化 state/report 与实时 stage 显示应分别核对。[emit](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/events.py#L96)、[Worker 消费协程与回调注入](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/worker.py#L303)、[入队闭包](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/worker.py#L810)、[正常/取消收尾](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/worker.py#L362)

## 6. install：先热加载，再提交 active

### 6.1 入口限制与独立安装副本

installer 要求 task.scenario=HARNESS、task.status=COMPLETED、publication_status=published、published refs 存在；先尝试 adapter/provider 的 publication reader，reader 不可用、抛异常或未返回可识别发布字段时，回退读取 `run/single_harness_state.yaml`。只接受 task run 内的 refs 与恰好一个 role 包，校验目录边界、manifest、包内路径。[安装前置条件](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/harness_activation.py#L708)、[publication reader 回退](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/harness_activation.py#L901)、[单 role 与边界](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/harness_activation.py#L221)

版本身份为 `installation_id = rsi-harness-<package_sha256前16位>`。安装复制到 `<task>/harness/versions/<installation_id>/<extension_name>/`，另写该版本的 `harness_refs.yaml`；active 的 runtime_path 指向这个安装副本。旧 active 的 task_id 与 sha 同本次相同则幂等返回 already_active（修复 catalog 注册，但不重新广播）；目录存在却 hash 不同则冲突。[幂等判断](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/harness_activation.py#L749)、[hash 版本与复制](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/harness_activation.py#L772)

实际成功时序：

```text
保存旧 active 与 activation snapshot
→ 复制/复用 immutable installed package，写 installed refs
→ register_harness_plugin（获得 undo_catalog）
→ await broadcast(old, new) 更新本进程 live agents
→ activation_store.commit(record) 写 active/history
→ task config 写 rsi_installation provenance
→ 返回 ACTIVE + hot_load + installation_id
```

虽然内存 record 在广播前已有 `status=ACTIVE` 字符串，持久化 active 是广播成功后才 commit。`activation.json` 位于 workspace 的 `rsi/tasks/`；commit 保留旧版本到 history，并补充 version_sequence；经临时文件 + `os.replace` 原子替换 JSON。[顺序](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/harness_activation.py#L804)、[active 文件位置](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/harness_activation.py#L299)、[commit/history/sequence](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/harness_activation.py#L416)、[atomic JSON](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/harness_activation.py#L466)

### 6.2 live 加载具体落在哪个对象

AgentManager 遍历缓存 channel agents，只选择 cache_key mode 为 `agent` 或 `code` 的 facade；每个先 await ensure_instance，再 await facade 的 dedicated `apply_rsi_harness_install`。facade 转调其 `_adapter`；DeepAdapter 默认把自己与已有 session adapters 作为 targets，逐个 await local 加载。[Manager 目标选择](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/server/runtime/agent_manager.py#L1534)、[facade 委托](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/server/runtime/agent_adapter/interface.py#L4426)、[session fanout](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/server/runtime/agent_adapter/interface_deep.py#L7425)

local activation 保存旧安装信息、卸载旧 RSI LoadRecord，并处理同 package_id/installation_id 的普通 plugin 所有权，最终 `record = await instance.load_plugin(config_path)`。成功才保存 `_rsi_harness_load_record`、`_rsi_harness_install_id`、`_rsi_harness_config_path` 等实例字段；LoadRecord 用于后续 `unload_extension`。这里 config_path 实际传的是包 runtime 目录，不是配置 YAML 的字符串路径。[local 加载与所有权](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/server/runtime/agent_adapter/interface_deep.py#L7340)、[load_plugin](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/server/runtime/agent_adapter/interface_deep.py#L7374)、[实例状态更新](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/server/runtime/agent_adapter/interface_deep.py#L7399)

### 6.3 失败与补偿：有回滚，但不是无条件事务保证

| 失败点 | 实际补偿 | 边界与保留 |
|---|---|---|
| 单个 DeepAgent 新包 load 失败 | local 尝试恢复被置换 ordinary plugins，再加载旧 RSI 包 | 旧包恢复也失败则 InstallConflict；部分插件补偿本身仍可能抛错 |
| 同一个 adapter 的 session fanout 中途失败 | 逆序按 snapshots 恢复 targets，之后抛原异常 | **恢复异常只记 logger.exception 并继续**，没有承诺每个 session 已恢复 |
| AgentManager 中某个 facade 失败 | 停止后续广播，逆序恢复已成功的 facade | 无论补偿成功与否都抛 InstallConflict；失败的 facade 依赖自身内部补偿。成功补偿也不会继续 commit active |
| 广播成功后 active commit 失败 | installer 反向广播，恢复 live；active 原子替换失败时旧文件通常仍在 | 反向广播再失败则 InstallConflict；普通 InstallFailed 且尚未 committed 时删除新建版本副本 |
| active 已提交，task provenance 写失败 | 反向广播 + activation snapshot restore | 两者成功则 pointer_committed=false、清理新副本并撤销 catalog；恢复失败报冲突，不宣称一致 |
| 无 manager 或无广播方法 | 返回 attempted=0/succeeded=0/failed=[]，仍可提交 active | 此分支跳过 live 广播；不能据此推断没有缓存实例。未来 Agent 另读 active |

证据：[local 补偿](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/server/runtime/agent_adapter/interface_deep.py#L7375)、[session 补偿及仅日志异常](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/server/runtime/agent_adapter/interface_deep.py#L7460)、[Manager 回滚与抛错](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/server/runtime/agent_manager.py#L1574)、[指针/provenance 补偿](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/harness_activation.py#L821)、[异常清理区别](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/harness_activation.py#L865)、[无 manager 分支](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/harness_activation.py#L938)。

真实 manager 的部分失败会抛异常，不是返回 failed list 后悄悄提交 active。但 installer 的泛化 `_broadcast` 本身只检查是否 awaitable，不检查返回 dict 中的 failed；`_restore_live` 也以回调是否抛异常判成功。Manager 的 succeeded 计数按 await 没抛异常增加，不检查返回 status，而 facade/无实例 local 可以返回 SKIPPED。DeepAdapter 自己也可能把 local 返回的 SKIPPED 计入 applied，而未核验底层加载。因此应阅读返回 hot_load 与各层实际状态，不能将 succeeded 当成严格的每个底层实例确认。[session计数](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/server/runtime/agent_adapter/interface_deep.py#L7452)[广播适配](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/harness_activation.py#L938)、[恢复判定](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/harness_activation.py#L949)、[Manager 成功计数](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/server/runtime/agent_manager.py#L1555)、[facade SKIPPED](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/server/runtime/agent_adapter/interface.py#L4435)

静态读到的安装测试用假 manager 验证 provenance 失败时第二次反向广播、active 恢复、版本副本与 catalog 删除；另一个测试令 manager 抛普通 RuntimeError 验证 catalog 撤销。它们不等于验证了真实多 session 广播的所有补偿失败组合。[provenance 测试](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/tests/unit_tests/rsi/test_harness_activation.py#L260)、[热加载失败测试](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/tests/unit_tests/rsi/test_harness_activation.py#L300)

显式 `rsi.harness.rollback(installation_id)` 是另一操作：对任一保留版本检查包存在/hash/manifest；若存在 QUEUED/RUNNING/PAUSED RSI task 则拒绝回退；仍然先 broadcast 再 commit，不等于优化器把候选丢弃。[rollback 入口与顺序](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/harness_activation.py#L623)、[回退限制](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/harness_activation.py#L682)

## 7. 新 Agent 与下一轮优化分别怎样继承

新 DeepAdapter 初始化在普通 active packages 后 await `_load_rsi_active_harness`。它从 workspace `rsi/tasks/activation.json` 读取 active.runtime_path，再调用本 adapter 的 local install，不做 session fanout。读取 active 或加载失败会记日志并返回 None，启动继续；因此“active 指针存在”不保证每个新 Agent 必然加载成功。初始化和配置 reload 都有这个调用点。[恢复实现](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/server/runtime/agent_adapter/interface_deep.py#L7271)、[初始化调用](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/server/runtime/agent_adapter/interface_deep.py#L9895)、[reload 调用](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/server/runtime/agent_adapter/interface_deep.py#L10271)

下一次创建优化任务时，源 Harness provider 的实际优先级为：显式 package_id（由插件 catalog 解析，失败不悄悄替代）→ active.runtime_path → initial_harness_refs.yaml → legacy registry → native baseline。显式 legacy harness_id 位于 active/initial 之后，不能当成必定覆盖 active 的 selector。task service 还保留受控调用者/测试的 harness_path 显式入口。[provider 优先级](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/server/agent_ws_server.py#L10594)、[active 后的 fallback](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/server/agent_ws_server.py#L10626)、[受控 harness_path](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/services.py#L335)

选中 active 后不是下轮一直读全局 mutable pointer：materializer 复制源包到新 task 的 `harness/versions/baseline-<source hash前16位>/<package>/`，核对复制 hash，写新 task 的 `harness/harness_refs.yaml`。于是已有 task 的基线保持私有；“运行 Agent 使用新版”与“新建优化任务冻结新版为基线”是两条分别发生的路径。[基线 materialization](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/materializer.py#L177)、[copy 与 hash/refs](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/materializer.py#L218)、[task config 注释](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/services.py#L267)

## 8. 优化取消/异常保留什么

**外层 task 标为 TERMINATED 不保证 core 已终止。** 生产 HarnessProvider 的 supports_terminate=false；Worker 的 terminate 分支取消 `_execution_tasks[task_id]` 并标外层 task TERMINATED，但这个字典保存的是 `_run_until_slot_free(...)` 的外层 Task。该协程又通过 `asyncio.create_task` 创建真正运行 `_execute_task → adapter → Provider → core` 的内层 runner，再 `await asyncio.wait({runner, released}, FIRST_COMPLETED)`。外层取消的 finally 只移除 slot 引用和 cancel released，没有 cancel/await runner；异常传播也会跳过 finally 后将 runner 加入 `_winding_down` 的语句。因此此路径存在“外层已终止、内层仍执行、未登记后台收尾”的取消传播缺口，不能根据 cancel 分支注释宣称实际引擎已停止。[Provider 能力](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/harness_provider.py#L168)、[terminate 取消字典中的 Task](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/worker.py#L154)、[外层 Task 注册](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/worker.py#L227)、[内层 runner 与 finally](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/worker.py#L264)

本轮对源码原样 AST 提取的 `_run_until_slot_free` 配合受控 inner 做有限本地检查，结果为 `outer_cancelled=true`、`inner_done_after_outer_cancel=false`、`inner_cancelled_after_outer_cancel=false`、`inner_registered_as_winding_down=false`；检查后主动释放并 await 受控 inner。它只验证原始外层协程的取消行为，**没有执行 `RsiWorker.cancel`、store、Provider、真实 core 或实际服务**，不能称为服务端终止问题的端到端复现。[本地检查范围与结果](evidence/local_contract_checks.json)

源码还显示另一后果：`_run_loop` 在 `await exec_task` 外只捕获 `Exception`，而本地 Python 的 `asyncio.CancelledError` 直接继承 BaseException。若外层 Task 的取消在这里传播，`except Exception` 不会处理，finally 清理字典/`task_done` 后 `_run_loop` 也会以取消结束，而非自然进入下一次队列循环。`_ensure_runner` 可在后续被调用时重建已结束的 loop，但 terminate 分支没有在此直接重启它；不能保证已有排队任务当即继续。这一条为源码控制流加本地异常继承关系核查，未运行实际 Worker 队列。[await/except/finally](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/worker.py#L239)、[重建条件](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/worker.py#L198)

**只有取消实际到达执行 core 的协程时**，core run 的 finally 才会检测到当前 coroutine.cancelling；若 observer 已绑定 state，就将 core state.status 改 terminated，结束 pending usage 记录，再原子写 state；已有 report 才更新 usage/status，不保证生成完整最终 report。普通外层状态变化不会自行触发这段 terminated 保存。它也没有统一删除候选目录或回退 installed active 的动作，因为优化过程本就没有安装。[core finally 的实际条件](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L181)

普通异常在该 core finally 中只保存已有 state/usage，没有统一把 core status 改 failed；Swarm Worker 捕获异常后另把仍在 RUNNING 的 task 标 FAILED。故排错要同时看 Swarm task 状态和 core state，而不是要求二者字符串始终一致。已写的 eval、candidate、checkpoint 文件可保留为审计证据，但不代表都被接受或发布。安装器要求外层 task COMPLETED，因此终止/失败任务即使磁盘有部分产物，也不能从正常 install 入口安装。[Worker 异常处理](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/worker.py#L352)、[安装 task 门槛](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/harness_activation.py#L717)

“保存 terminated 防止恢复”也要说清边界：Swarm Worker 的 resume 仅允许 PAUSED，因此不能正常 resume TERMINATED；core 的 `_load_or_create_state` 则主要校验 fingerprint，并没有以 terminated 单独拒绝直接库调用 resume。本轮不将 core 注释扩大成独立库入口已有终止不可恢复锁。[Swarm resume 状态检查](https://gitcode.com/openJiuwen/jiuwenswarm/blob/f29c060cee90aef10e46b2a3646fe3628f60ea7c/jiuwenswarm/agents/harness/common/rsi/worker.py#L174)、[core resume state 加载](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/single_harness/iterative.py#L1730)
