# 验证范围、实现边界与继续读代码的检查点

## 本轮实际执行了什么

| 检查 | 输入与执行方式 | 得到的结果及限制 |
|---|---|---|
| 评分函数 | 原样提取评分函数，调用真实归一化/requirement函数，使用仓内受控Judge夹具 | total存在/units缺失得到连续分0.5；缺评分项被拒绝；伪造模型权重被覆盖；累积扣分约0.7、上限惩罚0.8。未运行Judge Agent/CaseRunner |
| 取消传播 | 原样提取`RsiWorker._run_until_slot_free`，将其内部执行替换为等待Event的受控协程 | 外层取消后内层仍未结束/取消；slot引用清理，但未加入收尾集合。结束检查时已放行并await内层。未执行真实cancel/store/Provider或远端请求 |
| 文档与基线 | 检查本文及相关文档中的本地路径/行号、代码块配对、所读仓库提交和工作树 | 见[本轮校验记录](evidence/document_validation.json)；不代表调用链已经联调 |

可复读脚本为 [verify_local_contracts.py](verify_local_contracts.py)，输出为 [local_contract_checks.json](evidence/local_contract_checks.json)，包括被提取源码的SHA-256。运行命令为 `python3 -B research/f01/verify_local_contracts.py`；脚本不导入完整应用、不安装依赖、不连接模型或启动服务。

本地可用 `python3` 为3.9.6，低于项目要求的3.11；未安装pytest/yaml/pydantic。另一个python3.12入口启动时缺标准库encodings，未作为可用测试环境。本轮据此采用上述有限检查，**没有运行任何仓内pytest**；本文出现的“测试断言”均指已读到的测试定义。[项目Python要求](https://gitcode.com/openJiuwen/agent-core/blob/13d226d91ccc1ff4c041e984fb6aa90de6c5e0ff/pyproject.toml#L10)

## 本次深入后必须保留的限定

| 可以根据代码确认 | 仍不能据此确认 |
|---|---|
| create时固定私有材料；Provider将其转换成core请求 | 本地Swarm/core不同于声明依赖的版本组合已能联调 |
| Skill文件能经过manifest/binder进入SkillUseRail；Rail能把内容投递给模型 | 模型必然遵循规程；本例报告已经实际修好 |
| 模型返回文件全文，程序校验、写入、注册、包检查 | 每次尝试都是文件事务；包合法等于业务效果提升 |
| 局部gate、epoch retained和整版promotion分别存状态 | accepted_count就是进入best的改动数；published必然优于初始H0 |
| 安装先广播热加载，再提交active，失败有多层补偿 | 每个缓存/会话实例均确认成功；所有补偿失败组合仍保持一致；跨进程集群一致性 |
| core收到取消时保存终止状态 | Worker外层TERMINATED保证内层引擎或远端模型已经停止 |
| 文件、引用、评分和事件存在明确衔接 | 有真实完整run证明收益、泛化或所有异常恢复路径正确 |

这些边界分别对应前文第2章取消传播、第3章评分口径、第4章文件写入、第5章gate/发布/安装的代码证据。发现点属于当前固定快照的实现分析；本轮没有为其修改源码。

## 跟同一个case时应留下的阅读笔记

```text
request_id / 用户session
  → task_id + task私有input/harness/models/config
  → HarnessEngineRequest → core request + profile
  → run/epoch/batch + 当前harness_refs中的角色/包路径
  → case_a + 独立eval_session + task workspace
  → report.json → artifacts/trace → JudgeResult
  → eval_ref + case.score + continuous_score + requirement_results
  → issue → hypothesis摘要/decision_contract → action/declared_write_paths
  → 模型file_writes → 动作副本 → integration → verification
  → candidate refs → 目标gate → epoch full/selected_full → best
  → publication refs → 独立安装副本/installation_id
  → live LoadRecord + activation.json active.runtime_path
  → 新Agent加载 / 新Task冻结baseline（两条路径）
```

复读时每次只追一个交接：调用前截取传入字段，调用后核对返回对象或引用文件，再定位谁读了它。看到`success/accepted/ACTIVE`时，同时记录它属于哪一层，以及后续还有哪个检查未完成。原 walkthrough 的前三轮已完成实现分析；F08及两条链的联合分析保留为原计划后续范围。
