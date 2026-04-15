# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

QReward is a Python acceleration library for RL (Reinforcement Learning) reward processes. It addresses compute capacity shortage and concurrency rate-limiting issues by integrating multiple cloud compute services with intelligent scheduling and request optimization strategies. Key capabilities:

- **OpenAI-compatible API proxy** with connection pooling, rate limiting, and concurrency control
- **Intelligent retry mechanism** with exponential backoff, jitter, and error-type-based retry
- **Smart scheduling** (`schedule` decorator) with hedged requests, overload detection, and multi-source failover
- **HTTP optimization** including JSON serialization monkey-patching (ujson/orjson), TCP keepalive, and connection reuse
- **Framework integration** with [verl](https://github.com/volcengine/verl) and [slime](https://github.com/BAIR-RLHF/slime) RL frameworks

## Quick Reference

### Package Management
- Uses `pip` / `setuptools` for packaging (with `uv` dev-dependencies in `pyproject.toml`)
- Python version: >= 3.10

### Common Commands
```bash
# Testing
pytest -n auto -v tests/                     # Run all tests (parallel)
pytest tests/test_file.py::test_name         # Run specific test
pytest --cov=. --cov-report=term-missing     # Run with coverage (default via pyproject.toml addopts)

# Build & Install
python setup.py sdist bdist_wheel            # Build wheel
make install                                 # Build and install
make reinstall                               # Uninstall and reinstall

# Linting & Formatting
make lint                                    # Run flake8
flake8 --exclude=build,examples,.venv        # Flake8 directly
black qreward/ tests/                        # Format code (max line 88)
mypy qreward/                                # Type checking (strict mode)
ruff check qreward/                          # Ruff linter
```

## Architecture

### Source Structure
```
qreward/
├── __init__.py               # Package entry: exports client, utils
├── _version.py               # Version: 0.1.6
├── globals.py                # Overload exception/keyword constants
├── types.py                  # Type aliases (SOCKET_OPTION, RetryPredicate, etc.)
│
├── client/                   # OpenAI API proxy layer
│   ├── __init__.py           # Exports OpenAIChatProxy, OpenAIChatProxyManager
│   ├── openai.py             # Core proxy: chat completion, embeddings, batch calls
│   └── patch_openai.py       # Runtime patch for OpenAI Embeddings SDK
│
└── utils/                    # Utility modules
    ├── __init__.py            # Exports schedule, retry, patch_httpx, keepalive utils
    ├── patch.py               # httpx JSON serialization monkey-patch (ujson/orjson)
    ├── retry.py               # Sync/async retry decorator with exponential backoff
    ├── schedule.py            # Smart scheduling: LimiterPool, RunningTaskPool, hedged requests
    └── socket_keepalive.py    # TCP keepalive for aiohttp/httpx/requests
```

### Key Patterns
- **Concurrency control**: `asyncio.Semaphore` + `aiolimiter.AsyncLimiter` for rate limiting
- **Retry**: `tenacity` for OpenAI client retries; custom `retry` decorator for general use
- **Scheduling**: `schedule` decorator with overload detection, hedged requests, and multi-source failover
- **Monkey-patching**: Runtime patches for httpx JSON encoding/decoding and OpenAI Embeddings SDK
- **Type hints**: Required for all public functions; `mypy --strict` enforced

## Code Style Summary

- **Formatting**: Black (max line length: 88 chars)
- **Imports**: PEP 8 order (stdlib → third-party → local)
- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants
- **Docstrings**: Google-style for all public functions/classes
- **Testing**: pytest with fixtures; pytest-asyncio for async tests; pytest-xdist for parallel execution
- **Type checking**: mypy strict mode enabled

## Dependencies

### Runtime
- `openai` (>= 1.102.0) — OpenAI SDK
- `aiohttp` — Async HTTP client
- `httpx` + `httpx-aiohttp` — HTTP client with aiohttp backend
- `aiodns` — Async DNS resolver
- `tenacity` — Retry library
- `aiolimiter` — Async rate limiter
- `requests` — Sync HTTP client
- `ujson` — Fast JSON serialization

### Dev
- `pytest`, `pytest-xdist`, `pytest-asyncio`, `pytest-cov`, `coverage`
- `mypy`, `flake8`, `black`, `ruff`

## Examples

- **Normal usage**: `examples/normal/` — single call, batch call
- **Schedule decorator**: `examples/schedule/` — debug, default values, hedged request, limit, retry, sync
- **verl integration**: `examples/verl_example/` — multi-turn LLM reward with GRPO
- **slime integration**: `examples/slime_example/` — multi-turn LLM reward

## Known Constraints

- `qreward/client/openai.py` is 459 lines (exceeds 400-line guideline)
- `qreward/utils/schedule.py` is 1028 lines (exceeds 400-line guideline)
- `flake8` has per-file ignore for `schedule.py: E501`

---

## Harness 开发模式

> **重要**：本项目采用 Harness 开发模式管理所有功能开发的完整生命周期。

### 强制启动仪式

收到任何涉及 **sprint / harness / 合约 / 评估 / 需求开发** 的任务时，或修改 `qreward/`、`tests/`、`examples/` 路径下的代码时，**必须先读取以下 3 个文件**：

```bash
read_file .harness/README.md
read_file .harness/prompts/generator.md
read_file .harness/prompts/evaluator.md
```

### 三 Agent 架构执行顺序

```
Step 1: [Planner]    需求分析 → 扩展为完整技术规格
Step 2: [Generator]  写 sprint-N-contract.md（合约先行）
Step 3: [Evaluator]  独立审查合约（sub agent，怀疑视角）
Step 4: ⏸️ 用户确认   与用户讨论合约，等待用户确认
Step 5: [Generator]  实现代码
Step 6: ⚠️ 全量回归   pytest --cov=qreward
Step 7: [Evaluator]  执行评估脚本 + 独立代码审查
Step 8: 评分判定     ≥ 90 → 继续；< 90 → 修复后重跑（最多 3 轮）
```

### 关键约束

- **禁止跳过合约阶段**：必须先写合约、经 Evaluator 审查、用户确认后才能实现
- **禁止"就近验证"**：回归测试必须跑全量 `pytest --cov=qreward`，禁止只跑修改涉及的文件
- **评分通过阈值**：90 分（满分 100）
- **独立 Evaluator**：使用 sub agent 以怀疑论者视角独立审查，不受 Generator 自评影响

### 豁免场景

以下场景不触发 Harness：
- 纯文档修改（`.md` 文件）
- 配置文件调整（`.gitignore`、`pyproject.toml` 等）
- CI/CD 脚本修改
- 纯重构（不改变外部行为）

### Harness 文件结构

详见 `.harness/README.md`。
