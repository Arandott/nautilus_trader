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
    ($name:ident, $rust_type:ty, $constructor:expr) => {
        #[pyclass(name = stringify!($name))]
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
create_python_wrapper!(PyMean, Mean, Mean::new);
create_python_wrapper!(PySum, Sum, Sum::new);
create_python_wrapper!(PyMin, Min, Min::new);
create_python_wrapper!(PyMax, Max, Max::new);
create_python_wrapper!(PyMedian, Median, Median::new);
create_python_wrapper!(PyDelta, Delta, Delta::new);
create_python_wrapper!(PyEma, Ema, Ema::new);
create_python_wrapper!(PyWma, Wma, Wma::new);
create_python_wrapper!(PySkew, Skew, Skew::new);
create_python_wrapper!(PyKurtosis, Kurtosis, Kurtosis::new);
create_python_wrapper!(PyMad, Mad, Mad::new);
create_python_wrapper!(PyProduct, Product, Product::new);
create_python_wrapper!(PyPctChange, PctChange, PctChange::new);

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
    operator_name: &str,
    window_size: usize,
    kwargs: Option<&PyDict>,
) -> PyResult<PyObject> {
    Python::with_gil(|py| {
        match operator_name {
            "TS_Mean" => Ok(PyMean::py_new(window_size)?.into_py(py)),
            "TS_Sum" => Ok(PySum::py_new(window_size)?.into_py(py)),
            "TS_Min" => Ok(PyMin::py_new(window_size)?.into_py(py)),
            "TS_Max" => Ok(PyMax::py_new(window_size)?.into_py(py)),
            "TS_Med" => Ok(PyMedian::py_new(window_size)?.into_py(py)),
            "TS_Delta" => Ok(PyDelta::py_new(window_size)?.into_py(py)),
            "TS_EMA" => Ok(PyEma::py_new(window_size)?.into_py(py)),
            "TS_WMA" => Ok(PyWma::py_new(window_size)?.into_py(py)),
            "TS_Skew" => Ok(PySkew::py_new(window_size)?.into_py(py)),
            "TS_Kurt" => Ok(PyKurtosis::py_new(window_size)?.into_py(py)),
            "TS_Mad" => Ok(PyMad::py_new(window_size)?.into_py(py)),
            "TS_Product" => Ok(PyProduct::py_new(window_size)?.into_py(py)),
            "TS_PctChg" => Ok(PyPctChange::py_new(window_size)?.into_py(py)),
            "TS_Std" => {
                let ddof = kwargs
                    .and_then(|d| d.get_item("ddof"))
                    .and_then(|v| v.extract::<usize>().ok())
                    .unwrap_or(1);
                Ok(PyStd::py_new(window_size, ddof)?.into_py(py))
            }
            "TS_Var" => {
                let ddof = kwargs
                    .and_then(|d| d.get_item("ddof"))
                    .and_then(|v| v.extract::<usize>().ok())
                    .unwrap_or(1);
                Ok(PyVar::py_new(window_size, ddof)?.into_py(py))
            }
            _ => Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
                format!("Unknown operator: {}", operator_name),
            )),
        }
    })
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