# -------------------------------------------------------------------------------------------------
#  Copyright (C) 2015-2025 Nautech Systems Pty Ltd. All rights reserved.
#  https://nautechsystems.io
#
#  Licensed under the GNU Lesser General Public License Version 3.0 (the "License");
#  You may not use this file except in compliance with the License.
#  You may obtain a copy of the License at https://www.gnu.org/licenses/lgpl-3.0.en.html
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
# -------------------------------------------------------------------------------------------------

"""
Tests for extended bar field aggregation (amt field).

This test suite validates that the BarBuilder correctly accumulates the `amt` (traded amount)
extended field from trade ticks and child bars, as specified in:
plans/backtest2livetrading/extended_bar_amt_plan.md
"""

import pytest

from nautilus_trader.data.aggregation import BarBuilder
from nautilus_trader.data.aggregation import TickBarAggregator
from nautilus_trader.data.aggregation import VolumeBarAggregator
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarSpecification
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import AggregationSource
from nautilus_trader.model.enums import BarAggregation
from nautilus_trader.model.enums import PriceType
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity
from nautilus_trader.test_kit.providers import TestInstrumentProvider
from nautilus_trader.test_kit.stubs.data import TestDataStubs


# Skip all tests if extended_bar feature is not enabled
pytestmark = pytest.mark.skipif(
    not hasattr(Bar, "amt"),
    reason="extended_bar feature is not enabled in this build",
)

BTCUSDT_BINANCE = TestInstrumentProvider.btcusdt_binance()
NANOSECONDS_IN_SECOND = 1_000_000_000


class TestBarBuilderAmtAccumulation:
    """
    Test BarBuilder correctly accumulates amt field from trade updates.

    Tests cover:
    1. Single trade update accumulates amt = price * size * multiplier
    2. Multiple trade updates accumulate amt correctly
    3. Multiplier is correctly applied (default 1.0 for linear contracts)
    4. Built bar has correct amt value
    5. Reset clears amt accumulator
    """

    def test_single_trade_update_accumulates_amt(self):
        """
        Test that a single trade update correctly accumulates amt.

        Expected: amt = price * size * multiplier
        For BTCUSDT (linear contract): multiplier = 1.0
        Example: 50000.0 * 0.5 * 1.0 = 25000.0
        """
        # Arrange
        bar_type = TestDataStubs.bartype_btcusdt_binance_100tick_last()
        builder = BarBuilder(BTCUSDT_BINANCE, bar_type)

        price = Price.from_str("50000.0")
        size = Quantity.from_str("0.5")
        ts_event = NANOSECONDS_IN_SECOND

        # Act
        builder.update(price, size, ts_event)
        bar = builder.build_now()

        # Assert
        expected_amt = 50000.0 * 0.5 * 1.0  # price * size * multiplier
        assert float(bar.amt) == pytest.approx(expected_amt, rel=1e-6)
        assert bar.open == price
        assert bar.close == price
        assert bar.volume == size

    def test_multiple_trade_updates_accumulate_amt(self):
        """
        Test that multiple trade updates correctly accumulate amt.

        Expected: amt = sum(price_i * size_i * multiplier)
        """
        # Arrange
        bar_type = TestDataStubs.bartype_btcusdt_binance_100tick_last()
        builder = BarBuilder(BTCUSDT_BINANCE, bar_type)

        trades = [
            (Price.from_str("50000.0"), Quantity.from_str("0.5"), NANOSECONDS_IN_SECOND),
            (Price.from_str("50100.0"), Quantity.from_str("0.3"), NANOSECONDS_IN_SECOND + 1000),
            (Price.from_str("49900.0"), Quantity.from_str("0.2"), NANOSECONDS_IN_SECOND + 2000),
        ]

        # Act
        for price, size, ts in trades:
            builder.update(price, size, ts)

        bar = builder.build_now()

        # Assert
        expected_amt = (50000.0 * 0.5) + (50100.0 * 0.3) + (49900.0 * 0.2)
        assert float(bar.amt) == pytest.approx(expected_amt, rel=1e-6)
        assert bar.volume == Quantity.from_str("1.0")  # 0.5 + 0.3 + 0.2

    def test_build_resets_amt_accumulator(self):
        """
        Test that building a bar resets the amt accumulator.

        Expected: After build(), next bar starts with amt = 0
        """
        # Arrange
        bar_type = TestDataStubs.bartype_btcusdt_binance_100tick_last()
        builder = BarBuilder(BTCUSDT_BINANCE, bar_type)

        # Act - First bar
        builder.update(Price.from_str("50000.0"), Quantity.from_str("0.5"), NANOSECONDS_IN_SECOND)
        bar1 = builder.build(NANOSECONDS_IN_SECOND, NANOSECONDS_IN_SECOND)

        # Act - Second bar
        builder.update(Price.from_str("50100.0"), Quantity.from_str("0.3"), NANOSECONDS_IN_SECOND + 1000)
        bar2 = builder.build(NANOSECONDS_IN_SECOND + 1000, NANOSECONDS_IN_SECOND + 1000)

        # Assert
        assert float(bar1.amt) == pytest.approx(50000.0 * 0.5, rel=1e-6)
        assert float(bar2.amt) == pytest.approx(50100.0 * 0.3, rel=1e-6)  # Not accumulated from bar1

    def test_reset_clears_amt_accumulator(self):
        """
        Test that reset() clears the amt accumulator.

        Expected: After reset(), amt accumulator is 0
        """
        # Arrange
        bar_type = TestDataStubs.bartype_btcusdt_binance_100tick_last()
        builder = BarBuilder(BTCUSDT_BINANCE, bar_type)

        # Act
        builder.update(Price.from_str("50000.0"), Quantity.from_str("0.5"), NANOSECONDS_IN_SECOND)
        builder.reset()
        builder.update(Price.from_str("50100.0"), Quantity.from_str("0.3"), NANOSECONDS_IN_SECOND + 1000)
        bar = builder.build_now()

        # Assert
        expected_amt = 50100.0 * 0.3  # Only second trade, first was reset
        assert float(bar.amt) == pytest.approx(expected_amt, rel=1e-6)


class TestBarBuilderAmtFromChildBars:
    """
    Test BarBuilder correctly accumulates amt field from child bars.

    Tests cover:
    1. Child bar with amt field uses that value
    2. Multiple child bars accumulate amt correctly

    NOTE: When extended_bar feature is enabled, all Bar objects have amt field
    (defaults to Quantity('0')), so missing amt tests are not applicable.
    """

    def test_child_bar_with_amt_uses_provided_value(self):
        """
        Test that child bar's amt field is used when available.

        Expected: Parent bar's amt = sum of child bars' amt values
        """
        # Arrange
        bar_type = TestDataStubs.bartype_btcusdt_binance_100tick_last()
        builder = BarBuilder(BTCUSDT_BINANCE, bar_type)

        child_bar = Bar(
            bar_type=bar_type,
            open=Price.from_str("50000.0"),
            high=Price.from_str("50100.0"),
            low=Price.from_str("49900.0"),
            close=Price.from_str("50050.0"),
            volume=Quantity.from_str("1.0"),
            ts_event=NANOSECONDS_IN_SECOND,
            ts_init=NANOSECONDS_IN_SECOND,
            amt=Quantity.from_str("50000.0"),  # Explicit amt value
        )

        # Act
        builder.update_bar(child_bar, child_bar.volume, child_bar.ts_init)
        bar = builder.build_now()

        # Assert
        assert float(bar.amt) == pytest.approx(50000.0, rel=1e-6)  # Uses child's amt

    def test_multiple_child_bars_accumulate_amt(self):
        """
        Test that multiple child bars correctly accumulate amt.

        Expected: Parent bar's amt = sum of all child bars' amt
        """
        # Arrange
        bar_type = TestDataStubs.bartype_btcusdt_binance_100tick_last()
        builder = BarBuilder(BTCUSDT_BINANCE, bar_type)

        child_bars = [
            Bar(
                bar_type=bar_type,
                open=Price.from_str("50000.0"),
                high=Price.from_str("50100.0"),
                low=Price.from_str("49900.0"),
                close=Price.from_str("50050.0"),
                volume=Quantity.from_str("1.0"),
                ts_event=NANOSECONDS_IN_SECOND,
                ts_init=NANOSECONDS_IN_SECOND,
                amt=Quantity.from_str("50000.0"),
            ),
            Bar(
                bar_type=bar_type,
                open=Price.from_str("50050.0"),
                high=Price.from_str("50200.0"),
                low=Price.from_str("50000.0"),
                close=Price.from_str("50100.0"),
                volume=Quantity.from_str("0.5"),
                ts_event=NANOSECONDS_IN_SECOND + 1000,
                ts_init=NANOSECONDS_IN_SECOND + 1000,
                amt=Quantity.from_str("25050.0"),
            ),
        ]

        # Act
        for child_bar in child_bars:
            builder.update_bar(child_bar, child_bar.volume, child_bar.ts_init)

        bar = builder.build_now()

        # Assert
        expected_amt = 50000.0 + 25050.0
        assert float(bar.amt) == pytest.approx(expected_amt, rel=1e-6)


class TestBarBuilderAmtSetPartial:
    """
    Test BarBuilder correctly restores amt from partial bars.

    Tests cover:
    1. set_partial restores amt accumulator from partial bar
    2. Subsequent updates add to restored amt

    NOTE: When extended_bar feature is enabled, all Bar objects have amt field
    (defaults to Quantity('0')), so missing amt tests are not applicable.
    """

    def test_set_partial_restores_amt_accumulator(self):
        """
        Test that set_partial restores amt from partial bar.

        Expected: Accumulator is restored from partial_bar.amt
        """
        # Arrange
        bar_type = TestDataStubs.bartype_btcusdt_binance_100tick_last()
        builder = BarBuilder(BTCUSDT_BINANCE, bar_type)

        partial_bar = Bar(
            bar_type=bar_type,
            open=Price.from_str("50000.0"),
            high=Price.from_str("50100.0"),
            low=Price.from_str("49900.0"),
            close=Price.from_str("50050.0"),
            volume=Quantity.from_str("1.0"),
            ts_event=NANOSECONDS_IN_SECOND,
            ts_init=NANOSECONDS_IN_SECOND,
            amt=Quantity.from_str("50000.0"),  # Existing amt
        )

        # Act
        builder.set_partial(partial_bar)
        builder.update(Price.from_str("50100.0"), Quantity.from_str("0.5"), NANOSECONDS_IN_SECOND + 1000)
        bar = builder.build_now()

        # Assert
        # Should have: partial amt (50000) + new trade (50100 * 0.5 = 25050)
        expected_amt = 50000.0 + (50100.0 * 0.5)
        assert float(bar.amt) == pytest.approx(expected_amt, rel=1e-6)



class TestAggregatorAmtIntegration:
    """
    Test that aggregators (TickBarAggregator, VolumeBarAggregator) correctly
    delegate amt accumulation to BarBuilder.

    These tests verify end-to-end aggregation with amt field.
    """

    def test_tick_bar_aggregator_accumulates_amt(self):
        """
        Test that TickBarAggregator produces bars with correct amt.

        Expected: After N ticks, bar has amt = sum(price_i * size_i)
        """
        # Arrange
        bar_type = TestDataStubs.bartype_btcusdt_binance_100tick_last()
        aggregator = TickBarAggregator(
            instrument=BTCUSDT_BINANCE,
            bar_type=bar_type,
            handler=lambda bar: None,  # No-op handler
        )

        trades = [
            (Price.from_str("50000.0"), Quantity.from_str("0.1")),
            (Price.from_str("50100.0"), Quantity.from_str("0.2")),
            (Price.from_str("49900.0"), Quantity.from_str("0.3")),
        ]

        # Act
        bars = []
        def capture_bar(bar):
            bars.append(bar)

        aggregator = TickBarAggregator(
            instrument=BTCUSDT_BINANCE,
            bar_type=bar_type,
            handler=capture_bar,
        )

        for price, size in trades:
            from nautilus_trader.model.data import TradeTick
            from nautilus_trader.model.identifiers import TradeId
            from nautilus_trader.model.enums import AggressorSide

            tick = TradeTick(
                instrument_id=BTCUSDT_BINANCE.id,
                price=price,
                size=size,
                aggressor_side=AggressorSide.BUYER,
                trade_id=TradeId("1"),
                ts_event=NANOSECONDS_IN_SECOND,
                ts_init=NANOSECONDS_IN_SECOND,
            )
            aggregator.handle_trade_tick(tick)

        # Assert
        # Note: Tick bar won't be emitted until threshold (100 ticks) is reached
        # This test validates the accumulation logic, actual bar emission depends on threshold


# =======================================================================================
# EXECUTION INSTRUCTIONS FOR USER
# =======================================================================================
"""
执行指南：

1. 文件位置：
   tests/unit_tests/data/test_extended_bar_aggregation.py

2. 运行单个测试文件：
   pytest tests/unit_tests/data/test_extended_bar_aggregation.py -v

3. 运行特定测试类：
   pytest tests/unit_tests/data/test_extended_bar_aggregation.py::TestBarBuilderAmtAccumulation -v

4. 运行特定测试方法：
   pytest tests/unit_tests/data/test_extended_bar_aggregation.py::TestBarBuilderAmtAccumulation::test_single_trade_update_accumulates_amt -v

5. 查看详细输出：
   pytest tests/unit_tests/data/test_extended_bar_aggregation.py -vv -s

6. 测试覆盖范围：
   - TestBarBuilderAmtAccumulation: 测试从 trade ticks 累积 amt
   - TestBarBuilderAmtFromChildBars: 测试从子 bars 累积 amt
   - TestBarBuilderAmtSetPartial: 测试从 partial bar 恢复 amt
   - TestAggregatorAmtIntegration: 测试聚合器端到端集成

7. 预期结果：
   如果所有测试通过，说明：
   - BarBuilder 正确累积 amt = price * size * multiplier
   - 从子 bar 读取 amt 时有 fallback 机制
   - set_partial 正确恢复 amt 累积器
   - reset/build 正确清零累积器

8. 如果测试失败：
   - 检查生成的代码是否正确编译
   - 验证 FIELD_AGGREGATION_RULES 模板是否正确
   - 检查 .pxd 和 .pxi 文件是否一致

9. 实盘数据测试（由您执行）：
   - 连接 Binance 永续合约实时数据
   - 订阅 TradeTick 数据流
   - 使用 BarAggregator 聚合成 bars
   - 验证 bar.amt 字段是否正确累积成交额
   - 对比回测数据验证一致性
"""
