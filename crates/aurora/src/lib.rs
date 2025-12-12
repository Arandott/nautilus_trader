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

//! Aurora strategy support primitives implemented in pure Rust.

pub mod alpha;
pub mod exec;
pub mod orchestrator;
pub mod fill;
pub mod grid;
pub mod risk;

pub use alpha::{AlphaEngine, AlphaModel, RlsAlpha, RlsParams};
pub use exec::{
    ActiveOrder, CancelReq, ExecPolicy, ExecPolicyConfig, ExecutionActions, OrderIntent, OrderKind,
    PlannedOrder,
};
pub use orchestrator::{AuroraOrchestrator, OrchestratorConfig, make_default_components};
pub use fill::{FillModel, QueueStats};
pub use grid::{GridLevel, GridParams, GridPlan, GridPlanner, GridPlannerConfig, InventoryParams};
pub use risk::{
    RegimeParams, RegimeState, RiskAdvisor, RiskDecision, RiskMode, RiskState, TrendBias,
};

#[cfg(feature = "python")]
pub mod python;
