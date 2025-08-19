#!/usr/bin/env python3
"""
FactorExp Expression Playground

A utility for quickly testing and debugging individual FactorExp expressions.
This is useful for development, debugging, and exploring the system's capabilities.

Usage:
    python test_expression_playground.py
    
    # Or import and use programmatically
    from test_expression_playground import ExpressionPlayground
    playground = ExpressionPlayground()
    playground.test_expression("TS_Mean($close, 20)")
"""

import sys
import math
import time
import traceback
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from nautilus_trader.indicators.factorexp.indicator import FactorExpIndicator
from nautilus_trader.model.data import Bar, BarType, BarSpecification
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.enums import BarAggregation, AggregationSource
from nautilus_trader.core.nautilus_pyo3 import PriceType
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue


class ExpressionPlayground:
    """Interactive playground for testing FactorExp expressions."""
    
    def __init__(self):
        """Initialize the expression playground."""
        self.bar_type = BarType(
            instrument_id=InstrumentId(Symbol("TEST"), Venue("SIM")),
            bar_spec=BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST),
            aggregation_source=AggregationSource.EXTERNAL,
        )
        
        # Predefined test datasets
        self.datasets = {
            'trending_up': self._generate_trending_data(100, 110, 50),
            'trending_down': self._generate_trending_data(110, 100, 50),
            'sideways': self._generate_sideways_data(100, 5, 50),
            'volatile': self._generate_volatile_data(100, 20, 50),
            'sine_wave': self._generate_sine_wave_data(100, 10, 50),
            'step_function': self._generate_step_function_data([95, 100, 105, 110]),
        }
    
    def _generate_trending_data(self, start: float, end: float, count: int) -> List[Tuple[float, float, float, float, float]]:
        """Generate trending price data."""
        step = (end - start) / (count - 1)
        data = []
        
        for i in range(count):
            close = start + i * step + (i % 3 - 1) * 0.5  # Add small noise
            open_price = close + (i % 2 - 0.5) * 0.3
            high = max(open_price, close) + abs(i % 4 - 1.5) * 0.2
            low = min(open_price, close) - abs(i % 4 - 1.5) * 0.2
            volume = 1000 + i * 10 + (i % 7) * 100
            
            data.append((open_price, high, low, close, volume))
        
        return data
    
    def _generate_sideways_data(self, center: float, range_size: float, count: int) -> List[Tuple[float, float, float, float, float]]:
        """Generate sideways (range-bound) price data."""
        import random
        data = []
        
        for i in range(count):
            close = center + (random.random() - 0.5) * range_size
            open_price = close + (random.random() - 0.5) * 1.0
            high = max(open_price, close) + random.random() * 0.5
            low = min(open_price, close) - random.random() * 0.5
            volume = 1000 + random.randint(-200, 200)
            
            data.append((open_price, high, low, close, volume))
        
        return data
    
    def _generate_volatile_data(self, center: float, volatility: float, count: int) -> List[Tuple[float, float, float, float, float]]:
        """Generate highly volatile price data."""
        import random
        data = []
        last_close = center
        
        for i in range(count):
            # Random walk with high volatility
            change = (random.random() - 0.5) * volatility
            close = last_close + change
            open_price = last_close + (random.random() - 0.5) * 2.0
            high = max(open_price, close) + random.random() * 2.0
            low = min(open_price, close) - random.random() * 2.0
            volume = 1000 + random.randint(-500, 500)
            
            data.append((open_price, high, low, close, volume))
            last_close = close
        
        return data
    
    def _generate_sine_wave_data(self, center: float, amplitude: float, count: int) -> List[Tuple[float, float, float, float, float]]:
        """Generate sine wave price data."""
        data = []
        
        for i in range(count):
            angle = 2 * math.pi * i / 20  # Complete cycle every 20 bars
            close = center + amplitude * math.sin(angle)
            open_price = close + math.sin(angle + math.pi/4) * 0.5
            high = max(open_price, close) + abs(math.cos(angle)) * 0.3
            low = min(open_price, close) - abs(math.cos(angle)) * 0.3
            volume = 1000 + 200 * (1 + math.sin(angle * 2))
            
            data.append((open_price, high, low, close, volume))
        
        return data
    
    def _generate_step_function_data(self, levels: List[float]) -> List[Tuple[float, float, float, float, float]]:
        """Generate step function price data."""
        data = []
        bars_per_level = 15
        
        for level in levels:
            for i in range(bars_per_level):
                close = level + (i % 3 - 1) * 0.1  # Small noise
                open_price = close + (i % 2 - 0.5) * 0.05
                high = max(open_price, close) + 0.05
                low = min(open_price, close) - 0.05
                volume = 1000 + i * 5
                
                data.append((open_price, high, low, close, volume))
        
        return data
    
    def create_bar(self, open_price: float, high_price: float, 
                   low_price: float, close_price: float, volume: float) -> Bar:
        """Create a test bar."""
        return Bar(
            bar_type=self.bar_type,
            open=Price.from_str(f"{open_price:.4f}"),
            high=Price.from_str(f"{high_price:.4f}"),
            low=Price.from_str(f"{low_price:.4f}"),
            close=Price.from_str(f"{close_price:.4f}"),
            volume=Quantity.from_str(f"{volume:.0f}"),
            ts_event=int(time.time() * 1e9),
            ts_init=int(time.time() * 1e9),
        )
    
    def test_expression(self, expression: str, dataset: str = 'trending_up', 
                       verbose: bool = True, return_history: bool = False) -> Dict[str, Any]:
        """
        Test a single expression with detailed analysis.
        
        Parameters
        ----------
        expression : str
            The FactorExp expression to test
        dataset : str
            Which dataset to use ('trending_up', 'trending_down', 'sideways', 'volatile', 'sine_wave', 'step_function')
        verbose : bool
            Whether to print detailed output
        return_history : bool
            Whether to return the value history
        
        Returns
        -------
        dict
            Test results including final value, history, performance metrics
        """
        if verbose:
            print(f"\n{'='*60}")
            print(f"🧪 Testing Expression: {expression}")
            print(f"📊 Dataset: {dataset}")
            print(f"{'='*60}")
        
        results = {
            'expression': expression,
            'dataset': dataset,
            'success': False,
            'final_value': None,
            'value_history': [],
            'bar_count': 0,
            'compilation_time': 0,
            'execution_time': 0,
            'errors': [],
            'warnings': [],
            'statistics': {}
        }
        
        try:
            # Measure compilation time
            start_time = time.time()
            indicator = FactorExpIndicator(expression)
            compilation_time = time.time() - start_time
            results['compilation_time'] = compilation_time
            
            if verbose:
                print(f"✅ Expression compiled successfully ({compilation_time*1000:.2f}ms)")
                print(f"   Period: {indicator.period}")
                print(f"   Name: {indicator.name}")
                print("")
            
            # Get test data
            if dataset not in self.datasets:
                raise ValueError(f"Unknown dataset: {dataset}. Available: {list(self.datasets.keys())}")
            
            test_data = self.datasets[dataset]
            
            # Measure execution time
            start_time = time.time()
            value_history = []
            
            # Feed data and collect values
            for i, (open_p, high, low, close, volume) in enumerate(test_data):
                bar = self.create_bar(open_p, high, low, close, volume)
                indicator.handle_bar(bar)
                
                if return_history:
                    value_history.append({
                        'bar': i + 1,
                        'close': close,
                        'value': indicator.value if not math.isnan(indicator.value) else None
                    })
            
            execution_time = time.time() - start_time
            results['execution_time'] = execution_time
            results['bar_count'] = len(test_data)
            results['final_value'] = indicator.value
            results['value_history'] = value_history
            
            # Calculate statistics
            if return_history and value_history:
                valid_values = [h['value'] for h in value_history if h['value'] is not None]
                if valid_values:
                    results['statistics'] = {
                        'count': len(valid_values),
                        'mean': sum(valid_values) / len(valid_values),
                        'min': min(valid_values),
                        'max': max(valid_values),
                        'std': (sum((x - sum(valid_values)/len(valid_values))**2 for x in valid_values) / len(valid_values))**0.5
                    }
            
            # Check for warnings
            if math.isnan(indicator.value):
                results['warnings'].append("Final value is NaN")
            elif math.isinf(indicator.value):
                results['warnings'].append("Final value is infinite")
            
            results['success'] = True
            
            if verbose:
                print(f"📈 Data Processing:")
                print(f"   Bars processed: {len(test_data)}")
                print(f"   Execution time: {execution_time*1000:.2f}ms")
                print(f"   Speed: {len(test_data)/execution_time:.0f} bars/second")
                print("")
                
                print(f"📊 Results:")
                print(f"   Final value: {indicator.value}")
                print(f"   Has inputs: {indicator.has_inputs}")
                print(f"   Initialized: {indicator.initialized}")
                
                if results['statistics']:
                    stats = results['statistics']
                    print(f"   Value statistics: mean={stats['mean']:.4f}, std={stats['std']:.4f}")
                    print(f"                    min={stats['min']:.4f}, max={stats['max']:.4f}")
                
                if results['warnings']:
                    print(f"⚠️  Warnings:")
                    for warning in results['warnings']:
                        print(f"   - {warning}")
        
        except Exception as e:
            results['success'] = False
            results['errors'].append(str(e))
            
            if verbose:
                print(f"❌ Expression failed: {e}")
                traceback.print_exc()
        
        if verbose:
            print(f"{'='*60}\n")
        
        return results
    
    def compare_expressions(self, expressions: List[str], dataset: str = 'trending_up') -> Dict[str, Any]:
        """Compare multiple expressions on the same dataset."""
        print(f"\n🔀 Comparing {len(expressions)} expressions on '{dataset}' dataset")
        print("="*80)
        
        results = {}
        
        for expr in expressions:
            try:
                result = self.test_expression(expr, dataset, verbose=False, return_history=True)
                results[expr] = result
                
                status = "✅" if result['success'] else "❌"
                value = result['final_value']
                value_str = f"{value:.4f}" if value is not None and not math.isnan(value) else "NaN"
                
                print(f"{status} {expr:<40} → {value_str}")
                
            except Exception as e:
                print(f"❌ {expr:<40} → ERROR: {e}")
        
        return results
    
    def benchmark_performance(self, expressions: List[str], iterations: int = 100) -> Dict[str, Dict[str, float]]:
        """Benchmark performance of expressions."""
        print(f"\n⚡ Performance Benchmark ({iterations} iterations)")
        print("="*60)
        
        results = {}
        
        for expr in expressions:
            compilation_times = []
            execution_times = []
            
            for _ in range(iterations):
                try:
                    # Measure compilation
                    start = time.time()
                    indicator = FactorExpIndicator(expr)
                    compilation_times.append(time.time() - start)
                    
                    # Measure execution with small dataset
                    start = time.time()
                    for i in range(10):  # 10 bars
                        bar = self.create_bar(100+i, 101+i, 99+i, 100+i, 1000+i)
                        indicator.handle_bar(bar)
                    execution_times.append(time.time() - start)
                    
                except Exception:
                    continue
            
            if compilation_times and execution_times:
                results[expr] = {
                    'compilation_mean': sum(compilation_times) / len(compilation_times) * 1000,  # ms
                    'compilation_std': (sum((x - sum(compilation_times)/len(compilation_times))**2 
                                           for x in compilation_times) / len(compilation_times))**0.5 * 1000,
                    'execution_mean': sum(execution_times) / len(execution_times) * 1000,  # ms
                    'execution_std': (sum((x - sum(execution_times)/len(execution_times))**2 
                                         for x in execution_times) / len(execution_times))**0.5 * 1000,
                    'total_mean': (sum(compilation_times) + sum(execution_times)) / len(compilation_times) * 1000
                }
                
                r = results[expr]
                print(f"{expr:<40} | Compile: {r['compilation_mean']:.2f}ms | Execute: {r['execution_mean']:.2f}ms | Total: {r['total_mean']:.2f}ms")
        
        return results
    
    def interactive_mode(self):
        """Start interactive mode for testing expressions."""
        print(f"\n🎮 FactorExp Interactive Playground")
        print("="*50)
        print("Available datasets:", list(self.datasets.keys()))
        print("Commands:")
        print("  test <expression> [dataset]  - Test an expression")
        print("  compare <expr1> <expr2> ...  - Compare expressions")  
        print("  benchmark <expr1> <expr2> ... - Benchmark performance")
        print("  datasets - List available datasets")
        print("  examples - Show example expressions")
        print("  quit - Exit")
        print("")
        
        current_dataset = 'trending_up'
        
        while True:
            try:
                user_input = input(f"factorexp[{current_dataset}]> ").strip()
                
                if not user_input:
                    continue
                
                parts = user_input.split()
                command = parts[0].lower()
                
                if command == 'quit' or command == 'exit':
                    print("Goodbye! 👋")
                    break
                
                elif command == 'test':
                    if len(parts) < 2:
                        print("Usage: test <expression> [dataset]")
                        continue
                    
                    expression = ' '.join(parts[1:])
                    dataset = current_dataset
                    
                    # Check if last part is a dataset name
                    if parts[-1] in self.datasets:
                        expression = ' '.join(parts[1:-1])
                        dataset = parts[-1]
                    
                    self.test_expression(expression, dataset)
                
                elif command == 'compare':
                    if len(parts) < 3:
                        print("Usage: compare <expr1> <expr2> [expr3] ...")
                        continue
                    
                    expressions = parts[1:]
                    self.compare_expressions(expressions, current_dataset)
                
                elif command == 'benchmark':
                    if len(parts) < 2:
                        print("Usage: benchmark <expr1> [expr2] ...")
                        continue
                    
                    expressions = parts[1:]
                    self.benchmark_performance(expressions)
                
                elif command == 'datasets':
                    print("Available datasets:")
                    for name, data in self.datasets.items():
                        print(f"  {name:<15} - {len(data)} bars")
                
                elif command == 'dataset':
                    if len(parts) != 2 or parts[1] not in self.datasets:
                        print(f"Usage: dataset <name>. Available: {list(self.datasets.keys())}")
                        continue
                    current_dataset = parts[1]
                    print(f"Current dataset: {current_dataset}")
                
                elif command == 'examples':
                    self.show_examples()
                
                else:
                    print(f"Unknown command: {command}")
                    print("Type 'quit' to exit or see command list above.")
            
            except KeyboardInterrupt:
                print("\nGoodbye! 👋")
                break
            except Exception as e:
                print(f"Error: {e}")
    
    def show_examples(self):
        """Show example expressions."""
        examples = [
            ("Basic", [
                "$close",
                "$high - $low", 
                "$close + 5",
                "Abs($close - 100)"
            ]),
            ("Mathematical", [
                "Log($close)",
                "Sqrt($volume)",
                "Sin($close / 10)",
                "Max($close, 100)"
            ]),
            ("Rolling Operations", [
                "TS_Mean($close, 20)",
                "TS_Std($close, 20)", 
                "TS_Max($close, 10)",
                "TS_Delta($close, 1)"
            ]),
            ("Financial Indicators", [
                "TS_Mean($close, 20) / TS_Mean($close, 50)",
                "($close - TS_Mean($close, 20)) / TS_Std($close, 20)",
                "TS_Mean(Max($close - TS_Ref($close, 1), 0), 14)",
                "Greater(TS_Mean($close, 5), TS_Mean($close, 20))"
            ]),
            ("Complex Nested", [
                "Abs(TS_Mean($close, 10) - TS_Mean($open, 10))",
                "Max(TS_Min($close, 5), TS_Mean($close, 20))",
                "TS_Mean(Sqrt(Abs($high - $low)), 10)",
                "Log(TS_Sum($volume, 5) / TS_Mean($volume, 20))"
            ])
        ]
        
        print("\n📚 Example Expressions:")
        print("="*50)
        
        for category, exprs in examples:
            print(f"\n{category}:")
            for expr in exprs:
                print(f"  {expr}")


def main():
    """Main entry point for the playground."""
    playground = ExpressionPlayground()
    
    if len(sys.argv) > 1:
        # Command line mode
        expression = ' '.join(sys.argv[1:])
        playground.test_expression(expression, verbose=True, return_history=True)
    else:
        # Interactive mode
        playground.interactive_mode()


if __name__ == "__main__":
    main()