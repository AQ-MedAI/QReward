### version 0.1.6 - 2025/10/16 (Current)

#### New Features
* Added example code to demonstrate the usage of the `schedule` decorator
* Added json monkey patch for httpx
  * The environment variable `JSON_LIB` can be used to control whether to use `ujson` or `orjson`
* Utilized httpx hooks to add support for custom paths
* Added `patch_openai` to maintain compatibility with custom embedding interface return formats

#### Performance Optimization
* Updated the default value of `hedged_request_proportion`

#### Documentation & Testing
* Added unit test code

#### Removed Features
* Removed `speed_up_retry`, replaced with `schedule`
* Removed the `custom_url` parameter from embedding-related interfaces

---

### version 0.1.5 - 2025/09/29

#### New Features
* Added `OpenAIChatProxyManager` class for proxy management
* Added keepalive configuration compatible with multiple HTTP frameworks
* Added retry logic
* Added transport configuration to `RewardServiceProxy`
* Added openai proxy functionality
* Added reward service client

#### Performance Optimization
* Optimized `speed_up_retry` functionality
* Introduced aiolimiter for faster task processing (2x+ performance improvement over version 0.1.0)
  * Semaphore controls global concurrency, aiolimiter precisely controls concurrent context
* Concurrency control via semaphore (supporting both large batch and small batch task processing)

#### Documentation & Testing
* Updated reward service interface parameters, usage methods and examples
* Updated examples and project dependencies
* Added unit test coverage (internal version code coverage: 91.56%)

#### Code Quality
* Other code formatting improvements