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

//! Feature registry used by AlphaEngine. Each feature is a single scalar output driven by
//! indicator-style update functions.

use std::{
    any::{Any, TypeId},
    collections::HashMap,
};

use nautilus_indicators::{
    book::{l1_factors::BookL1Factors, mid_price_vol::BookMidPriceVolEstimator},
    indicator::Indicator,
};
use nautilus_model::{data::TradeTick, orderbook::OrderBook};
use once_cell::sync::Lazy;

/// Inputs available to book-driven features.
#[derive(Debug, Clone, Copy)]
pub struct FeatureInputs<'a> {
    pub book: &'a OrderBook,
    #[allow(dead_code)]
    pub inventory_qty: f64,
    pub tick_size: f64,
    #[allow(dead_code)]
    pub i_max: f64,
    pub base_sigma: f64,
}

/// A registered feature entry. Each name produces exactly one scalar value.
/// `source` identifies the shared indicator instance; multiple names can point to the same source.
#[derive(Debug)]
pub struct FeatureEntry {
    pub name: &'static str,
    /// Source key allows multiple names to share one indicator instance.
    pub source: &'static str,
    pub type_id: TypeId,
    pub make: fn() -> Box<dyn Any + Send + Sync>,
    pub on_book: Option<fn(&mut dyn Any, &OrderBook)>,
    pub on_trade: Option<fn(&mut dyn Any, &TradeTick)>,
    pub value: fn(&dyn Any, &FeatureInputs) -> f64,
    #[allow(dead_code)]
    pub reset: fn(&mut dyn Any),
}

macro_rules! register_indicator {
    (
        name: $name:literal,
        ty: $ty:ty,
        value: $value_fn:expr
        $(, source: $source:expr)?
        $(, ctor: $ctor:expr)?
        $(, on_book: $on_book:tt)?
        $(, on_trade: $on_trade:tt)?
        $(,)?
    ) => {
        FeatureEntry {
            name: $name,
            source: register_indicator!(@source $ty $(, $source)?),
            type_id: TypeId::of::<$ty>(),
            make: register_indicator!(@ctor $ty $(, $ctor)?),
            on_book: register_indicator!(@on_book $ty $(, $on_book)?),
            on_trade: register_indicator!(@on_trade $ty $(, $on_trade)?),
            value: |state, inputs| {
                let typed = state.downcast_ref::<$ty>().unwrap();
                $value_fn(typed, inputs)
            },
            reset: |state| {
                state.downcast_mut::<$ty>().unwrap().reset();
            },
        }
    };

    // Defaults and overrides
    (@source $ty:ty) => { stringify!($ty) };
    (@source $ty:ty, $src:expr) => { $src };

    (@ctor $ty:ty) => { || Box::new(<$ty>::new()) };
    (@ctor $ty:ty, $ctor:expr) => { || Box::new($ctor) };

    // on_book defaults to calling handle_book; `none` disables; `auto` is the same as default;
    // custom handler is given &mut $ty and &OrderBook.
    (@on_book $ty:ty) => {
        Some(|state: &mut dyn Any, book: &OrderBook| {
            state.downcast_mut::<$ty>().unwrap().handle_book(book);
        })
    };
    (@on_book $ty:ty, none) => { None };
    (@on_book $ty:ty, auto) => {
        Some(|state: &mut dyn Any, book: &OrderBook| {
            state.downcast_mut::<$ty>().unwrap().handle_book(book);
        })
    };
    (@on_book $ty:ty, $handler:expr) => {
        Some(|state: &mut dyn Any, book: &OrderBook| {
            $handler(state.downcast_mut::<$ty>().unwrap(), book);
        })
    };

    // on_trade defaults to None; `auto` calls handle_trade; custom handler takes &mut $ty, &TradeTick.
    (@on_trade $ty:ty) => { None };
    (@on_trade $ty:ty, none) => { None };
    (@on_trade $ty:ty, auto) => {
        Some(|state: &mut dyn Any, trade: &TradeTick| {
            state.downcast_mut::<$ty>().unwrap().handle_trade(trade);
        })
    };
    (@on_trade $ty:ty, $handler:expr) => {
        Some(|state: &mut dyn Any, trade: &TradeTick| {
            $handler(state.downcast_mut::<$ty>().unwrap(), trade);
        })
    };
}

static REGISTRY: Lazy<HashMap<&'static str, FeatureEntry>> = Lazy::new(|| {
    // Keep mutable for test-only registrations; in non-test builds this remains immutable.
    #[allow(unused_mut)]
    let mut entries = vec![
        // Share one L1 instance for imbalance + micro_skew via common source "l1".
        register_indicator!(
            name: "imbalance",
            ty: BookL1Factors,
            value: |ind: &BookL1Factors, _inputs: &FeatureInputs| { ind.imbalance.unwrap_or(0.0) },
        ),
        register_indicator!(
            name: "micro_skew",
            ty: BookL1Factors,
            value: |ind: &BookL1Factors, inputs: &FeatureInputs| {
                let mid = ind.mid.unwrap_or(0.0);
                if mid <= 0.0 {
                    return 0.0;
                }
                let micro = ind.microprice.unwrap_or(mid);
                let tick = inputs.tick_size.max(1e-9);
                (micro - mid) / tick
            },
        ),
        register_indicator!(
            name: "sigma_rel",
            ty: BookMidPriceVolEstimator,
            value: |vol: &BookMidPriceVolEstimator, inputs: &FeatureInputs| {
                if vol.count() > 0 {
                    vol.sigma_rel()
                } else {
                    inputs.base_sigma
                }
            },
            ctor: BookMidPriceVolEstimator::new(0.94),
        ),
    ];

    #[cfg(test)]
    {
        entries.push(register_indicator!(
            name: "test_shared_book",
            ty: crate::alpha::features::tests::TestSharedIndicator,
            value: |ind: &crate::alpha::features::tests::TestSharedIndicator, _inputs: &FeatureInputs| {
                ind.book_called as f64
            },
            source: "test_shared",
            ctor: crate::alpha::features::tests::TestSharedIndicator::default(),
            on_book: (|ind: &mut crate::alpha::features::tests::TestSharedIndicator, _book: &OrderBook| {
                ind.book_called += 1;
            }),
            on_trade: none,
        ));

        entries.push(register_indicator!(
            name: "test_shared_trade",
            ty: crate::alpha::features::tests::TestSharedIndicator,
            value: |ind: &crate::alpha::features::tests::TestSharedIndicator, _inputs: &FeatureInputs| {
                ind.trade_called as f64
            },
            source: "test_shared",
            ctor: crate::alpha::features::tests::TestSharedIndicator::default(),
            on_book: none,
            on_trade: (|ind: &mut crate::alpha::features::tests::TestSharedIndicator, _trade: &TradeTick| {
                ind.trade_called += 1;
            }),
        ));
    }

    let mut map = HashMap::with_capacity(entries.len());
    for entry in entries {
        let name = entry.name;
        if map.insert(name, entry).is_some() {
            panic!("duplicate feature name registered: {}", name);
        }
    }
    map
});

pub fn lookup_feature(name: &str) -> Option<&'static FeatureEntry> {
    REGISTRY.get(name)
}

#[allow(dead_code)]
pub fn all_feature_names() -> impl Iterator<Item = &'static str> {
    REGISTRY.keys().copied()
}

#[cfg(test)]
pub(crate) mod tests {
    #[derive(Default, Debug)]
    pub struct TestSharedIndicator {
        pub book_called: usize,
        pub trade_called: usize,
    }

    impl TestSharedIndicator {
        pub fn reset(&mut self) {
            self.book_called = 0;
            self.trade_called = 0;
        }
    }
}
