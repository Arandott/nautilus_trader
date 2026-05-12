# Chapter 2 Source Notes

用途：

- 本文件保留第二章草稿中的文献占位、事实核对点和与实现对齐的备注。
- 这些内容是后续补文献、统一术语和衔接第三到第五章时使用的工作底稿。
- 本文件不是论文正文，不应直接并入章节内容。

## 使用建议

- 正式成稿时，将这里的文献占位统一替换为学校要求的参考文献格式。
- 第二章应保持在“概念界定”和“技术动机”层面，具体代码命名、结构字段和实现细节尽量留到第四章。
- 若第三章或第四章已经固定术语，回头统一第二章用词，避免出现“概念层写法”和“实现层写法”不一致。

## 第二章文献占位建议

1. `[文献待补-1]`
   用于支撑订单簿基本作用、L1/L2/L3分层、L2在信息充分性与维护成本之间的工程折中等基础概念。
   更适合补综述、教材或经典订单簿研究文献。

2. `[文献待补-2]`
   用于支撑 MBP 与 MBO 的组织方式区别，以及聚合盘口状态与订单级状态的差异。
   更适合补微观结构教材、订单簿综述或交易所数据说明文献。

3. `[文献待补-3]`
   用于支撑有序树、动态插删与有序查询在本地维护中的技术动机。
   更适合补数据结构基础资料、系统论文或工程型技术说明。

4. `[文献待补-4]`
   用于支撑缓存局部性、连续内存布局、访问路径紧凑性等对低延迟性能的影响。
   更适合补体系结构、性能工程或工程优化类资料。

## 与后文实现对齐时需复核的点

1. baseline 内部是否要在正文中明确写出具体命名。
   目前第二章已经收敛为“多层组织结构、辅助状态、一般化内部表示”这一层。
   如果第四章准备详细介绍代码命名，再在那里写 `BookLadder`、`BookLevel`、cache、synthetic `order_id` 会更稳。

2. 关于内部映射语义的表述是否要进一步具体化。
   如果后文需要强调 baseline 仍保留从价位聚合信息到更一般内部表示的转换，可以在第四章结合真实代码再落到具体机制。

3. 关于 `L2GridBook` 的措辞是否要继续收紧。
   当前第二章写的是“可结合分页、位图等类似稀疏管理思路”。
   如果第四章实现并未严格使用这些同名机制，建议保持这种抽象写法，不要回退成过实的实现描述。

4. 第二章与第四章的分工边界。
   第二章负责回答“为什么这些路线成立”。
   第四章负责回答“这些路线在本论文系统中如何实现”。

## 可回查的本地材料

1. baseline 建模与分析
   - `plans/cufe_undergradution/baseline/baseline_path_model.md`
   - `plans/cufe_undergradution/baseline/baseline_overhead_hypotheses.md`

2. 正确性与 workload 口径
   - `plans/cufe_undergradution/correctness/correctness_spec.md`
   - `plans/cufe_undergradution/workloads/workload_spec.md`

3. 相关实现文件
   - `crates/model/src/orderbook/l2.rs`
   - `crates/model/src/orderbook/l2_vec.rs`
   - `crates/model/src/orderbook/l2_grid.rs`

4. 实验与状态材料
   - `cufe_undergraduate_playground/thesis/brainstorm/2026-04-09_l2_orderbook_engineering_status.md`
   - `cufe_undergraduate_playground/results/comparisons/all_books_subset_10m_r3_q100_q1000/summaries/all_books_summary.md`

## 后续整合提醒

- 第二章正文已经去掉了作者备注，更适合并入论文总稿。
- 如果你后面要统一全文参考文献，我可以继续把本文件整理成：
  - 编号版文献清单
  - GB/T 7714 初稿
  - “正文句子 -> 参考文献条目”的映射表
