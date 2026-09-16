# A3 后半段：执行结果怎样成为分数，再交给分析器

本节接住上一段返回的 `CaseExecutionResult`。以 `case_a` 写出缺 `currency` 的 `report.json` 为教学说明；真实交接测试只描述“结构化产物漏字段”，没有提供这条销售任务的运行记录。显式选择 `llm_as_judge` 后，任务模型与评分 Agent 是不同对象；默认 `script_based` 不会自动理解报告的自然语言评分规则。[真实案例原型](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/tests/unit_tests/rsi/test_analyzer_optimizer_handoff.py#L32)、[评分器工厂](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/judger/__init__.py#L21)

## 谁装配评分器，谁真正调用

`TeamEvaluator.__init__` 同步执行 `_make_case_runner()`，通过 `build_backend(config)` 与 `build_judger(config)` 创建两个对象，再注入同一个 `CaseRunner`。因此 backend 的职责是执行，judger 的职责是评价。`CaseRunner.execute()` 先 `await backend.execute()`，再处理证据，最后 `await self._judge()`。这里没有单独部署“评分器进程”；本例 Judge 的 DeepAgent 在宿主中创建，模型请求访问外部服务。[装配](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/team_evaluator.py#L66)、[执行与评分调用](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/case_runner.py#L110)

| 交接 | 传递的数据与实际动作 | 返回或写入 |
|---|---|---|
| backend → CaseRunner | `CaseExecutionResult.response/execution_status/error/workspace_dir/metadata`；不把 response 的“检查完成”当成验收 | CaseRunner 拿到任务结束状态及工作目录 |
| CaseRunner → 证据整理函数 | 从任务目录收集指定产物；`_harvest_artifacts` 没取到文件时可按 `workspace_changes` 回收变化文件 | `artifacts/`、`tr/trajectory_events.jsonl`、评分前的 `judge/normalized_trace.json` |
| CaseRunner → `_judge` | 同时传 `case`、完整 `execution_result` 和案例输出目录；若 backend 已给 `judge_result`，优先采用；否则调用注入的 judger | `JudgeResult` 对象；没有评分器或只有完成状态时抛基础设施异常 |
| LlmAsJudgeJudger → `prepare_judge_workspace` | 经 `asyncio.to_thread` 复制产物、轨迹、公开附件、私有评分材料；写任务和 rubric | `judge/evaluation_<id>/evidence/request.json` 及证据副本 |
| Judger → `run_judge_agent` | 创建只读 DeepAgent，要求读 request 和证据后返回 JSON；`await Runner.run_agent` | 模型返回的 JSON 字符串，不是最终可信总分 |
| Judger → 解析及评分函数 | 校验 ID 全覆盖、逐项分数范围、reason/evidence；使用数据集给定权重计算 | 连续分、规范化 assessment、逐条 requirement 结果 |
| Judger → CaseRunner → TeamEvaluator | 阈值化为 `JudgeResult.score/passed`；CaseRunner 落盘并返回 `EvaluationCaseTraceRef` | 每题结果，继而 `summary.json` 和 `eval_ref.yaml` 路径 |
| 编排器 → Analyzer | 把 `eval_ref.yaml` 路径传给分析入口；Analyzer 的 CaseReader 重新读取结果和轨迹 | `CaseAnalysisInput`，进入下一节的诊断链 |

对应交接代码：[收集、轨迹与调用](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/case_runner.py#L120)、[`_judge` 优先级](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/case_runner.py#L306)、[证据副本](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/judger/judge_evidence.py#L90)、[模型调用](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/judger/judge_runtime.py#L115)、[回读结果](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluation_result_analyzer/case_reader.py#L110)。

## 用同一份报告跟踪一次评分

设本例 `reference.rubric` 有两项：①报告字段和类型符合 schema；②total 等于 amounts 的和。不要再无意加一个 `reference.answer`：默认 `answer_role=criterion` 会把它插入为第三项 `reference_answer`，改变分母；只供参考时应显式使用 `answer_role=reference`。这是源码规定，不是按任务语义推断。[评分契约](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/judger/scoring.py#L57)

下面展示的是**教学用 Judge 返回值**。它说明字段如何转换，不代表本次调用了评分模型：

```json
{
  "status": "completed",
  "overall_reason": "total正确，但实际report.json遗漏currency",
  "behaviors": [
    {"id":"rubric_001","score":0,"reason":"缺少必填字段","evidence":"artifacts/report.json只有total"},
    {"id":"rubric_002","score":1,"reason":"10+20=30","evidence":"assets/orders.json与artifacts/report.json"}
  ],
  "forbidden_hits": []
}
```

模型给出的是逐项判断及证据文字；`score_judge_output` 验证结构与数值，但不会再用一个确定性 JSON Schema 程序证明模型判断正确。每个要求必须恰好出现一次；模型额外给的 `overall_score` 不作为总分，模型自行改写的 weight/penalty 也会被数据集中的值覆盖。[覆盖与校验](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/judger/scoring.py#L125)、[计算](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/judger/scoring.py#L144)

```text
逐项分：schema=0，sum=1，两个权重均为1
连续分 = (0×1 + 1×1) / (1+1) = 0.5
passed = 连续分 >= judge_success_score；默认阈值0.8 → false
JudgeResult.score = float(passed) → 0.0
CaseRunner的最终status = failed（执行本身仍可是passed）
```

`execution_status=passed` 只表示 backend 正常结束；最终任务通过看 `JudgeResult.passed`。执行失败时最终 status 为 `error`，不与“执行完成但答案不合格”的 `failed` 混用。[阈值化](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/judger/llm_as_judge.py#L160)、[最终状态](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/case_runner.py#L347)

若使用 forbidden 项，默认 `ceiling` 是把连续分限制到 `1-max(已触发penalty)` 以下；显式 `subtract` 才累加扣分并以0为下界。`judge_rubrics` 的百分比导入可指定后者，不能把两种算式混写。[惩罚公式](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/judger/scoring.py#L179)、[rubric 归一化](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/data_loader/grading_contract.py#L92)

## 同一个分数为什么保存在多个位置

| 位置 | 本例教学值 / 意义 | 下游怎么读 |
|---|---|---|
| `result.json.score`、`trace.json.evaluation.score` | `0.0`，阈值化后的正式 case 分数 | MetricsCollector 聚合；全局 best 等选择使用正式分 |
| `result.json.evaluation.passed` | `false` | CaseReader 及通过案例统计 |
| `evaluation.metadata.parsed.overall_score` | `0.5`，连续分 | 保留评审原始拆分与诊断依据 |
| `evaluation.metadata.optimization_signals.continuous_score.value` | `0.5`，显式优化信号契约 | 候选层记录连续改善供诊断；不替代当前 gate 对正式目标分提高的要求 |
| `evaluation.metadata.requirement_results.items` | schema未通过、sum通过 | 逐条比较失败修复和已通过要求是否回退 |
| `evaluation.metadata.parsed.dimensions` | 低分项、各项 reason/evidence、项数等 | `LlmJudgeSignalExtractor` 确定性提取，不再调用模型 |
| `summary.json.average_score` | 对本批正式 case 分求均值；仅有本例时为0 | `eval_ref.yaml` 指向 summary，供编排器读取 |

字段写入见 [JudgeResult 元数据](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/judger/llm_as_judge.py#L164)、[CaseRunner 的两个文件](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/case_runner.py#L206)、[MetricsCollector](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/metrics_collector.py#L22)、[确定性信号提取](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluation_result_analyzer/signal_extractor.py#L355)。

真实测试 `test_node_score_averages_binary_cases_not_raw_judge_scores` 固定五个模型分数，其中四个过0.8，断言整批 average_score=0.8；同时断言 native signals 仍保留五个连续分。该测试把模型调用换成 `AsyncMock`，本次没有执行它。它明确了两种评分口径的接口预期。[测试定义](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/tests/unit_tests/rsi/test_evaluator_agent.py#L99)

## 证据如何冻结，异常如何回到上层

Judge 工作区只复制本题所需证据，不包含任务的可变工作区、模型配置或历史评分。评分前的 normalized trace 先被复制成 `execution_trace.json`；评分完成后 CaseRunner 才重写主目录的 trace，加入本次评分。因此 Judge 读到的是评分前快照。[准备证据](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/judger/judge_evidence.py#L103)、[评分前后写入](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/case_runner.py#L155)

`JudgeReadOnlyRail` 只注册 read_file/list_dir/glob/grep；不提供 shell、写文件、Skill 执行或子 Agent。默认最多8轮，最后一轮由 BudgetRail 关闭工具并要求完整 JSON；模型 temperature 固定0，但这不保证判断正确或输出绝对确定。[工具](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/judger/judge_runtime.py#L26)、[预算钩子](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/judger/judge_runtime.py#L50)、[模型装配](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/judger/judge_runtime.py#L90)

| 情况 | 谁处理、如何衔接 | 是否应解释为任务得0分 |
|---|---|---|
| 任务 Agent 正常结束，但产物缺字段 | Judge返回不满足项；程序算分和阈值 | 是任务失败或部分得分，取决于规则 |
| backend 的 execution_status 不是passed | Judger生成score=0、passed=false的failure result，CaseRunner最终status=error | 该数值0仍可计入均值，但须保留执行失败原因，不声称已完成业务验收 |
| Judge漏项、非数值分、输出格式不合法 | `_evaluate` 用同一份冻结证据最多补一次格式修复 | 两次均不可用则抛 `EvaluationInfrastructureError`，不是取两次高分 |
| Judge声称unavailable | 第一次要求复核“任务没完成”与“证据无法检查”；仍unavailable则抛异常 | 不直接归为任务低分 |
| 模型传输错误或评分超时 | Judger写error.json；TeamEvaluator仅对识别的临时传输错误按配置重试整题 | 未恢复则向上抛；不能伪造业务评分 |
| 评分基础设施异常 | CaseRunner写`evaluation_error.json`后抛出；finally清理运行资源 | 不能当成正常`result.json`中的失败案例 |

评分内的格式补救与模型调用重试是两层机制：格式补救固定最多两轮输出/解析尝试，两轮也可能均不可用；每次模型调用还经过 `run_model_call_with_retries`，默认 judge_max_retries=2。外层 TeamEvaluator 又有默认2次临时案例重试，可能重新执行任务，不能称所有重试都只读同一份证据。外层依赖异常文本识别传输错误；Judger 包装后的异常常只写“LLM evaluator failed”和error.json路径，因此不能保证评分传输错误或超时一定触发整题重试。[格式及调用重试](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/judger/llm_as_judge.py#L108)、[异常包装](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/judger/llm_as_judge.py#L91)、[案例重试](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/team_evaluator.py#L169)、[异常落盘](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/case_runner.py#L270)

## 怎样交给下一段诊断

每题完成后，`TeamEvaluator` 等所有案例结束，调用 `MetricsCollector.collect` 读取 `cases/*/result.json` 写 summary，再返回 `eval_ref.yaml`。这个返回值是**文件路径字符串**，不是直接把 Judge 对象交给 Analyzer。[汇总与返回](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluator/team_evaluator.py#L236)

Analyzer 的 `CaseReader.read_case_inputs` 再根据结果目录读取每题 result 和相邻 trace，把 `input/response/status/score/evaluation_metadata` 等装为 `CaseAnalysisInput`；`expected` 明确为None，不意味着案例没有评分标准。它随后选择 `LlmJudgeSignalExtractor` 读取已有评分拆分。至此，后续诊断拿到的是“任务+执行证据+评分结果+当前Harness”，并未再次执行报告任务。[对象转换](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/openjiuwen/rsi/harness_rsi/evaluation_result_analyzer/case_reader.py#L132)

本轮实际执行的局部检查使用仓内 `_case/_output` 夹具（total存在、units缺失），原样抽取评分函数，得到连续分0.5；还验证漏评分项被拒绝、模型伪造权重不生效、subtract与ceiling分别为约0.7与0.8。**没有调用真实Judge、CaseRunner或完整pytest。**脚本与原始输出分别见 [verify_local_contracts.py](verify_local_contracts.py)、[local_contract_checks.json](evidence/local_contract_checks.json)。
