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

//! Python bindings for FactorExp operators and indicators.

use pyo3::prelude::*;
use pyo3::types::PyDict;
use crate::operators::{
    RollingOperator,
    rolling::{Mean, Sum, Std, Var, Min, Max, Median, Delta},
    ma::{Ema, Wma},
    stats::{Skew, Kurtosis, Mad, Product, PctChange},
};

mod indicator;
use indicator::{PyFactorExpIndicator, compile_expression_from_python};

/// Base Python wrapper for Rust operators.
macro_rules! create_python_wrapper {
    ($name:ident, $rust_type:ty, $constructor:expr, $pyname:literal) => {
        #[pyclass(name = $pyname)]
        pub struct $name {
            inner: $rust_type,
        }

        #[pymethods]
        impl $name {
            #[new]
            #[pyo3(signature = (window_size))]
            fn py_new(window_size: usize) -> PyResult<Self> {
                Ok(Self {
                    inner: $constructor(window_size),
                })
            }

            fn __repr__(&self) -> String {
                format!("{}(window_size={})", self.inner.name(), self.inner.window_size())
            }

            #[getter]
            fn name(&self) -> &str {
                self.inner.name()
            }

            #[getter]
            fn window_size(&self) -> usize {
                self.inner.window_size()
            }

            #[getter]
            fn is_ready(&self) -> bool {
                self.inner.is_ready()
            }

            #[getter]
            fn value(&self) -> f64 {
                self.inner.value()
            }

            #[getter]
            fn count(&self) -> usize {
                self.inner.count()
            }

            fn update(&mut self, value: f64) {
                self.inner.update(value);
            }

            fn reset(&mut self) {
                self.inner.reset();
            }
        }
    };
}

// Create Python wrappers for all operators
create_python_wrapper!(PyMean, Mean, Mean::new, "Mean");
create_python_wrapper!(PySum, Sum, Sum::new, "Sum");
create_python_wrapper!(PyMin, Min, Min::new, "Min");
create_python_wrapper!(PyMax, Max, Max::new, "Max");
create_python_wrapper!(PyMedian, Median, Median::new, "Median");
create_python_wrapper!(PyDelta, Delta, Delta::new, "Delta");
create_python_wrapper!(PyEma, Ema, Ema::new, "Ema");
create_python_wrapper!(PyWma, Wma, Wma::new, "Wma");
create_python_wrapper!(PySkew, Skew, Skew::new, "Skew");
create_python_wrapper!(PyKurtosis, Kurtosis, Kurtosis::new, "Kurtosis");
create_python_wrapper!(PyMad, Mad, Mad::new, "Mad");
create_python_wrapper!(PyProduct, Product, Product::new, "Product");
create_python_wrapper!(PyPctChange, PctChange, PctChange::new, "PctChange");

// Special handling for Std and Var which take ddof parameter
#[pyclass(name = "Std")]
pub struct PyStd {
    inner: Std,
}

#[pymethods]
impl PyStd {
    #[new]
    #[pyo3(signature = (window_size, ddof=1))]
    fn py_new(window_size: usize, ddof: usize) -> PyResult<Self> {
        Ok(Self {
            inner: Std::new(window_size, ddof),
        })
    }

    fn __repr__(&self) -> String {
        format!("Std(window_size={})", self.inner.window_size())
    }

    #[getter]
    fn name(&self) -> &str {
        self.inner.name()
    }

    #[getter]
    fn window_size(&self) -> usize {
        self.inner.window_size()
    }

    #[getter]
    fn is_ready(&self) -> bool {
        self.inner.is_ready()
    }

    #[getter]
    fn value(&self) -> f64 {
        self.inner.value()
    }

    #[getter]
    fn count(&self) -> usize {
        self.inner.count()
    }

    fn update(&mut self, value: f64) {
        self.inner.update(value);
    }

    fn reset(&mut self) {
        self.inner.reset();
    }
}

#[pyclass(name = "Var")]
pub struct PyVar {
    inner: Var,
}

#[pymethods]
impl PyVar {
    #[new]
    #[pyo3(signature = (window_size, ddof=1))]
    fn py_new(window_size: usize, ddof: usize) -> PyResult<Self> {
        Ok(Self {
            inner: Var::new(window_size, ddof),
        })
    }

    fn __repr__(&self) -> String {
        format!("Var(window_size={})", self.inner.window_size())
    }

    #[getter]
    fn name(&self) -> &str {
        self.inner.name()
    }

    #[getter]
    fn window_size(&self) -> usize {
        self.inner.window_size()
    }

    #[getter]
    fn is_ready(&self) -> bool {
        self.inner.is_ready()
    }

    #[getter]
    fn value(&self) -> f64 {
        self.inner.value()
    }

    #[getter]
    fn count(&self) -> usize {
        self.inner.count()
    }

    fn update(&mut self, value: f64) {
        self.inner.update(value);
    }

    fn reset(&mut self) {
        self.inner.reset();
    }
}

/// Factory function to create operators by name.
#[pyfunction]
#[pyo3(signature = (operator_name, window_size, **kwargs))]
pub fn create_operator(
    py: Python<'_>,
    operator_name: &str,
    window_size: usize,
    kwargs: Option<&Bound<'_, PyDict>>,
) -> PyResult<PyObject> {
    match operator_name {
        "TS_Mean" => Ok(Py::new(py, PyMean::py_new(window_size)?)?.into_any()),
        "TS_Sum" => Ok(Py::new(py, PySum::py_new(window_size)?)?.into_any()),
        "TS_Min" => Ok(Py::new(py, PyMin::py_new(window_size)?)?.into_any()),
        "TS_Max" => Ok(Py::new(py, PyMax::py_new(window_size)?)?.into_any()),
        "TS_Med" => Ok(Py::new(py, PyMedian::py_new(window_size)?)?.into_any()),
        "TS_Delta" => Ok(Py::new(py, PyDelta::py_new(window_size)?)?.into_any()),
        "TS_EMA" => Ok(Py::new(py, PyEma::py_new(window_size)?)?.into_any()),
        "TS_WMA" => Ok(Py::new(py, PyWma::py_new(window_size)?)?.into_any()),
        "TS_Skew" => Ok(Py::new(py, PySkew::py_new(window_size)?)?.into_any()),
        "TS_Kurt" => Ok(Py::new(py, PyKurtosis::py_new(window_size)?)?.into_any()),
        "TS_Mad" => Ok(Py::new(py, PyMad::py_new(window_size)?)?.into_any()),
        "TS_Product" => Ok(Py::new(py, PyProduct::py_new(window_size)?)?.into_any()),
        "TS_PctChg" => Ok(Py::new(py, PyPctChange::py_new(window_size)?)?.into_any()),
        "TS_Std" => {
            let ddof = kwargs
                .and_then(|d| d.get_item("ddof").ok().flatten())
                .and_then(|v| v.extract::<usize>().ok())
                .unwrap_or(1);
            Ok(Py::new(py, PyStd::py_new(window_size, ddof)?)?.into_any())
        }
        "TS_Var" => {
            let ddof = kwargs
                .and_then(|d| d.get_item("ddof").ok().flatten())
                .and_then(|v| v.extract::<usize>().ok())
                .unwrap_or(1);
            Ok(Py::new(py, PyVar::py_new(window_size, ddof)?)?.into_any())
        }
        _ => Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
            format!("Unknown operator: {}", operator_name),
        )),
    }
}

/// Python module definition.
#[pymodule]
pub fn factorexp(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Register indicator class
    m.add_class::<PyFactorExpIndicator>()?;
    
    // Register all operator classes
    m.add_class::<PyMean>()?;
    m.add_class::<PySum>()?;
    m.add_class::<PyStd>()?;
    m.add_class::<PyVar>()?;
    m.add_class::<PyMin>()?;
    m.add_class::<PyMax>()?;
    m.add_class::<PyMedian>()?;
    m.add_class::<PyDelta>()?;
    m.add_class::<PyEma>()?;
    m.add_class::<PyWma>()?;
    m.add_class::<PySkew>()?;
    m.add_class::<PyKurtosis>()?;
    m.add_class::<PyMad>()?;
    m.add_class::<PyProduct>()?;
    m.add_class::<PyPctChange>()?;
    
    // Register factory functions
    m.add_function(wrap_pyfunction!(create_operator, m)?)?;
    m.add_function(wrap_pyfunction!(compile_expression_from_python, m)?)?;
    
    Ok(())
}