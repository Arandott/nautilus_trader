# Chapter 1 Source Notes

用途：

- 本文件保留第一章草稿中提到的文献、官方文档与仓库链接线索。
- 这些内容是后续整合参考文献、补全文献编号和核对事实时使用的工作底稿。
- 本文件不是论文正文，不应直接并入章节内容。

## 使用建议

- 正式成稿时，将这里的条目按学校要求统一整理为 GB/T 7714 格式。
- 正文中的引用编号、脚注、访问日期和文献类型标识，应在总稿阶段统一处理。
- 开源仓库、官方文档与学术论文建议分开管理，不要在最终参考文献中混成同一层级。

## 第一章可能使用的学术文献

1. Gould, M. D., Porter, M. A., Williams, S., McDonald, M., Fenn, D. J., & Howison, S. D.
   `Limit order books`. Quantitative Finance, 2013.
   Link: `https://www.tandfonline.com/doi/abs/10.1080/14697688.2013.803148`

2. Cont, R., Stoikov, S., & Talreja, R.
   `A Stochastic Model for Order Book Dynamics`. Operations Research, 2010.
   Link: `https://rama.cont.perso.math.cnrs.fr/pdf/CST2010.pdf`

3. Cont, R., Kukanov, A., & Stoikov, S.
   `The Price Impact of Order Book Events`. Journal of Financial Econometrics, 2014.
   Link: `https://academic.oup.com/jfec/article/12/1/47/816163`

4. Cao, C., Hansch, O., & Wang, X.
   `The information content of an open limit-order book`. Journal of Futures Markets, 2009.
   Link: `https://doi.org/10.1002/fut.20334`

5. Cartea, A., Jaimungal, S., & Penalva, J.
   `Algorithmic and High-Frequency Trading`. Cambridge University Press, 2015.
   Link: `https://books.google.com/books/about/Algorithmic_and_High_Frequency_Trading.html?id=5dMmCgAAQBAJ`

6. Huang, R., & Polak, T.
   `LOBSTER: Limit Order Book Reconstruction System`, 2011.
   Link: `https://data.lobsterdata.com/info/docs/LobsterReport.pdf`

7. Ntakaris, A., Magris, M., Kanniainen, J., Gabbouj, M., & Iosifidis, A.
   `Benchmark dataset for mid-price forecasting of limit order book data with machine learning methods`. Journal of Forecasting, 2018.
   Link: `https://ideas.repec.org/a/wly/jforec/v37y2018i8p852-866.html`

8. Lucchese, L., Pakkanen, M. S., & Veraart, A. E. D.
   `The short-term predictability of returns in order book markets: A deep learning perspective`. International Journal of Forecasting, 2024.
   Link: `https://www.sciencedirect.com/science/article/pii/S0169207024000062`

9. Avellaneda, M., & Stoikov, S.
   `High-frequency trading in a limit order book`. Quantitative Finance, 2008.
   Link: `https://www.tandfonline.com/doi/abs/10.1080/14697680701381228`

## 第一章可能使用的中文文献

1. 刘志东，赵致远.
   《基于状态依赖Hawkes过程的我国股市限价指令簿事件激励效应研究》.
   Link: `https://www.zgglkx.com/CN/10.16381/j.cnki.issn1003-207x.2020.0337`

2. 刘志东，王超.
   《多层级指令流不平衡的价格冲击效应研究》.
   Link: `https://www.zgglkx.com/CN/10.16381/j.cnki.issn1003-207x.2022.2771`

3. 王春峰等.
   对应草稿中提及的早期国内高频订单流冲击研究。
   当前候选链接：`https://journal.bit.edu.cn/sk/article/id/20070217`
   Note: 这一条需要你在总稿时再次核对题名、作者和期刊页信息。

## 第一章可参考的工程资料

1. NautilusTrader
   Repo: `https://github.com/nautechsystems/nautilus_trader`
   Docs: `https://nautilustrader.io/docs/latest/`
   API/book docs candidate:
   - `https://nautilustrader.io/docs/nightly/api_reference/model/book/`
   - `https://nautilustrader.io/docs/latest/concepts/overview/`

2. HftBacktest
   Repo: `https://github.com/nkaz001/hftbacktest`
   Docs: `https://hftbacktest.readthedocs.io/en/latest/`
   Candidate page:
   - `https://mintlify.com/nkaz001/hftbacktest/concepts/order-book`

3. Kungfu Trader
   Repo: `https://github.com/kungfu-origin/kungfu`
   Docs: `https://docs.kungfu-trader.com/latest/`
   Note: 相关能力表述建议在最终定稿前重新人工核对。

4. ITCH reconstruction project
   Repo: `https://github.com/martinobdl/ITCH`

5. Databento schema docs
   Candidate page:
   - `https://databento.com/docs/schemas-and-data-formats/mbp-1`

## 当前建议的引用分工

- 学术论述：
  - 主要使用期刊论文、专著、技术报告
- 工程背景或系统对比：
  - 使用官方文档、仓库 README、技术页面
- 不建议：
  - 在最终正文中直接保留裸链接
  - 把 Repo 和期刊论文混成同类参考文献

## 后续整合提醒

- 第一章已经去掉了这些链接附录，正文会更像论文。
- 如果后面你要统一全文参考文献，我可以再帮你把本文件整理成：
  - 编号版文献清单
  - GB/T 7714 初稿
  - “正文句子 -> 文献条目”的映射表
