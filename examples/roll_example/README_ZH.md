# ROLL 框架使用文档

[English](./README.md)

## 简介

本目录包含 QReward 与 [ROLL（Reinforcement Learning Optimization for Large-Scale Learning）](https://github.com/alibaba/ROLL) 框架的集成示例。ROLL 是阿里巴巴开源的大模型强化学习训练框架。

QReward 在 ROLL 训练流程中作为 **Reward 计算加速层**，当 Judge 模型部署在远程 API 服务上时，替代 ROLL 内置的 `LLMJudgeRewardWorker`。

### 架构

```
ROLL 训练循环
  ├── Actor（策略模型训练）
  ├── Rollout（响应生成）
  ├── Reference（KL 散度计算）
  └── Reward ← QReward（本示例）
        └── OpenAIChatProxy → 远程 LLM Judge API
```

### 何时使用 QReward

| 场景 | 推荐方案 |
|------|---------|
| Judge 模型在本地 GPU 运行 | 使用 ROLL 内置 `LLMJudgeRewardWorker` |
| Judge 模型部署为远程 API | ✅ **使用 QReward**（本示例） |
| 多个 Judge API 端点 | ✅ **使用 QReward** 负载均衡 |
| 需要重试 / 限流 / 熔断 | ✅ **使用 QReward** |

## 目录文件说明

* [multiturn_llm_reward.py](./multiturn_llm_reward.py) — 使用 QReward 的 `OpenAIChatProxy` 实现高并发 LLM-as-Judge 评分的自定义 Reward Worker。提供两种接口：
  - `QRewardLLMJudgeWorker` 类（ROLL worker_cls 接口）
  - `compute_score()` 函数（verl/slime 兼容接口）
* [rlvr_qreward_llm_judge.yaml](./rlvr_qreward_llm_judge.yaml) — 使用 QReward Reward Worker 的 ROLL YAML 配置文件。

## 使用方法

### 1. 安装依赖

```bash
pip install qreward
```

### 2. 设置环境变量

```bash
# 必需
export OPENAI_API_BASE="https://your-judge-api/v1"
export OPENAI_API_KEY="sk-your-key"

# 可选
export JUDGE_MODEL="DeepSeek-R1"          # 默认: DeepSeek-R1
export JUDGE_MAX_CONCURRENT="64"          # 默认: 64

# 可选：多端点负载均衡
export JUDGE_EXTRA_URLS="https://backup-api-1/v1,https://backup-api-2/v1"
export JUDGE_EXTRA_KEYS="sk-key-1,sk-key-2"
```

### 3. 配置 ROLL

在 ROLL 的 YAML 配置中，将 Reward Worker 设置为使用 QReward：

```yaml
rewards:
  llm_judge:
    worker_cls: multiturn_llm_reward.QRewardLLMJudgeWorker
    tag_included: [RLVR]
```

### 4. 启动训练

```bash
python examples/start_rlvr_pipeline.py \
  --config_name rlvr_qreward_llm_judge
```

## 相比内置 LLMJudgeRewardWorker 的优势

| 特性 | 内置方案 | QReward |
|------|---------|---------|
| Judge 模型 GPU 分配 | 需要 | 不需要 |
| 并发 API 调用 | 有限 | 高并发（可配置） |
| 自动重试 | 无 | 有 |
| 限流控制 | 无 | 有 |
| 熔断保护 | 无 | 有 |
| 负载均衡 | 无 | 有（轮询、加权） |
| 多端点支持 | 无 | 有（故障转移） |
