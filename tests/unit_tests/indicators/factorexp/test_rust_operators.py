"""
Unit tests for Rust operator implementations.

Tests verify that Rust operators produce identical results to NumPy implementations
and maintain API compatibility.
"""

import pytest
import numpy as np
from typing import List

# Try to import Rust operators
try:
    from nautilus_trader.indicators.factorexp.core.rust_bridge import (
        create_streaming_computation,
        RustBridge,
        enhanced_bridge,
    )
    RUST_AVAILABLE = RustBridge.is_available()
except ImportError:
    RUST_AVAILABLE = False

# Import Python implementations for comparison
from nautilus_trader.indicators.factorexp.core.bridge import StreamingBridge
from nautilus_trader.indicators.factorexp.operators.rolling import (
    StreamingSkew,
    StreamingKurtosis,
    StreamingEMA,
    StreamingWMA,
)


@pytest.mark.skipif(not RUST_AVAILABLE, reason="Rust operators not available")
class TestRustOperators:
    """Test suite for Rust operator implementations."""
    
    @pytest.fixture
    def test_data(self) -> List[float]:
        """Generate test data."""
        np.random.seed(42)
        # Mix of different patterns
        trend = np.linspace(100, 150, 100)
        noise = np.random.normal(0, 2, 100)
        return (trend + noise).tolist()
    
    @pytest.fixture
    def simple_data(self) -> List[float]:
        """Simple test data for debugging."""
        return [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    
    def test_mean_operator(self, test_data):
        """Test TS_Mean operator."""
        window = 20
        
        # Python version
        py_op = StreamingBridge.create_computation("TS_Mean", window)
        
        # Rust version
        rust_op = create_streaming_computation("TS_Mean", window, use_rust=True)
        
        for value in test_data:
            py_result = py_op.update(value)
            rust_result = rust_op.update(value)
            
            if py_result is not None and rust_result is not None:
                assert abs(py_result - rust_result) < 1e-10, \
                    f"Results differ: Python={py_result}, Rust={rust_result}"
    
    def test_std_operator(self, test_data):
        """Test TS_Std operator with different ddof values."""
        window = 20
        
        for ddof in [0, 1]:
            # Python version
            py_op = StreamingBridge.create_computation("TS_Std", window, ddof=ddof)
            
            # Rust version
            rust_op = create_streaming_computation("TS_Std", window, use_rust=True, ddof=ddof)
            
            for value in test_data:
                py_result = py_op.update(value)
                rust_result = rust_op.update(value)
                
                if py_result is not None and rust_result is not None:
                    assert abs(py_result - rust_result) < 1e-10, \
                        f"Std differs (ddof={ddof}): Python={py_result}, Rust={rust_result}"
    
    def test_min_max_operators(self, test_data):
        """Test TS_Min and TS_Max operators."""
        window = 20
        
        # Min
        py_min = StreamingBridge.create_computation("TS_Min", window)
        rust_min = create_streaming_computation("TS_Min", window, use_rust=True)
        
        # Max
        py_max = StreamingBridge.create_computation("TS_Max", window)
        rust_max = create_streaming_computation("TS_Max", window, use_rust=True)
        
        for value in test_data:
            py_min_result = py_min.update(value)
            rust_min_result = rust_min.update(value)
            
            py_max_result = py_max.update(value)
            rust_max_result = rust_max.update(value)
            
            if py_min_result is not None and rust_min_result is not None:
                assert abs(py_min_result - rust_min_result) < 1e-10
            
            if py_max_result is not None and rust_max_result is not None:
                assert abs(py_max_result - rust_max_result) < 1e-10
    
    def test_ema_operator(self, test_data):
        """Test TS_EMA operator."""
        window = 20
        
        # Python version
        py_op = StreamingEMA(window)
        
        # Rust version
        rust_op = create_streaming_computation("TS_EMA", window, use_rust=True)
        
        for value in test_data:
            py_result = py_op.update(value)
            rust_result = rust_op.update(value)
            
            if py_result is not None and rust_result is not None:
                # EMA can have small numerical differences due to different implementations
                assert abs(py_result - rust_result) < 1e-8, \
                    f"EMA differs: Python={py_result}, Rust={rust_result}"
    
    def test_skewness_operator(self, simple_data):
        """Test TS_Skew operator."""
        window = 5
        
        # Python version
        py_op = StreamingSkew(window)
        
        # Rust version
        rust_op = create_streaming_computation("TS_Skew", window, use_rust=True)
        
        results = []
        for value in simple_data:
            py_result = py_op.update(value)
            rust_result = rust_op.update(value)
            
            if py_result is not None and rust_result is not None:
                # Skewness can have larger numerical differences
                assert abs(py_result - rust_result) < 1e-6, \
                    f"Skew differs: Python={py_result}, Rust={rust_result}"
                results.append((py_result, rust_result))
        
        # Should have results after window is full
        assert len(results) >= len(simple_data) - window + 1
    
    def test_operator_reset(self):
        """Test operator reset functionality."""
        window = 5
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        
        rust_op = create_streaming_computation("TS_Mean", window, use_rust=True)
        
        # Fill buffer
        for value in data:
            rust_op.update(value)
        
        assert rust_op.is_ready
        first_value = rust_op.value
        
        # Reset
        rust_op.reset()
        assert not rust_op.is_ready
        assert rust_op.value is None
        
        # Fill again
        for value in data:
            rust_op.update(value)
        
        assert rust_op.value == first_value
    
    def test_all_supported_operators(self):
        """Test that all advertised operators are available."""
        expected_operators = [
            "TS_Mean", "TS_Sum", "TS_Std", "TS_Var",
            "TS_Min", "TS_Max", "TS_Med", "TS_Delta",
            "TS_EMA", "TS_WMA", "TS_Skew", "TS_Kurt",
            "TS_Mad", "TS_Product", "TS_PctChg",
        ]
        
        for op_name in expected_operators:
            assert RustBridge.supports_operator(op_name), \
                f"Operator {op_name} not supported"
            
            # Try to create it
            op = create_streaming_computation(op_name, 10, use_rust=True)
            assert op is not None, f"Failed to create {op_name}"
    
    def test_performance_improvement(self, test_data):
        """Verify that Rust operators are actually faster."""
        import time
        
        window = 20
        iterations = 10
        
        # Warm up
        for _ in range(2):
            py_op = StreamingBridge.create_computation("TS_Mean", window)
            rust_op = create_streaming_computation("TS_Mean", window, use_rust=True)
            for value in test_data:
                py_op.update(value)
                rust_op.update(value)
        
        # Python timing
        py_times = []
        for _ in range(iterations):
            py_op = StreamingBridge.create_computation("TS_Mean", window)
            start = time.perf_counter()
            for value in test_data:
                py_op.update(value)
            py_times.append(time.perf_counter() - start)
        
        # Rust timing
        rust_times = []
        for _ in range(iterations):
            rust_op = create_streaming_computation("TS_Mean", window, use_rust=True)
            start = time.perf_counter()
            for value in test_data:
                rust_op.update(value)
            rust_times.append(time.perf_counter() - start)
        
        avg_py_time = np.mean(py_times)
        avg_rust_time = np.mean(rust_times)
        speedup = avg_py_time / avg_rust_time
        
        print(f"\nPerformance test results:")
        print(f"  Python: {avg_py_time*1000:.3f} ms")
        print(f"  Rust:   {avg_rust_time*1000:.3f} ms")
        print(f"  Speedup: {speedup:.1f}x")
        
        # Rust should be at least 5x faster
        assert speedup > 5.0, f"Insufficient speedup: {speedup:.1f}x"
    
    def test_enhanced_bridge_statistics(self, simple_data):
        """Test enhanced bridge statistics tracking."""
        bridge = enhanced_bridge
        bridge._rust_stats = {"attempts": 0, "successes": 0, "fallbacks": 0}
        
        # Create a Rust operator
        op = bridge.create_computation("TS_Mean", 5)
        for value in simple_data:
            op.update(value)
        
        stats = bridge.get_statistics()
        assert stats["rust_available"]
        assert stats["rust_enabled"]
        assert stats["stats"]["attempts"] > 0
        assert stats["stats"]["successes"] > 0
        
        # Try an unsupported operator (should fallback)
        try:
            unsupported_op = bridge.create_computation("TS_Unsupported", 5)
        except ValueError:
            pass
        
        print(f"\nBridge statistics: {stats}")


@pytest.mark.skipif(not RUST_AVAILABLE, reason="Rust operators not available")
def test_rust_operator_edge_cases():
    """Test edge cases for Rust operators."""
    
    # Empty window
    op = create_streaming_computation("TS_Mean", 5, use_rust=True)
    assert op.value is None
    assert not op.is_ready
    
    # Single value
    op.update(42.0)
    assert not op.is_ready  # Window not full
    
    # NaN handling
    op = create_streaming_computation("TS_Mean", 3, use_rust=True)
    op.update(1.0)
    op.update(float('nan'))
    op.update(3.0)
    
    # Result should be NaN
    assert op.is_ready
    assert np.isnan(op.value)
    
    # Infinity handling
    op = create_streaming_computation("TS_Sum", 3, use_rust=True)
    op.update(1.0)
    op.update(float('inf'))
    op.update(3.0)
    
    assert op.is_ready
    assert np.isinf(op.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])