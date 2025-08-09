// -------------------------------------------------------------------------------------------------
//  Copyright (C) 2015-2025 Nautech Systems Pty Ltd. All rights reserved.
//  https://nautechsystems.io
//
//  Licensed under the GNU Lesser General Public License Version 3.0 (the "License");
//  You may not use this file except in compliance with the License.
//  You may obtain a copy of the License at https://www.gnu.org/licenses/lgpl-3.0.en.html
//
//  Unless required by applicable law or agreed to in writing, software
//  distributed under the License is distributed on an "AS IS" BASIS,
//  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
//  See the License for the specific language governing permissions and
//  limitations under the License.
// -------------------------------------------------------------------------------------------------

use criterion::{black_box, criterion_group, criterion_main, Criterion};
use nautilus_factorexp::{
    operators::{
        RollingOperator,
        rolling::{Mean, Std, Min, Max},
        ma::{Ema, Wma},
        stats::{Skew, Kurtosis},
    },
};

fn generate_test_data(size: usize) -> Vec<f64> {
    // Generate synthetic price data
    let mut data = vec![100.0];
    let mut price = 100.0;
    
    for _ in 1..size {
        let return_pct = 0.0001 + 0.02 * rand::random::<f64>();
        price *= 1.0 + return_pct;
        data.push(price);
    }
    
    data
}

fn benchmark_mean(c: &mut Criterion) {
    let data = generate_test_data(10_000);
    
    c.bench_function("TS_Mean window=20", |b| {
        b.iter(|| {
            let mut op = Mean::new(20);
            for &value in &data {
                op.update(black_box(value));
            }
            black_box(op.value());
        });
    });
}

fn benchmark_std(c: &mut Criterion) {
    let data = generate_test_data(10_000);
    
    c.bench_function("TS_Std window=20", |b| {
        b.iter(|| {
            let mut op = Std::new(20, 1);
            for &value in &data {
                op.update(black_box(value));
            }
            black_box(op.value());
        });
    });
}

fn benchmark_ema(c: &mut Criterion) {
    let data = generate_test_data(10_000);
    
    c.bench_function("TS_EMA window=20", |b| {
        b.iter(|| {
            let mut op = Ema::new(20);
            for &value in &data {
                op.update(black_box(value));
            }
            black_box(op.value());
        });
    });
}

fn benchmark_min_max(c: &mut Criterion) {
    let data = generate_test_data(10_000);
    
    c.bench_function("TS_Min/Max window=20", |b| {
        b.iter(|| {
            let mut min_op = Min::new(20);
            let mut max_op = Max::new(20);
            for &value in &data {
                min_op.update(black_box(value));
                max_op.update(black_box(value));
            }
            black_box((min_op.value(), max_op.value()));
        });
    });
}

fn benchmark_skew_kurt(c: &mut Criterion) {
    let data = generate_test_data(10_000);
    
    c.bench_function("TS_Skew/Kurt window=20", |b| {
        b.iter(|| {
            let mut skew = Skew::new(20);
            let mut kurt = Kurtosis::new(20);
            for &value in &data {
                skew.update(black_box(value));
                kurt.update(black_box(value));
            }
            black_box((skew.value(), kurt.value()));
        });
    });
}

fn benchmark_comparison(c: &mut Criterion) {
    let mut group = c.benchmark_group("operator_comparison");
    let data = generate_test_data(100_000);
    
    // Compare different window sizes
    for window in [10, 20, 50, 100] {
        group.bench_function(format!("Mean_w{}", window), |b| {
            b.iter(|| {
                let mut op = Mean::new(window);
                for &value in &data {
                    op.update(value);
                }
                op.value()
            });
        });
    }
    
    group.finish();
}

criterion_group!(
    benches,
    benchmark_mean,
    benchmark_std,
    benchmark_ema,
    benchmark_min_max,
    benchmark_skew_kurt,
    benchmark_comparison,
);
criterion_main!(benches);