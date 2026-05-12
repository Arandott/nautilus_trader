# Phase 0 Profiling Note

日期：2026-03-23

## 目标

记录 Phase 0 基线 profiling 的可用性、已完成动作和当前限制，避免后续把“没有 flamegraph”说得含糊。

## 当前环境

- 主机内核：`6.14.0-1018-aws`
- `perf` 路径：`/usr/bin/perf`
- 当前状态：`perf` 可执行文件存在，但缺少与当前内核匹配的 `linux-tools`

实际检查结果：

```text
WARNING: perf not found for kernel 6.14.0-1018

You may need to install the following packages for this specific kernel:
  linux-tools-6.14.0-1018-aws
  linux-cloud-tools-6.14.0-1018-aws
```

## Phase 0 已完成的替代手段

- 使用 `criterion` 获得 baseline microbench 的稳定统计结果
- 使用 `tardis-l2-baseline` runner 获得 `parse_only`、`replay_only`、`replay_periodic_query` 的真实 workload 结果
- 将 hotspot 判断约束在已有代码路径与测量结果共同支持的范围内

这意味着当前我们可以较可靠地判断：

- CSV 解析本身已经占据明显成本
- 订单簿应用路径会在此基础上进一步拉低吞吐
- `q=100` 和 `q=1000` 这类低到中频查询，在 baseline 下不是主要瓶颈

但当前我们**不能**声称：

- 某个具体函数已经由 flamegraph 证明是首要热点
- `synthetic order_id` 或 `cache` 的占比已经被采样器直接量化

## 对 Phase 1 的影响

Phase 1 可以继续推进，不需要等待系统级 profiling 环境修好。

理由：

- Phase 0 的目标是建立可信 baseline，而不是完成最终归因
- 当前已有 microbench + replay workload 足以支撑 `L2TreeBook` 第一轮实现
- 等 `L2TreeBook` 出来后，再补系统级 profiling 会更有价值，因为届时可以直接做 baseline / proposed 对照

## 后续补充条件

如果后面需要标准热点图，建议先在机器上补齐：

- `linux-tools-6.14.0-1018-aws`
- `linux-cloud-tools-6.14.0-1018-aws`

补齐后优先运行：

- baseline `replay_only`
- `L2TreeBook replay_only`
- baseline `replay_periodic_query_q100`
- `L2TreeBook replay_periodic_query_q100`

这样拿到的 flamegraph 才能直接服务于优化归因，而不是只说明 baseline 自己“哪里慢”。
