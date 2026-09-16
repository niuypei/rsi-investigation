# RSI 调研与源码分析

本仓只保存分析文档、配图、研究验证记录及分析用的局部检查脚本，不包含研究对象的代码仓库或源码快照。

## 阅读入口

- [调研要求](RESEARCH_REQUIREMENTS.md)
- [RSI 调研笔记](RESEARCH_NOTES.md)
- [模型与 Harness 协同演进综述](MODEL_HARNESS_COEVOLUTION.md)
- [八项工作 Walkthrough 总索引](walkthroughs/README.md)
- [openJiuwen 特性总览](OPENJIUWEN_RSI_OVERVIEW.md)
- [F01 Harness 迭代](OPENJIUWEN_F01_HARNESS_ITERATION.md)
- [F01 深入分析](OPENJIUWEN_F01_DEEP_DIVE.md)
- [F01 代码参考](OPENJIUWEN_F01_CODE_REFERENCE.md)
- [F01 分章节分析](research/f01/README.md)
- [F08 在线模型适配](OPENJIUWEN_F08_ONLINE_MODEL_ADAPTATION.md)
- [F01 / F08 代码阅读计划](OPENJIUWEN_F01_F08_CODE_WALKTHROUGH.md)
- [HarnessX 架构、部署与关键流程](research/harnessx/CODE_ARCHITECTURE_ANALYSIS.md)

## 发布说明

文档内容来自本地分析工作区。发布副本的文档链接改为仓内相对路径，源码链接指向原项目的固定提交；不会将原项目代码复制进本仓。源码站点可能有登录或访问限制，远程提交可用性未逐链接复核。

`research/f01/verify_local_contracts.py` 是分析过程编写的有限检查脚本，运行时需要另行准备对应源码，不是项目实现仓库。`research/continual-harness/history/` 保存文档引用的历史输入摘录及来源说明，不代表本次进行了游戏或训练。

验证 JSON 保留原分析时的本地路径、哈希与检查结果；这些是历史证据，不能作为发布副本哈希的校验记录。发布只调整 Markdown 链接，不重新执行模型、服务或训练。
