# Verl 框架下的使用文档

[English](./README.md)

## 目录文件介绍

* multiturn_grpo.yaml 和 multiturn_megatron_grpo.yaml 是 Verl 框架下的配置文件，分别对应于普通版和 Megatron 版的 GRPO 模型。
* multiturn_llm_reward.py 是 Verl 框架下的自定义奖励模型文件，用于计算奖励值。

使用方式：
1. 确保已安装 Verl 框架和相关依赖。
2. 将 multiturn_grpo.yaml 或 multiturn_megatron_grpo.yaml 配置文件中的模型路径指向预训练的 GRPO 模型。
3. 将 multiturn_llm_reward.py 配置文件中的奖励模型路径指向该文件。
4. 使用 Verl 框架运行配置文件，即可开始训练和评估模型。
