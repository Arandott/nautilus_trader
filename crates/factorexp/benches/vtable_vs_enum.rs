// Benchmark: Virtual dispatch vs Enum dispatch vs Static dispatch
// 让数据说话，而不是猜测

use criterion::{black_box, criterion_group, criterion_main, Criterion};
use nautilus_factorexp::operators::{RollingOperator, rolling::Mean};
use std::time::Duration;

// 方案1: Trait object (virtual dispatch)
fn benchmark_trait_object(c: &mut Criterion) {
    c.bench_function("trait_object_dispatch", |b| {
        let mut operators: Vec<Box<dyn RollingOperator>> = vec![
            Box::new(Mean::new(20)),
            Box::new(Mean::new(50)),
            Box::new(Mean::new(100)),
        ];

        let values = vec![100.0; 1000];

        b.iter(|| {
            for value in &values {
                for op in &mut operators {
                    op.update(black_box(*value));
                    black_box(op.value());
                }
            }
        });
    });
}

// 方案2: Enum dispatch
enum OperatorEnum {
    Mean20(Mean),
    Mean50(Mean),
    Mean100(Mean),
}

impl OperatorEnum {
    fn update(&mut self, value: f64) {
        match self {
            Self::Mean20(m) => m.update(value),
            Self::Mean50(m) => m.update(value),
            Self::Mean100(m) => m.update(value),
        }
    }

    fn value(&self) -> f64 {
        match self {
            Self::Mean20(m) => m.value(),
            Self::Mean50(m) => m.value(),
            Self::Mean100(m) => m.value(),
        }
    }
}

fn benchmark_enum_dispatch(c: &mut Criterion) {
    c.bench_function("enum_dispatch", |b| {
        let mut operators = vec![
            OperatorEnum::Mean20(Mean::new(20)),
            OperatorEnum::Mean50(Mean::new(50)),
            OperatorEnum::Mean100(Mean::new(100)),
        ];

        let values = vec![100.0; 1000];

        b.iter(|| {
            for value in &values {
                for op in &mut operators {
                    op.update(black_box(*value));
                    black_box(op.value());
                }
            }
        });
    });
}

// 方案3: Static dispatch (monomorphization)
struct StaticOperator<T: RollingOperator> {
    operator: T,
}

fn benchmark_static_dispatch(c: &mut Criterion) {
    c.bench_function("static_dispatch", |b| {
        let mut op1 = Mean::new(20);
        let mut op2 = Mean::new(50);
        let mut op3 = Mean::new(100);

        let values = vec![100.0; 1000];

        b.iter(|| {
            for value in &values {
                op1.update(black_box(*value));
                black_box(op1.value());
                op2.update(black_box(*value));
                black_box(op2.value());
                op3.update(black_box(*value));
                black_box(op3.value());
            }
        });
    });
}

// 真实场景: 计算复杂表达式
fn benchmark_real_expression(c: &mut Criterion) {
    c.bench_function("real_expression_trait", |b| {
        // TS_Mean($close, 20) / TS_Mean($close, 50)
        let mut mean20: Box<dyn RollingOperator> = Box::new(Mean::new(20));
        let mut mean50: Box<dyn RollingOperator> = Box::new(Mean::new(50));

        b.iter(|| {
            for i in 0..1000 {
                let value = 100.0 + (i as f64) * 0.01;
                mean20.update(black_box(value));
                mean50.update(black_box(value));

                if mean20.is_ready() && mean50.is_ready() {
                    let result = mean20.value() / mean50.value();
                    black_box(result);
                }
            }
        });
    });
}

criterion_group! {
    name = benches;
    config = Criterion::default()
        .measurement_time(Duration::from_secs(10))
        .warm_up_time(Duration::from_secs(3));
    targets = benchmark_trait_object,
              benchmark_enum_dispatch,
              benchmark_static_dispatch,
              benchmark_real_expression
}

criterion_main!(benches);