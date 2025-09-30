# Usage Documentation under the Verl Framework

## Introduction to Directory Files

* [multiturn_grpo.yaml](file:///Users/hailinsun/Documents/sunhailin-Leo/github/python-projects/QReward/examples/verl_example/multiturn_grpo.yaml) and [multiturn_megatron_grpo.yaml](file:///Users/hailinsun/Documents/sunhailin-Leo/github/python-projects/QReward/examples/verl_example/multiturn_megatron_grpo.yaml) are configuration files under the Verl framework, corresponding to the standard version and Megatron version of the GRPO model respectively.
* [multiturn_llm_reward.py](file:///Users/hailinsun/Documents/sunhailin-Leo/github/python-projects/QReward/examples/verl_example/multiturn_llm_reward.py) is a custom reward model file under the Verl framework used for calculating reward values.

Usage instructions:
1. Ensure that the Verl framework and related dependencies are installed.
2. Point the model path in the [multiturn_grpo.yaml](file:///Users/hailinsun/Documents/sunhailin-Leo/github/python-projects/QReward/examples/verl_example/multiturn_grpo.yaml) or [multiturn_megatron_grpo.yaml](file:///Users/hailinsun/Documents/sunhailin-Leo/github/python-projects/QReward/examples/verl_example/multiturn_megatron_grpo.yaml) configuration file to the pretrained GRPO model.
3. Point the reward model path in the [multiturn_llm_reward.py](file:///Users/hailinsun/Documents/sunhailin-Leo/github/python-projects/QReward/examples/verl_example/multiturn_llm_reward.py) configuration file to this file.
4. Run the configuration file using the Verl framework to start training and evaluating the model.