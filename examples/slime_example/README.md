# Slime Framework Usage Documentation

[English](./README.md)

## Directory File Introduction

* [multiturn_llm_reward.py](file:///Users/hailinsun/Documents/sunhailin-Leo/github/python-projects/QReward/examples/verl_example/multiturn_llm_reward.py) is a file under the Slime framework for custom reward models and custom generation of rollout data, used to generate datasets and calculate reward values.

Usage:
1. Ensure that the Slime framework and related dependencies are installed.
2. Check the `【# Change Here !!!!】` comment in [run_qwen2.5_3B.sh](file:///Users/hailinsun/Documents/sunhailin-Leo/github/python-projects/QReward/examples/slime_example/run_qwen2.5_3B.sh) to ensure the path points to the correct file.
3. Point the reward model path in the configuration file to the [multiturn_llm_reward.py](file:///Users/hailinsun/Documents/sunhailin-Leo/github/python-projects/QReward/examples/verl_example/multiturn_llm_reward.py) file, ensuring the function name and parameters are correct.
4. Run the training script using [run_qwen2.5_3B.sh](file:///Users/hailinsun/Documents/sunhailin-Leo/github/python-projects/QReward/examples/slime_example/run_qwen2.5_3B.sh) to start training and evaluating the model.

To implement multi-turn + tool calling, in slime you only need to implement a custom data generation function and a reward model required for the task, corresponding to these 2 configuration items in the startup script:

```bash
CUSTOM_ARGS=(
   --custom-generate-function-path multiturn_llm_reward.generate
   --custom-rm-path multiturn_llm_reward.compute_score
)
```
