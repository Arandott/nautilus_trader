#!/usr/bin/env python3
"""
FactorExp Test Suite Runner

This script runs comprehensive tests for the FactorExp indicator system,
covering all operators, edge cases, and complex expressions.

Usage:
    python run_factorexp_tests.py [--verbose] [--suite SUITE]
    
Arguments:
    --verbose: Enable detailed output
    --suite: Run specific test suite (basic|comprehensive|advanced|all)
"""

import sys
import math
import time
import argparse
from pathlib import Path
import traceback

# Add the project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

# Import test modules
try:
    from test_factorexp_integration import *
    from test_factorexp_comprehensive import TestFactorExpComprehensive, run_expression_test
    from test_factorexp_advanced import TestFactorExpAdvanced, run_advanced_test_suite
except ImportError as e:
    print(f"❌ Failed to import test modules: {e}")
    sys.exit(1)


class FactorExpTestRunner:
    """Comprehensive test runner for FactorExp system."""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.results = {
            'passed': 0,
            'failed': 0,
            'skipped': 0,
            'errors': []
        }
    
    def log(self, message: str, level: str = "INFO"):
        """Log message with timestamp."""
        timestamp = time.strftime("%H:%M:%S")
        prefix = {
            "INFO": "ℹ️ ",
            "SUCCESS": "✅",
            "FAIL": "❌",
            "SKIP": "⏸️ ",
            "WARN": "⚠️ "
        }.get(level, "")
        
        print(f"[{timestamp}] {prefix} {message}")
    
    def run_test_method(self, test_instance, method_name: str, description: str = None):
        """Run a single test method with error handling."""
        if description is None:
            description = method_name.replace('test_', '').replace('_', ' ').title()
        
        try:
            if self.verbose:
                self.log(f"Running {description}...")
            
            # Setup if needed
            if hasattr(test_instance, 'setup_method'):
                test_instance.setup_method()
            
            # Run the test
            method = getattr(test_instance, method_name)
            start_time = time.time()
            method()
            end_time = time.time()
            
            duration = (end_time - start_time) * 1000  # Convert to milliseconds
            
            if self.verbose:
                self.log(f"{description} - PASSED ({duration:.1f}ms)", "SUCCESS")
            
            self.results['passed'] += 1
            return True
            
        except Exception as e:
            error_msg = f"{description} - FAILED: {str(e)}"
            self.log(error_msg, "FAIL")
            self.results['failed'] += 1
            self.results['errors'].append({
                'test': description,
                'error': str(e),
                'traceback': traceback.format_exc() if self.verbose else None
            })
            return False
    
    def run_basic_tests(self):
        """Run basic integration tests."""
        self.log("🚀 Running Basic Integration Tests")
        self.log("-" * 50)
        
        # Test basic functionality from the integration test
        try:
            # Test imports
            self.log("Testing imports...")
            from nautilus_trader.indicators.factorexp.indicator import FactorExpIndicator
            from nautilus_trader.model.data import Bar, BarType, BarSpecification
            self.log("Imports successful", "SUCCESS")
            self.results['passed'] += 1
            
            # Test basic indicator creation
            self.log("Testing basic indicator creation...")
            indicator = FactorExpIndicator("$close")
            self.log("Basic indicator creation successful", "SUCCESS")
            self.results['passed'] += 1
            
        except Exception as e:
            self.log(f"Basic tests failed: {e}", "FAIL")
            self.results['failed'] += 1
            self.results['errors'].append({
                'test': 'Basic Integration',
                'error': str(e),
                'traceback': traceback.format_exc() if self.verbose else None
            })
    
    def run_comprehensive_tests(self):
        """Run comprehensive test suite."""
        self.log("🔍 Running Comprehensive Test Suite")
        self.log("-" * 50)
        
        test_instance = TestFactorExpComprehensive()
        
        # Get all test methods
        test_methods = [
            ('test_basic_features', 'Basic Features'),
            ('test_arithmetic_operators', 'Arithmetic Operators'),
            ('test_comparison_operators', 'Comparison Operators'),
            ('test_logical_operators', 'Logical Operators'),
            ('test_unary_mathematical_operators', 'Unary Math Operators'),
            ('test_trigonometric_operators', 'Trigonometric Operators'),
            ('test_rolling_statistics', 'Rolling Statistics'),
            ('test_rolling_advanced_statistics', 'Advanced Rolling Stats'),
            ('test_rolling_reference_operators', 'Rolling Reference Operators'),
            ('test_insufficient_data_window', 'Insufficient Data Handling'),
            ('test_zero_and_negative_values', 'Zero and Negative Values'),
            ('test_division_by_zero_protection', 'Division by Zero Protection'),
            ('test_simple_nested_expressions', 'Simple Nested Expressions'),
            ('test_complex_rolling_expressions', 'Complex Rolling Expressions'),
            ('test_deeply_nested_expressions', 'Deeply Nested Expressions'),
            ('test_financial_indicators_expressions', 'Financial Indicators'),
            ('test_large_dataset_performance', 'Large Dataset Performance'),
            ('test_expression_compilation_performance', 'Compilation Performance'),
            ('test_memory_stability', 'Memory Stability'),
        ]
        
        for method_name, description in test_methods:
            if hasattr(test_instance, method_name):
                self.run_test_method(test_instance, method_name, description)
            else:
                self.log(f"Method {method_name} not found", "SKIP")
                self.results['skipped'] += 1
    
    def run_advanced_tests(self):
        """Run advanced test suite."""
        self.log("🔬 Running Advanced Test Suite")
        self.log("-" * 50)
        
        test_instance = TestFactorExpAdvanced()
        
        # Get all test methods
        test_methods = [
            ('test_ts_correlation_positive', 'Positive Correlation Test'),
            ('test_ts_correlation_negative', 'Negative Correlation Test'),
            ('test_ts_covariance', 'Covariance Test'),
            ('test_ts_beta', 'Beta Coefficient Test'),
            ('test_zscore_operator', 'Z-Score Operator'),
            ('test_demean_operator', 'Demean Operator'),
            ('test_csrank_operator', 'Cross-Sectional Rank'),
            ('test_cs_statistics', 'Cross-Sectional Statistics'),
            ('test_advanced_rolling_operators', 'Advanced Rolling Operators'),
            ('test_mixed_operator_types', 'Mixed Operator Types'),
            ('test_extreme_values', 'Extreme Values Handling'),
            ('test_rapid_value_changes', 'Rapid Value Changes'),
            ('test_constant_values', 'Constant Values'),
            ('test_window_size_edge_cases', 'Window Size Edge Cases'),
            ('test_expression_compilation_edge_cases', 'Compilation Edge Cases'),
            ('test_deep_nesting_performance', 'Deep Nesting Performance'),
            ('test_many_operators_performance', 'Many Operators Performance'),
        ]
        
        for method_name, description in test_methods:
            if hasattr(test_instance, method_name):
                self.run_test_method(test_instance, method_name, description)
            else:
                self.log(f"Method {method_name} not found", "SKIP")
                self.results['skipped'] += 1
    
    def run_expression_samples(self):
        """Run tests on sample expressions."""
        self.log("📊 Testing Sample Expressions")
        self.log("-" * 50)
        
        sample_expressions = [
            # # Basic expressions
            # ("$close", "Basic Close Price"),
            # ("$close + $open", "Price Addition"),
            # ("$high - $low", "Price Range"),
            
            # # Mathematical expressions
            # ("Abs($close - 100)", "Absolute Deviation"),
            # ("Sqrt($close)", "Square Root"),
            # ("Log($close)", "Natural Logarithm"),
            
            # # Rolling expressions
            # ("TS_Mean($close, 5)", "5-Period Moving Average"),
            # ("TS_Std($close, 10)", "10-Period Standard Deviation"),
            # ("TS_Max($close, 5)", "5-Period Maximum"),
            # ("TS_Min($close, 5)", "5-Period Minimum"),
            
            # Complex expressions
            ("TS_Mean($close, 10) / TS_Mean($close, 20)", "SMA Ratio"),
            ("($close - TS_Mean($close, 20)) / TS_Std($close, 20)", "Z-Score"),
            ("Max($close, TS_Mean($close, 5))", "Price vs SMA"),
            
            # Advanced expressions
            ("TS_Mean(Abs($close - TS_Ref($close, 1)), 10)", "Average Price Change"),
            ("Greater(TS_Mean($close, 5), TS_Mean($close, 20))", "SMA Crossover Signal"),
        ]
        
        for expression, description in sample_expressions:
            try:
                if self.verbose:
                    self.log(f"Testing: {description} ({expression})")
                
                result = run_expression_test(expression, num_bars=25, verbose=False)
                
                if result is not None and not math.isnan(result):
                    self.log(f"{description} - OK (value: {result:.4f})", "SUCCESS")
                    self.results['passed'] += 1
                else:
                    self.log(f"{description} - Failed (NaN or None)", "FAIL")
                    self.results['failed'] += 1
                    
            except Exception as e:
                self.log(f"{description} - Error: {str(e)}", "FAIL")
                self.results['failed'] += 1
                self.results['errors'].append({
                    'test': f"Sample Expression: {description}",
                    'error': str(e),
                    'expression': expression
                })
    
    def print_summary(self):
        """Print test summary."""
        self.log("=" * 60)
        self.log("🏆 TEST SUMMARY")
        self.log("=" * 60)
        
        total_tests = self.results['passed'] + self.results['failed'] + self.results['skipped']
        pass_rate = (self.results['passed'] / total_tests * 100) if total_tests > 0 else 0
        
        self.log(f"Total Tests: {total_tests}")
        self.log(f"Passed: {self.results['passed']}", "SUCCESS")
        self.log(f"Failed: {self.results['failed']}", "FAIL" if self.results['failed'] > 0 else "INFO")
        self.log(f"Skipped: {self.results['skipped']}", "SKIP" if self.results['skipped'] > 0 else "INFO")
        self.log(f"Pass Rate: {pass_rate:.1f}%")
        
        if self.results['errors'] and self.verbose:
            self.log("")
            self.log("❌ DETAILED ERROR REPORT")
            self.log("-" * 40)
            
            for i, error in enumerate(self.results['errors'], 1):
                self.log(f"{i}. {error['test']}")
                self.log(f"   Error: {error['error']}")
                if error.get('expression'):
                    self.log(f"   Expression: {error['expression']}")
                if error.get('traceback') and self.verbose:
                    self.log(f"   Traceback:\n{error['traceback']}")
                self.log("")
        
        return self.results['failed'] == 0


def main():
    """Main entry point for test runner."""
    parser = argparse.ArgumentParser(description="FactorExp Test Suite Runner")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    parser.add_argument("--suite", "-s", choices=["basic", "comprehensive", "advanced", "samples", "all"], 
                       default="all", help="Test suite to run")
    
    args = parser.parse_args()
    
    print("🧪 FactorExp Comprehensive Test Suite")
    print("=" * 60)
    
    runner = FactorExpTestRunner(verbose=args.verbose)
    
    start_time = time.time()
    
    # Run selected test suites
    if args.suite in ["basic", "all"]:
        runner.run_basic_tests()
        print()
    
    if args.suite in ["comprehensive", "all"]:
        runner.run_comprehensive_tests()
        print()
    
    if args.suite in ["advanced", "all"]:
        runner.run_advanced_tests()
        print()
    
    if args.suite in ["samples", "all"]:
        runner.run_expression_samples()
        print()
    
    end_time = time.time()
    total_time = end_time - start_time
    
    # Print final summary
    success = runner.print_summary()
    
    runner.log(f"Total execution time: {total_time:.2f} seconds")
    
    if success:
        runner.log("🎉 All tests completed successfully!", "SUCCESS")
        sys.exit(0)
    else:
        runner.log("⚠️  Some tests failed - see details above", "WARN")
        sys.exit(1)


if __name__ == "__main__":
    main()