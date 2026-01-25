// -------------------------------------------------------------------------------------------------
//  Copyright (C) 2015-2026 Nautech Systems Pty Ltd. All rights reserved.
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

//! Feature registry used by AlphaEngine. Each feature is a single scalar output.

use std::ops::{BitOr, BitOrAssign};

use nautilus_indicators::{
    indicator::Indicator, ImbalanceFactor, MicroSkewFactor, SigmaRelFactor, ValueIndicator,
};
use nautilus_model::{
    data::{QuoteTick, TradeTick},
    orderbook::OrderBook,
};

#[derive(Debug, Clone, Copy)]
pub struct FeatureConfig {
    pub tick_size: f64,
    pub base_sigma: f64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct Inputs(u8);

impl Inputs {
    pub const BOOK: Inputs = Inputs(1);
    pub const TRADE: Inputs = Inputs(2);
    pub const QUOTE: Inputs = Inputs(4);

    pub fn contains(self, other: Inputs) -> bool {
        (self.0 & other.0) != 0
    }
}

impl BitOr for Inputs {
    type Output = Inputs;

    fn bitor(self, rhs: Inputs) -> Inputs {
        Inputs(self.0 | rhs.0)
    }
}

impl BitOrAssign for Inputs {
    fn bitor_assign(&mut self, rhs: Inputs) {
        self.0 |= rhs.0;
    }
}

macro_rules! define_features {
    ($( $name:literal => $variant:ident($ty:ty) { inputs: $inputs:expr, init: $init:expr $(,)? } ),+ $(,)?) => {
        #[derive(Debug)]
        pub(crate) enum Feature {
            $( $variant($ty), )+
        }

        impl Feature {
            pub(crate) fn on_book(&mut self, book: &OrderBook) {
                match self {
                    $( Feature::$variant(f) => f.handle_book(book), )+
                }
            }

            pub(crate) fn on_trade(&mut self, trade: &TradeTick) {
                match self {
                    $( Feature::$variant(f) => f.handle_trade(trade), )+
                }
            }

            #[allow(dead_code)]
            pub(crate) fn on_quote(&mut self, quote: &QuoteTick) {
                match self {
                    $( Feature::$variant(f) => f.handle_quote(quote), )+
                }
            }

            pub(crate) fn value(&self) -> f64 {
                match self {
                    $( Feature::$variant(f) => ValueIndicator::value(f), )+
                }
            }
        }

        pub(crate) fn lookup_feature(name: &str) -> Option<Inputs> {
            match name {
                $( $name => Some($inputs), )+
                _ => None,
            }
        }

        pub(crate) fn build_feature(
            name: &str,
            config: &FeatureConfig,
        ) -> Option<(Feature, Inputs)> {
            match name {
                $( $name => Some((Feature::$variant(($init)(config)), $inputs)), )+
                _ => None,
            }
        }

        #[allow(dead_code)]
        pub fn all_feature_names() -> impl Iterator<Item = &'static str> {
            [ $( $name ),+ ].iter().copied()
        }
    };
}

define_features! {
    "imbalance" => Imbalance(ImbalanceFactor) {
        inputs: Inputs::BOOK,
        init: |_: &FeatureConfig| ImbalanceFactor::new(),
    },
    "micro_skew" => MicroSkew(MicroSkewFactor) {
        inputs: Inputs::BOOK,
        init: |cfg: &FeatureConfig| {
            let mut factor = MicroSkewFactor::new();
            factor.set_tick_size(cfg.tick_size);
            factor
        },
    },
    "sigma_rel" => SigmaRel(SigmaRelFactor) {
        inputs: Inputs::BOOK,
        init: |cfg: &FeatureConfig| {
            let mut factor = SigmaRelFactor::new(0.94);
            factor.set_base_sigma(cfg.base_sigma);
            factor
        },
    },
}
