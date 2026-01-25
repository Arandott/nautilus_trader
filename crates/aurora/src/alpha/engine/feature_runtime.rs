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

//! Feature runtime helpers for AlphaEngine.

use anyhow::{Result, anyhow};
use nautilus_model::{data::TradeTick, orderbook::OrderBook};

use crate::alpha::AlphaModel;
use crate::alpha::features::{Feature, FeatureConfig, Inputs, build_feature};

use super::AlphaEngine;

pub(super) struct FeatureRuntime {
    pub(super) features: Vec<Feature>,
    pub(super) book_idx: Vec<usize>,
    pub(super) trade_idx: Vec<usize>,
    pub(super) quote_idx: Vec<usize>,
}

impl<M: AlphaModel> AlphaEngine<M> {
    pub(super) fn build_features(
        feature_names: &[String],
        config: &FeatureConfig,
    ) -> Result<FeatureRuntime> {
        let mut features: Vec<Feature> = Vec::with_capacity(feature_names.len());
        let mut book_idx = Vec::new();
        let mut trade_idx = Vec::new();
        let mut quote_idx = Vec::new();

        for name in feature_names {
            let canonical = name.replace('-', "_");
            let (feature, inputs) = build_feature(name.as_str(), config)
                .or_else(|| build_feature(&canonical, config))
                .ok_or_else(|| anyhow!("unknown feature name '{name}'"))?;
            let idx = features.len();
            features.push(feature);
            if inputs.contains(Inputs::BOOK) {
                book_idx.push(idx);
            }
            if inputs.contains(Inputs::TRADE) {
                trade_idx.push(idx);
            }
            if inputs.contains(Inputs::QUOTE) {
                quote_idx.push(idx);
            }
        }
        Ok(FeatureRuntime {
            features,
            book_idx,
            trade_idx,
            quote_idx,
        })
    }

    pub(super) fn update_features_on_book(
        features: &mut [Feature],
        book_idx: &[usize],
        book: &OrderBook,
    ) {
        for &idx in book_idx {
            features[idx].on_book(book);
        }
    }

    pub(super) fn update_features_on_trade(
        features: &mut [Feature],
        trade_idx: &[usize],
        trade: &TradeTick,
    ) {
        for &idx in trade_idx {
            features[idx].on_trade(trade);
        }
    }

    #[allow(dead_code)]
    pub(super) fn update_features_on_quote(
        features: &mut [Feature],
        quote_idx: &[usize],
        quote: &nautilus_model::data::QuoteTick,
    ) {
        for &idx in quote_idx {
            features[idx].on_quote(quote);
        }
    }

    pub(super) fn write_features(features: &[Feature], feature_buf: &mut [f64]) {
        debug_assert!(feature_buf.len() == features.len());
        for (idx, feature) in features.iter().enumerate() {
            feature_buf[idx] = feature.value();
        }
    }
}
