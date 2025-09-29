### version 0.1.5 - 2025/09/29

#### New Features
* Added [OpenAIChatProxyManager](file:///Users/hailinsun/Documents/sunhailin-Leo/github/python-projects/QReward/qreward/client/openai.py#L349-L435) class for proxy management
* Added keepalive configuration compatible with multiple HTTP frameworks
* Added retry logic
* Added transport configuration to `RewardServiceProxy`
* Added openai proxy functionality
* Added reward service client

#### Performance Optimization
* Optimized [speed_up_retry](file:///Users/hailinsun/Documents/sunhailin-Leo/github/python-projects/QReward/qreward/utils/retry.py#L293-L841) functionality
* Introduced aiolimiter for faster task processing (2x+ performance improvement over version 0.1.0)
  * Semaphore controls global concurrency, aiolimiter precisely controls concurrent context
* Concurrency control via semaphore (supporting both large batch and small batch task processing)

#### Documentation & Testing
* Updated reward service interface parameters, usage methods and examples
* Updated examples and project dependencies
* Added unit test coverage (internal version code coverage: 91.56%)

#### Code Quality
* Other code formatting improvements