# workbench-test-repo

> 交付工作台测试专用工程，**不是生产仓库**。所有数据、表名、主机和运行记录均为测试数据。

对应 Linear：RPF-26 / RPA-92。用于验证“飞书多维表写入超时 → 幂等重试 → 读回对账 → 恢复运行”的完整交付闭环。

## 目录

```text
bitable_client.py      最小飞书多维表 HTTP 客户端（测试实现）
callback_service.py    影刀回调 → 多维表更新服务（测试实现）
tests/test_timeout_retry.py  超时、重试、读回测试
```

## 测试目标

- `update_record` 遇到 `TimeoutError` 后不能盲目重试导致重复写入。
- 重试必须复用同一 `client_token`（create 场景）。
- 写超时后必须读回确认 `written / not_written / unknown`。
- 所有测试使用 mock，不访问真实飞书接口。
