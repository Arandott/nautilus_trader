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
//  See the License for the specific language governing.permissions and
//  limitations under the License.
// -------------------------------------------------------------------------------------------------

//! PyO3 bindings for Aurora risk advisory helpers.

use crate::risk::{
    RegimeParams as CoreRegimeParams, RegimeState, RiskAdvisor as CoreRiskAdvisor,
    RiskDecision as CoreRiskDecision, RiskMode, RiskState, TrendBias,
};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

#[pyclass(module = "nautilus_trader.core.nautilus_pyo3.aurora")]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AuroraRiskState {
    NORMAL,
    WIDEN,
    PAUSE,
}

impl From<RiskState> for AuroraRiskState {
    fn from(value: RiskState) -> Self {
        match value {
            RiskState::Normal => Self::NORMAL,
            RiskState::Widen => Self::WIDEN,
            RiskState::Pause => Self::PAUSE,
        }
    }
}

#[pymethods]
impl AuroraRiskState {
    fn __str__(&self) -> String {
        format!("{self:?}")
    }
}

#[pyclass(module = "nautilus_trader.core.nautilus_pyo3.aurora")]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AuroraRegime {
    NORMAL,
    TREND_UP,
    TREND_DOWN,
    CHAOS,
}

impl From<RegimeState> for AuroraRegime {
    fn from(value: RegimeState) -> Self {
        match value {
            RegimeState::Normal => Self::NORMAL,
            RegimeState::TrendUp => Self::TREND_UP,
            RegimeState::TrendDown => Self::TREND_DOWN,
            RegimeState::Chaos => Self::CHAOS,
        }
    }
}

#[pymethods]
impl AuroraRegime {
    fn __str__(&self) -> String {
        format!("{self:?}")
    }
}

#[pyclass(module = "nautilus_trader.core.nautilus_pyo3.aurora")]
#[derive(Clone, Debug)]
pub struct AuroraTrendBias {
    #[pyo3(get)]
    with_trend_is_bid: bool,
    #[pyo3(get)]
    opposite_clip_levels: u32,
}

impl From<TrendBias> for AuroraTrendBias {
    fn from(value: TrendBias) -> Self {
        Self {
            with_trend_is_bid: value.with_trend_is_bid,
            opposite_clip_levels: value.opposite_clip_levels,
        }
    }
}

#[pyclass(module = "nautilus_trader.core.nautilus_pyo3.aurora")]
pub struct AuroraRiskDecision {
    #[pyo3(get)]
    regime: AuroraRegime,
    #[pyo3(get)]
    state: AuroraRiskState,
    #[pyo3(get)]
    widen_factor: f64,
    #[pyo3(get)]
    reduce_levels: u32,
    #[pyo3(get)]
    hedge_qty: f64,
    #[pyo3(get)]
    trend_bias: Option<AuroraTrendBias>,
    #[pyo3(get)]
    reason: Option<String>,
}

impl From<CoreRiskDecision> for AuroraRiskDecision {
    fn from(value: CoreRiskDecision) -> Self {
        Self {
            regime: value.regime.into(),
            state: value.state.into(),
            widen_factor: value.widen_factor,
            reduce_levels: value.reduce_levels,
            hedge_qty: value.hedge_qty,
            trend_bias: value.trend_bias.map(Into::into),
            reason: value.reason,
        }
    }
}

#[pyclass(module = "nautilus_trader.core.nautilus_pyo3.aurora")]
#[derive(Clone, Debug)]
pub struct AuroraRegimeParams {
    pub(crate) inner: CoreRegimeParams,
}

#[pymethods]
impl AuroraRegimeParams {
    #[new]
    #[pyo3(
        signature = (
            alpha_gate_bps = 1.2,
            trend_delta_ratio_threshold = 0.6,
            mo_imbalance_threshold = 2.5,
            hysteresis_ms = 800.0,
            trend_opposite_clip_levels = 1,
            trend_widen_mult = 1.15,
            trend_reduce_levels = 1,
            chaos_widen_mult = 2.0,
            chaos_reduce_levels = 2,
            pause_on_chaos = true
        )
    )]
    pub fn new(
        alpha_gate_bps: f64,
        trend_delta_ratio_threshold: f64,
        mo_imbalance_threshold: f64,
        hysteresis_ms: f64,
        trend_opposite_clip_levels: u32,
        trend_widen_mult: f64,
        trend_reduce_levels: u32,
        chaos_widen_mult: f64,
        chaos_reduce_levels: u32,
        pause_on_chaos: bool,
    ) -> Self {
        Self {
            inner: CoreRegimeParams::new(
                alpha_gate_bps,
                trend_delta_ratio_threshold,
                mo_imbalance_threshold,
                hysteresis_ms,
                trend_opposite_clip_levels,
                trend_widen_mult,
                trend_reduce_levels,
                chaos_widen_mult,
                chaos_reduce_levels,
                pause_on_chaos,
            ),
        }
    }
}

#[derive(Clone, Debug)]
#[pyclass(module = "nautilus_trader.core.nautilus_pyo3.aurora")]
pub struct AuroraRiskAdvisor {
    pub(crate) inner: CoreRiskAdvisor,
}

#[pymethods]
impl AuroraRiskAdvisor {
    #[new]
    #[pyo3(
        signature = (
            vol_shock_sigma_mult,
            inventory_soft_limit,
            hedge_cooldown_ms,
            hedge_min_qty,
            regime_params = None,
            mode = None
        )
    )]
    pub fn new(
        vol_shock_sigma_mult: f64,
        inventory_soft_limit: f64,
        hedge_cooldown_ms: f64,
        hedge_min_qty: f64,
        regime_params: Option<AuroraRegimeParams>,
        mode: Option<String>,
    ) -> PyResult<Self> {
        let risk_mode = RiskMode::from_str(mode.as_deref().unwrap_or("full")).ok_or_else(|| {
            PyValueError::new_err("unsupported risk mode, use `full` or `normal_only`")
        })?;
        let regime_params = regime_params
            .map(|p| p.inner)
            .unwrap_or_else(CoreRegimeParams::default);
        Ok(Self {
            inner: CoreRiskAdvisor::new(
                vol_shock_sigma_mult,
                inventory_soft_limit,
                hedge_cooldown_ms,
                hedge_min_qty,
                regime_params,
                risk_mode,
            ),
        })
    }

    #[pyo3(signature = (sigma_rel, base_sigma, inventory_qty, alpha_bps, delta_ratio, mo_imbalance, now_ns))]
    pub fn advise(
        &mut self,
        sigma_rel: f64,
        base_sigma: f64,
        inventory_qty: f64,
        alpha_bps: f64,
        delta_ratio: f64,
        mo_imbalance: f64,
        now_ns: u64,
    ) -> AuroraRiskDecision {
        self.inner
            .advise(
                sigma_rel,
                base_sigma,
                inventory_qty,
                alpha_bps,
                delta_ratio,
                mo_imbalance,
                now_ns,
            )
            .into()
    }
}

pub fn register(_py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<AuroraRegime>()?;
    m.add_class::<AuroraRegimeParams>()?;
    m.add_class::<AuroraRiskAdvisor>()?;
    m.add_class::<AuroraRiskDecision>()?;
    m.add_class::<AuroraTrendBias>()?;
    m.add_class::<AuroraRiskState>()?;
    Ok(())
}
