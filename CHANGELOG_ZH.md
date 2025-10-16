### version 0.1.6 - 2025/10/16 (Current)

#### 新增功能 (New Features)
* 增加 example 代码，展示使用 schedule 装饰器
* 增加 httpx 的 json monkey patch
  * 可以通过环境变量 JSON_LIB 控制使用 ujson 或 orjson
* 利用 httpx 的 hook 方式增加自定义 path 的使用
* 增加 patch_openai，用于兼容自定义 embedding 接口的返回格式

#### 性能优化 (Performance Optimization)
* 更新 hedged_request_proportion 默认值

#### 文档与测试 (Documentation & Testing)
* 添加单元测试代码

#### 移除功能 (Removed Features)
* 移除 speed_up_retry，替换为 schedule
* 移除 embeddings 相关接口中 custom_url 的参数

---

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