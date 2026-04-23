# Build Context — QReward

> 累积的架构决策和项目上下文，供 Agent 在每个 Sprint 中参考。

## 项目概述

QReward 是一个面向 RL（强化学习）Reward 流程的 Python 加速库，解决算力不足和并发限流问题：
- OpenAI 兼容 API 代理：连接池、限流、并发控制
- 智能重试：指数退避、抖动、错误类型感知
- 智能调度：hedged request、过载检测、多源 failover
- HTTP 优化：JSON 序列化 monkey-patch（ujson/orjson）、TCP keepalive、连接复用
- 框架集成：verl、slime RL 框架

## 核心设计模式

### 客户端代理
- `OpenAIChatProxy`：封装 AsyncOpenAI，支持 chat completion、embeddings、batch 调用
- `OpenAIChatProxyManager`：管理多个 proxy 实例的字典映射
- 并发控制：`asyncio.Semaphore` + `aiolimiter.AsyncLimiter`

### 智能调度
- `schedule` 装饰器：支持同步/异步函数
- `LimiterPool`：滑动窗口限流器（单例模式）
- `RunningTaskPool`：运行任务池，监控并发度防止过载
- Hedged request：超时后发起冗余请求提升成功率
- 过载检测：HTTP 状态码 + 异常类型 + 关键词 + errno 多维判断

### 重试机制
- `retry` 装饰器：支持同步/异步，指数退避 + 抖动
- `tenacity`：OpenAI 客户端内置重试

### Monkey-patching
- `patch_httpx`：运行时替换 httpx JSON 编解码（ujson/orjson）
- `patch_openai_embeddings`：运行时替换 OpenAI Embeddings SDK 返回类型

## 项目结构

```
qreward/
├── __init__.py               # 包入口：导出 client, utils
├── _version.py               # 版本号：0.1.6
├── globals.py                # 过载异常/关键词常量
├── types.py                  # 类型别名
│
├── client/                   # OpenAI API 代理层
│   ├── __init__.py           # 导出 OpenAIChatProxy, OpenAIChatProxyManager
│   ├── openai.py             # 核心代理：chat completion, embeddings, batch
│   └── patch_openai.py       # OpenAI Embeddings SDK 运行时 patch
│
└── utils/                    # 工具模块
    ├── __init__.py            # 导出 schedule, retry, patch_httpx, keepalive
    ├── patch.py               # httpx JSON 序列化 monkey-patch
    ├── retry.py               # 同步/异步重试装饰器
    ├── schedule.py            # 智能调度：LimiterPool, RunningTaskPool, hedged request
    └── socket_keepalive.py    # TCP keepalive（aiohttp/httpx/requests）
```

## 核心组件

### OpenAIChatProxy
- 位置: `qreward/client/openai.py`
- 职责: OpenAI API 代理，支持 chat completion 和 embeddings
- 并发: `asyncio.Semaphore` + `AsyncLimiter`
- 重试: `tenacity` 装饰器，指数退避

### OpenAIChatProxyManager
- 位置: `qreward/client/openai.py`
- 职责: 管理多个 OpenAIChatProxy 实例
- 模式: 字典映射，key → proxy

### schedule 装饰器
- 位置: `qreward/utils/schedule.py`
- 职责: 智能调度，支持 hedged request、过载检测、多源 failover
- 模式: 装饰器，支持同步/异步函数

### retry 装饰器
- 位置: `qreward/utils/retry.py`
- 职责: 通用重试，支持同步/异步
- 模式: 装饰器，指数退避 + 抖动

## 构建与测试命令

```bash
# 构建
python setup.py sdist bdist_wheel

# 单元测试
pytest --cov=qreward

# 并行测试
pytest -n auto -v tests/

# Lint
make lint

# 格式化
black qreward/ tests/

# 类型检查
mypy qreward/
```

## 已知约束

1. `qreward/client/openai.py` 为 459 行，超过 400 行限制
2. `qreward/utils/schedule.py` 为 1028 行，超过 400 行限制
3. `flake8` 对 `schedule.py` 有 E501 豁免
4. 项目使用 `setuptools` 构建，非 `uv build`

## 依赖

### 运行时
- `openai` (>= 1.102.0) — OpenAI SDK
- `aiohttp` — 异步 HTTP 客户端
- `httpx` + `httpx-aiohttp` — HTTP 客户端
- `aiodns` — 异步 DNS 解析
- `tenacity` — 重试库
- `aiolimiter` — 异步限流器
- `requests` — 同步 HTTP 客户端
- `ujson` — 快速 JSON 序列化

### 开发
- `pytest`, `pytest-xdist`, `pytest-asyncio`, `pytest-cov`, `coverage`
- `mypy`, `flake8`, `black`, `ruff`

## Sprint 历史

（随着 Sprint 完成逐步填充）

| Sprint | 功能 | 日期 | 评分 |
|--------|------|------|------|
| — | 尚无 Sprint | — | — |

## 技术债务

| 编号 | 描述 | 优先级 | 来源 |
|------|------|--------|------|
| TD-1 | `qreward/client/openai.py` 超过 400 行限制（459 行） | P1 | 初始审计 |
| TD-2 | `qreward/utils/schedule.py` 超过 400 行限制（1028 行） | P0 | 初始审计 |
| TD-3 | `openai.py` 中存在 `except Exception as e` 裸捕获 | P2 | 初始审计 |
