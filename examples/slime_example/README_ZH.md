# Slime 框架下的使用文档

[English](./README.md)

## 目录文件介绍

* multiturn_llm_reward.py 是 Slime 框架下的自定义奖励模型和自定义生成 Rollout 数据的文件，用于自定义生成数据集和计算奖励值。

使用方式：
1. 确保已安装 Slime 框架和相关依赖。
2. 检查一下 run_qwen2.5_3B.sh 的 【# Change Here !!!!】注释，确保路径指向正确的文件。
3. 将配置文件中的奖励模型路径指向 multiturn_llm_reward.py 文件，确保函数名称和参数正确。
4. 使用 run_qwen2.5_3B.sh 运行训练脚本，即可开始训练和评估模型。

为了实现多轮 + 工具调用，在 slime 中只需要实现一个自定义的数据生成函数，以及一个任务所需的 reward model，对应启动脚本中的这 2 个配置项：

```bash
CUSTOM_ARGS=(
   --custom-generate-function-path multiturn_llm_reward.generate
   --custom-rm-path multiturn_llm_reward.compute_score
)
```