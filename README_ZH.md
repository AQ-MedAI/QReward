<h1 align="center">QReward</h1>
<p align="center">
   <em>AQ ✖️️ Reward = QReward</em>
</p>

<p align="center">
   <a href="https://github.com/AQ-MedAI/QReward/actions">
      <img src="https://github.com/AQ-MedAI/QReward/actions/workflows/python-app.yml/badge.svg" alt="Github Actions Status">
   </a>
   <a href="https://coverage-badge.samuelcolvin.workers.dev/redirect/AQ-MedAI/QReward" target="_blank">
      <img src="https://coverage-badge.samuelcolvin.workers.dev/AQ-MedAI/QReward.svg" alt="Coverage">
   </a>
   <a href="https://badge.fury.io/py/qreward">
      <img src="https://badge.fury.io/py/qreward.svg" alt="PyPI version">
   </a>
   <a href="https://pypi.org/project/qreward/">
      <img src="https://img.shields.io/pypi/pyversions/qreward.svg?colorB=brightgreen" alt="PyPI - Python Version">
   </a>
   <a href="https://img.shields.io/github/repo-size/AQ-MedAI/QReward">
      <img src="https://img.shields.io/github/repo-size/AQ-MedAI/QReward" alt="GitHub repo size">
   </a>
</p>
<p align="center">
   <a href="https://pypi.org/project/qreward">
      <img src="https://img.shields.io/pypi/format/qreward.svg" alt="PyPI - Format">
   </a>
   <a href="https://github.com/AQ-MedAI/QReward/pulls">
      <img src="https://img.shields.io/badge/contributions-welcome-brightgreen.svg?style=flat" alt="Contributions welcome">
   </a>
   <a href="https://github.com/AQ-MedAI/QReward/LICENSE">
      <img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License">
   </a>
</p>

[English README](README.md)

## 📣 介绍 & 背景

该功能旨在解决现有 RL reward 过程中的算力不足和并发限流问题，通过整合多个云算力服务，结合智能调度与请求优化策略，实现算力资源的最大化利用与任务执行时间的显著缩短。
系统会根据实时的算力可用情况、限流阈值、任务优先级，自动决定请求分发方式，避免无效的退避等待，并提高总吞吐率。

当前 RL reward 过程耗时问题的主要原因有三方面：

1. Python 并发请求触发限流失败

   * 并发量过高触发了算力服务的限流机制。
   * 一旦发生限流，调用端会执行退避（backoff）策略，减少活跃请求数量。
   * 结果是模型云服务的可用算力没有被充分利用，造成潜在的资源浪费。

2. 模型云服务算力不足

   * 单靠模型云服务无法满足全部算力需求，导致任务排队和处理延迟增加。
   * 需要引入其他算力服务进行补充，并设计合理的调度策略，将任务动态高效地分配到不同算力资源，从而缓解算力瓶颈。

3. 任务执行流程非最优，存在不必要的序列化阶段

   * RL reward 的部分子任务在逻辑上可并行，但目前实现中是串行执行，导致整体耗时增加。
   * 缺乏异步任务/流水线处理优化，I/O 等待和计算混合不合理。

## ✨ 特性

除了支持 Verl、Slime 等，还可以给通用函数进行加速。

1. HTTP 调用优化

   * 连接复用：通过 HTTP Keep-Alive 或连接池减少握手延迟和频繁新建连接的开销。
   * 批量请求：将多个小请求合并为批量请求，降低请求频次和网络开销。
   * 并发控制：智能调整并发度，避免触发模型云服务的限流阈值，同时保持高利用率。

2. 智能重试机制

   * 基于错误类型的重试：针对超时、临时网络故障等可恢复错误快速重试；对不可恢复错误不浪费请求资源。
   * 指数退避优化：在退避间隔中引入算力利用率监控，动态决定等待时间，防止长期资源闲置。
   * 多算力源重试：优先在可用算力服务间尝试重发，减少单一服务瓶颈。

3. 多源算力调度（Coming soon👀）

   * 引入模型云服务以外的算力资源，形成算力池，并通过调度算法实现任务动态分配。
   * 按任务优先级、延迟敏感度、算力负载均衡进行优化调度。

## 📒 更新日志

[CHANGELOG.md](CHANGELOG_ZH.md)
 
## 🔰 安装

**pip 安装**
```bash
pip install qreward
```

**源码安装**
```shell
# normal way to install from source code
$ git clone https://github.com/AQ-MedAI/QReward.git
$ cd QReward
$ pip install -r requirements.txt
$ python setup.py install

# or you can use make file
$ make install
```

## 📝 使用

### 纯加速方式

* [单次调用](examples/normal/single_call.py) — 基础 OpenAI 代理使用（单次请求、上下文管理器、代理管理器）
* [批量调用](examples/normal/batch_call.py) — 批量聊天完成和批量 Embedding 调用

### Schedule 调度装饰器

| 功能 | 示例 | 关键参数 |
|------|------|----------|
| **同步函数** | [schedule_sync.py](examples/schedule/schedule_sync.py) | `retry_times` |
| **调试日志** | [schedule_debug.py](examples/schedule/schedule_debug.py) | `debug=True` |
| **超时控制** | [schedule_timeout.py](examples/schedule/schedule_timeout.py) | `timeout`（整体执行截止时间，单位秒） |
| **限流控制** | [schedule_limit.py](examples/schedule/schedule_limit.py) | `limit_size`, `key_func` |
| **重试与加速** | [schedule_retry.py](examples/schedule/schedule_retry.py) | `retry_times`, `exception_types`, `retry_interval` |
| **默认值** | [schedule_default_value.py](examples/schedule/schedule_default_value.py) | `default_result`（固定值、None 或函数） |
| **对冲请求** | [schedule_hedged_request.py](examples/schedule/schedule_hedged_request.py) | `hedged_request_time`, `hedged_request_max_times` |
| **熔断器** | [schedule_circuit_breaker.py](examples/schedule/schedule_circuit_breaker.py) | `circuit_breaker_threshold`, `circuit_breaker_recovery` |
| **自适应限流** | [schedule_adaptive_limit.py](examples/schedule/schedule_adaptive_limit.py) | `adaptive_limit=True`, `adaptive_error_threshold` |
| **指标回调** | [schedule_metrics_callback.py](examples/schedule/schedule_metrics_callback.py) | `metrics_callback` |
| **优先级队列** | [schedule_priority.py](examples/schedule/schedule_priority.py) | `priority`（HIGH / NORMAL / LOW） |
| **OpenTelemetry** | [schedule_telemetry.py](examples/schedule/schedule_telemetry.py) | `telemetry_exporter` |
| **配置热更新** | [schedule_config_hot_reload.py](examples/schedule/schedule_config_hot_reload.py) | `ScheduleConfig`, `ConfigWatcher` |
| **多功能组合** | [schedule_combined.py](examples/schedule/schedule_combined.py) | 所有功能协同使用 |

### Client（多源算力调度）

| 功能 | 示例 | 关键概念 |
|------|------|----------|
| **负载均衡** | [client_load_balancer.py](examples/client/client_load_balancer.py) | `ROUND_ROBIN`、`WEIGHTED_ROUND_ROBIN`、`mark_unhealthy`、故障转移 |
| **模型路由** | [client_model_router.py](examples/client/client_model_router.py) | `register_model_route`、通配符匹配（`gpt-*`）、分组策略 |
| **流式响应** | [client_streaming.py](examples/client/client_streaming.py) | `stream_chat_completion`、逐 token 输出 |
| **批量流式** | [client_batch_streaming.py](examples/client/client_batch_streaming.py) | `batch_stream_chat_completion`、`max_concurrent_streams`、`on_stream_error` |

### 框架集成

* 结合 ROLL 框架使用示例: [Examples](examples/roll_example) — 通过远程 API 实现 LLM-as-Judge Reward，支持负载均衡
* 结合 Verl 框架使用示例: [Examples](examples/verl_example)
* 结合 Slime 框架使用示例: [Examples](examples/slime_example)

## ⛏ 代码质量

### 单元测试

```shell
$ pip install -r tests/requirements.txt
$ make
```

## 😉 Author

QReward 主要由以下几位开发者开发维护

* [@sunhailin-Leo](https://github.com/sunhailin-Leo)
* [@Vignetting](https://github.com/Vignetting)

更多贡献者信息可以访问 [QReward/graphs/contributors](https://github.com/AQ-MedAI/QReward/graphs/contributors)

## 💡 贡献

期待能有更多的开发者参与到 QReward 的开发中来，我们会保证尽快 Review PR 并且及时回复。但提交 PR 请确保

1. 通过所有单元测试，如若是新功能，请为其新增单元测试
2. 遵守开发规范，使用 black 以及 flake8 格式化代码（$ pip install -r requirements-dev.txt）
3. 如若需要，请更新相对应的文档

## 📃 License

Apache 2.0 [©AQ-MedAI](LICENSE)
