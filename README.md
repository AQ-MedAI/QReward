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

[中文版本](README_ZH.md)

## 📣 Introduction & Background

This feature is designed to address the compute capacity shortage and concurrency rate-limiting issues in the current RL reward process.
By integrating multiple cloud compute services and combining intelligent scheduling with request optimization strategies, it maximizes the utilization of computing resources and significantly reduces task execution time.
The system automatically determines the request distribution method based on real-time compute availability, rate-limit thresholds, and task priorities, thereby avoiding unnecessary backoff delays and improving overall throughput.

There are three main causes for the latency issue in the current RL reward process:

1. Python concurrent requests triggering rate-limit failures

   * Excessive concurrency leads to hitting the rate limits of the compute service.
   * Once rate limiting occurs, the client applies a backoff strategy, reducing the number of active requests.
   * As a result, the available compute capacity of the Model Cloud Service is not fully utilized, causing potential resource underuse.

2. Insufficient Model Cloud Service compute capacity

   * The Model Cloud Service alone cannot meet the total compute demand, resulting in increased task queuing and processing delays.
   * The solution involves introducing additional compute services to supplement capacity and designing an appropriate scheduling strategy to dynamically and efficiently distribute tasks among multiple compute resources, thereby alleviating compute bottlenecks.

3. Non-optimal task execution flow with unnecessary serialization

   * Some subtasks within the RL reward process could be executed in parallel, but the current implementation runs them sequentially, causing increased total latency.
   * Lack of asynchronous or pipeline optimization results in inefficient mixing of I/O waits and computation.


## ✨ Features

Beyond supporting Verl and Slime, the solution also provides acceleration capabilities for general-purpose functions.

1. HTTP Call Optimization

   * Connection reuse: Reduce handshake latency and frequent reconnections using HTTP Keep-Alive or connection pooling.
   * Batch requests: Aggregate multiple small requests into batch calls to reduce request frequency and network overhead.
   * Concurrency control: Intelligently adjust the level of concurrency to avoid hitting rate limits of the Model Cloud Service while maintaining high utilization.

2. Intelligent Retry Mechanism

   * Error-type-based retry: Quickly retry recoverable errors (e.g., timeouts, temporary network failures) while avoiding retries for non-recoverable errors to save resources.
   * Optimized exponential backoff: Integrate compute utilization monitoring into backoff intervals, dynamically deciding wait times to prevent prolonged idle resources.
   * Multi-source retry: Redirect retries to other available compute services to avoid single-service bottlenecks.

3. Multi-compute Scheduling（Coming soon👀）

   * Integrate additional compute resources beyond the Model Cloud Service into a unified compute pool.
   * Optimize distribution based on task priority, latency sensitivity, and load balancing.

## 📒 ChangeLog

[CHANGELOG.md](CHANGELOG.md)

## 🔰 Installation

**pip install**
```bash
pip install qreward
```

**from source code**
```shell
# normal way to install from source code
$ git clone https://github.com/AQ-MedAI/QReward.git
$ cd QReward
$ pip install -r requirements.txt
$ python setup.py install

# or you can use make file
$ make install
```

## 📝 Usage

### Pure Acceleration

* [Single Call](examples/normal/single_call.py) — Basic OpenAI proxy usage (single request, context manager, proxy manager)
* [Batch Call](examples/normal/batch_call.py) — Batch chat completion and batch embedding calls

### Schedule Decorator

| Feature | Example | Key Parameters |
|---------|---------|----------------|
| **Sync Function** | [schedule_sync.py](examples/schedule/schedule_sync.py) | `retry_times` |
| **Debug Logging** | [schedule_debug.py](examples/schedule/schedule_debug.py) | `debug=True` |
| **Timeout** | [schedule_timeout.py](examples/schedule/schedule_timeout.py) | `timeout` (wall-clock deadline in seconds) |
| **Rate Limiting** | [schedule_limit.py](examples/schedule/schedule_limit.py) | `limit_size`, `key_func` |
| **Retry & Speed-up** | [schedule_retry.py](examples/schedule/schedule_retry.py) | `retry_times`, `exception_types`, `retry_interval` |
| **Default Value** | [schedule_default_value.py](examples/schedule/schedule_default_value.py) | `default_result` (value, None, or callable) |
| **Hedged Request** | [schedule_hedged_request.py](examples/schedule/schedule_hedged_request.py) | `hedged_request_time`, `hedged_request_max_times` |
| **Circuit Breaker** | [schedule_circuit_breaker.py](examples/schedule/schedule_circuit_breaker.py) | `circuit_breaker_threshold`, `circuit_breaker_recovery` |
| **Adaptive Limiting** | [schedule_adaptive_limit.py](examples/schedule/schedule_adaptive_limit.py) | `adaptive_limit=True`, `adaptive_error_threshold` |
| **Metrics Callback** | [schedule_metrics_callback.py](examples/schedule/schedule_metrics_callback.py) | `metrics_callback` |
| **Priority Queue** | [schedule_priority.py](examples/schedule/schedule_priority.py) | `priority` (HIGH / NORMAL / LOW) |
| **OpenTelemetry** | [schedule_telemetry.py](examples/schedule/schedule_telemetry.py) | `telemetry_exporter` |
| **Config Hot Reload** | [schedule_config_hot_reload.py](examples/schedule/schedule_config_hot_reload.py) | `ScheduleConfig`, `ConfigWatcher` |
| **Combined Features** | [schedule_combined.py](examples/schedule/schedule_combined.py) | All features working together |

### Client (Multi-Source Scheduling)

| Feature | Example | Key Concepts |
|---------|---------|--------------|
| **Load Balancer** | [client_load_balancer.py](examples/client/client_load_balancer.py) | `ROUND_ROBIN`, `WEIGHTED_ROUND_ROBIN`, `mark_unhealthy`, failover |
| **Model Router** | [client_model_router.py](examples/client/client_model_router.py) | `register_model_route`, glob patterns (`gpt-*`), per-group strategy |
| **Streaming** | [client_streaming.py](examples/client/client_streaming.py) | `stream_chat_completion`, token-by-token output |
| **Batch Streaming** | [client_batch_streaming.py](examples/client/client_batch_streaming.py) | `batch_stream_chat_completion`, `max_concurrent_streams`, `on_stream_error` |

### Framework Integration

* With ROLL Framework: [Examples](examples/roll_example) — LLM-as-Judge reward via remote API with load balancing
* With verl Framework: [Examples](examples/verl_example)
* With slime Framework: [Examples](examples/slime_example)

## ⛏ Code Quality

### Unit Tests

```shell
$ pip install -r tests/requirements.txt
$ make
```

## 😉 Authors

QReward is primarily developed and maintained by the following developers:

* [@sunhailin-Leo](https://github.com/sunhailin-Leo)
* [@Vignetting](https://github.com/Vignetting)

For more contributor information, please visit [QReward/graphs/contributors](https://github.com/AQ-MedAI/QReward/graphs/contributors)

## 💡 Contributing

We look forward to more developers participating in the development of QReward. We will ensure prompt review of PRs and timely responses. However, when submitting a PR, please ensure:

1. Pass all unit tests; if it's a new feature, please add corresponding unit tests
2. Follow development guidelines, format code using black and flake8 (`$ pip install -r requirements-dev.txt`)
3. Update corresponding documentation if necessary

## 📃 License

Apache 2.0 [©AQ-MedAI](LICENSE)
