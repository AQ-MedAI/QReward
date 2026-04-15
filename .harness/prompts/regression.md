# 回归测试模板

## 概述

本模板定义 QReward 项目的回归测试流程，确保每次代码变更不会破坏现有功能。

## 测试维度

### 维度 1: 单元测试

```bash
pytest tests/ -v --tb=short
```

**判定规则**：
- 全部 PASS → ✅
- 任何 FAIL → ❌ 整体 FAIL

### 维度 2: 覆盖率

```bash
pytest --cov=qreward --cov-report=term-missing
```

**判定规则**：
- 总覆盖率 ≥ 80% → ✅
- 增量覆盖率 ≥ 70% → ✅
- 低于阈值 → ⚠️ WARNING

### 维度 3: Lint 检查

```bash
make lint
```

**判定规则**：
- 无错误 → ✅
- 有错误 → ⚠️ WARNING（不阻塞，但记录）

## 报告格式

```markdown
## 回归测试报告

### 执行时间: YYYY-MM-DD HH:MM:SS
### Sprint: N

| 维度 | 状态 | 详情 |
|------|------|------|
| 单元测试 | ✅/❌ | X passed, Y failed |
| 覆盖率 | ✅/⚠️ | 总覆盖率 XX%, 增量 XX% |
| Lint | ✅/⚠️ | X errors, Y warnings |

### 总体判定: PASS / FAIL / WARNING

### 失败详情
（如有失败，列出具体的测试名称和错误信息）
```

## 关键模块覆盖率基线

| 模块 | 最低覆盖率 |
|------|----------|
| `qreward.client.openai` | 80% |
| `qreward.client.patch_openai` | 70% |
| `qreward.utils.retry` | 80% |
| `qreward.utils.schedule` | 70% |
| `qreward.utils.patch` | 70% |
| `qreward.utils.socket_keepalive` | 70% |

## 执行顺序

```
1. Lint 检查（最快，先排除格式问题）
   ↓
2. 单元测试（核心验证）
   ↓
3. 覆盖率分析（质量指标）
```

## 快速回归 vs 完整回归

### 快速回归（Preflight，30 秒）
- Lint 检查
- 构建验证
- 无外部依赖

### 完整回归（Full Regression）
- 所有 3 个维度
- 输出完整报告
