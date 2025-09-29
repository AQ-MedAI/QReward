### version 0.1.5 - 2025/09/29

#### 新增功能 (New Features)
* 增加 [OpenAIChatProxyManager](file:///Users/hailinsun/Documents/sunhailin-Leo/github/python-projects/QReward/qreward/client/openai.py#L349-L435) 类，用于管理代理
* 新增 keepalive 配置，兼容多种 http 框架
* 新增 retry 逻辑
* `RewardServiceProxy` 增加 transport 配置
* 新增 openai proxy 功能
* 新增 reward service client

#### 性能优化 (Performance Optimization)
* 优化 [speed_up_retry](file:///Users/hailinsun/Documents/sunhailin-Leo/github/python-projects/QReward/qreward/utils/retry.py#L293-L841) 功能
* 引入 aiolimiter 提速任务处理（相比 0.1.0 版本提升 2 倍以上性能）
  * 信号量控制全局并发，aiolimiter 精准控制并发上下文
* 通过信号量控制并发（支持大批量和小批量任务处理）

#### 文档与测试 (Documentation & Testing)
* 更新 reward service 接口参数、使用方式以及使用示例
* 更新 example 和项目依赖
* 补充单元测试代码（内部版本代码覆盖率：91.56%）

#### 代码质量 (Code Quality)
* 其他代码格式化改进