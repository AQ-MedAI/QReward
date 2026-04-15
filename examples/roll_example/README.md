# Usage Documentation under the ROLL Framework

[中文版](./README_ZH.md)

## Introduction

This directory contains examples for integrating QReward with [ROLL (Reinforcement Learning Optimization for Large-Scale Learning)](https://github.com/alibaba/ROLL), Alibaba's RL training framework for LLMs.

QReward serves as the **reward computation acceleration layer** in ROLL's training pipeline, replacing the built-in `LLMJudgeRewardWorker` when the Judge model is deployed as a remote API service.

### Architecture

```
ROLL Training Loop
  ├── Actor (policy model training)
  ├── Rollout (response generation)
  ├── Reference (KL divergence)
  └── Reward ← QReward (this example)
        └── OpenAIChatProxy → Remote LLM Judge API
```

### When to Use QReward with ROLL

| Scenario | Recommended Approach |
|----------|---------------------|
| Judge model on local GPUs | Use ROLL's built-in `LLMJudgeRewardWorker` |
| Judge model as remote API | ✅ **Use QReward** (this example) |
| Multiple Judge API endpoints | ✅ **Use QReward** with load balancing |
| Need retry / rate limiting / circuit breaker | ✅ **Use QReward** |

## Directory Files

* [multiturn_llm_reward.py](./multiturn_llm_reward.py) — Custom Reward Worker using QReward's `OpenAIChatProxy` for high-concurrency LLM-as-Judge scoring. Provides both:
  - `QRewardLLMJudgeWorker` class (ROLL worker_cls interface)
  - `compute_score()` function (verl/slime-compatible interface)
* [rlvr_qreward_llm_judge.yaml](./rlvr_qreward_llm_judge.yaml) — ROLL YAML configuration that uses the QReward-based reward worker.

## Usage

### 1. Install Dependencies

```bash
pip install qreward
```

### 2. Set Environment Variables

```bash
# Required
export OPENAI_API_BASE="https://your-judge-api/v1"
export OPENAI_API_KEY="sk-your-key"

# Optional
export JUDGE_MODEL="DeepSeek-R1"          # Default: DeepSeek-R1
export JUDGE_MAX_CONCURRENT="64"          # Default: 64

# Optional: Multi-endpoint load balancing
export JUDGE_EXTRA_URLS="https://backup-api-1/v1,https://backup-api-2/v1"
export JUDGE_EXTRA_KEYS="sk-key-1,sk-key-2"
```

### 3. Configure ROLL

In your ROLL YAML config, set the reward worker to use QReward:

```yaml
rewards:
  llm_judge:
    worker_cls: multiturn_llm_reward.QRewardLLMJudgeWorker
    tag_included: [RLVR]
```

### 4. Run Training

```bash
python examples/start_rlvr_pipeline.py \
  --config_name rlvr_qreward_llm_judge
```

## Key Advantages over Built-in LLMJudgeRewardWorker

| Feature | Built-in | QReward |
|---------|----------|---------|
| GPU allocation for Judge | Required | Not needed |
| Concurrent API calls | Limited | High (configurable) |
| Automatic retry | No | Yes |
| Rate limiting | No | Yes |
| Circuit breaker | No | Yes |
| Load balancing | No | Yes (Round-Robin, Weighted) |
| Multiple endpoints | No | Yes (failover support) |
