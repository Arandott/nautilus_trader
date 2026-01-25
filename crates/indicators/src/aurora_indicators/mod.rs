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

//! Aurora-specific indicators with a unified value() interface.

pub mod book;
pub mod flow;
mod imbalance_factor;
mod micro_skew_factor;
mod sigma_rel_factor;
mod utils;

pub trait ValueIndicator {
    fn value(&self) -> f64;
}

pub use imbalance_factor::ImbalanceFactor;
pub use micro_skew_factor::MicroSkewFactor;
pub use sigma_rel_factor::SigmaRelFactor;
