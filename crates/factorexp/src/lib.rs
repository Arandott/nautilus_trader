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

//! High-performance factor expression operators for Nautilus Trader.
//!
//! This crate provides Rust implementations of FactorExp operators
//! for significant performance improvements over NumPy implementations.

#![warn(missing_docs)]
#![warn(clippy::all)]
#![warn(clippy::pedantic)]
#![allow(clippy::module_name_repetitions)]

pub mod buffer;
pub mod operators;
pub mod expression;
pub mod engine;
pub mod indicator;

#[cfg(feature = "python")]
pub mod python;

// Re-export commonly used types
pub use buffer::{RollingBuffer, BufferStats};
pub use operators::{
    RollingOperator,
    rolling::{Mean, Sum, Std, Var, Min, Max, Median},
    ma::{Ema, Wma},
    stats::{Skew, Kurtosis, Mad},
    get_rolling_operator,
};
pub use expression::{CompiledExpression, ExprNode, ExpressionMetadata, ExpressionError};
pub use engine::ComputationEngine;
pub use indicator::{FactorExpIndicator, FactorIndicator};