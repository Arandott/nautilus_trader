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

//! Alpha model implementations and registry utilities.

pub mod model_handle;
pub mod model_registry;
pub mod onnx;
pub mod rls;
pub mod linear;

pub use model_handle::{ArcSwapModelHandle, ModelHandle, Predictor, StaticPredictor, SwappableModel};
pub use model_registry::{InMemoryModelRegistry, ModelEntry, ModelMetadata, ModelRegistry};
pub use onnx::{OnnxPredictor, OnnxSession};
pub use linear::LinearAlpha;
pub use rls::{RlsAlpha, RlsParams};
