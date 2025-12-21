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

use std::collections::HashMap;

use anyhow::{Result, anyhow};
use nautilus_model::{data::TradeTick, orderbook::OrderBook};

use crate::alpha::AlphaModel;
use crate::alpha::features::{FeatureEntry, FeatureInputs, lookup_feature};

use super::AlphaEngine;

#[derive(Debug)]
// Backing indicator instance; may serve multiple feature names that share one source.
pub(super) struct FeatureState {
    pub(super) state: Box<dyn std::any::Any + Send + Sync>,
    pub(super) on_book: Option<fn(&mut dyn std::any::Any, &OrderBook)>,
    pub(super) on_trade: Option<fn(&mut dyn std::any::Any, &TradeTick)>,
}

#[derive(Debug)]
// Mapping from requested feature to its shared state and value function.
pub(super) struct FeatureHandle {
    pub(super) entry: &'static FeatureEntry,
    pub(super) state_idx: usize,
}

impl<M: AlphaModel> AlphaEngine<M> {
    pub(super) fn build_features(
        feature_names: &[String],
    ) -> Result<(Vec<FeatureState>, Vec<FeatureHandle>)> {
        // Group by (source, type) so a single indicator instance can back multiple feature names
        // (e.g. L1 imbalance + micro_skew) while keeping book/trade callbacks unified.
        let mut states: Vec<FeatureState> = Vec::new();
        let mut handles: Vec<FeatureHandle> = Vec::new();
        let mut source_to_state: HashMap<&'static str, (std::any::TypeId, usize)> = HashMap::new();

        for name in feature_names {
            let canonical = name.replace('-', "_");
            let entry = lookup_feature(name.as_str())
                .or_else(|| lookup_feature(&canonical))
                .ok_or_else(|| anyhow!("unknown feature name '{name}'"))?;

            let state_idx = match source_to_state.get_mut(entry.source) {
                Some((ty, idx)) => {
                    if *ty != entry.type_id {
                        return Err(anyhow!(
                            "feature source '{}' registered with multiple types (existing={:?}, new={:?})",
                            entry.source,
                            ty,
                            entry.type_id
                        ));
                    }
                    let state = &mut states[*idx];
                    if state.on_book.is_none() && entry.on_book.is_some() {
                        state.on_book = entry.on_book;
                    }
                    if state.on_trade.is_none() && entry.on_trade.is_some() {
                        state.on_trade = entry.on_trade;
                    }
                    *idx
                }
                None => {
                    let idx = states.len();
                    states.push(FeatureState {
                        state: (entry.make)(),
                        on_book: entry.on_book,
                        on_trade: entry.on_trade,
                    });
                    source_to_state.insert(entry.source, (entry.type_id, idx));
                    idx
                }
            };

            handles.push(FeatureHandle { entry, state_idx });
        }

        Ok((states, handles))
    }

    pub(super) fn update_features_on_book(states: &mut [FeatureState], book: &OrderBook) {
        for state in states {
            if let Some(on_book) = state.on_book {
                on_book(state.state.as_mut(), book);
            }
        }
    }

    pub(super) fn update_features_on_trade(states: &mut [FeatureState], trade: &TradeTick) {
        for state in states {
            if let Some(on_trade) = state.on_trade {
                on_trade(state.state.as_mut(), trade);
            }
        }
    }

    pub(super) fn write_features(
        handles: &[FeatureHandle],
        states: &[FeatureState],
        feature_buf: &mut [f64],
        inputs: &FeatureInputs,
    ) {
        debug_assert!(feature_buf.len() == handles.len());
        for (idx, handle) in handles.iter().enumerate() {
            let state = &states[handle.state_idx];
            feature_buf[idx] = (handle.entry.value)(state.state.as_ref(), inputs);
        }
    }
}
