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

use std::{collections::HashMap, io::Cursor, str::FromStr};

use datafusion::arrow::ipc::reader::StreamReader;
use nautilus_core::python::to_pyvalue_err;
use nautilus_model::data::bar::{Bar, BarType};
#[cfg(feature = "extended_bar")]
use nautilus_model::data::extended_bar;
use nautilus_serialization::arrow::DecodeFromRecordBatch;
use pyo3::prelude::*;

#[pyclass]
pub struct BarDataWrangler {
    bar_type: BarType,
    price_precision: u8,
    size_precision: u8,
    metadata: HashMap<String, String>,
}

#[pymethods]
impl BarDataWrangler {
    #[new]
    fn py_new(bar_type: &str, price_precision: u8, size_precision: u8) -> PyResult<Self> {
        let bar_type = BarType::from_str(bar_type).map_err(to_pyvalue_err)?;
        #[allow(unused_mut)]
        let mut metadata = Bar::get_metadata(&bar_type, price_precision, size_precision);

        #[cfg(feature = "extended_bar")]
        append_extended_bar_metadata(&mut metadata, price_precision, size_precision);

        Ok(Self {
            bar_type,
            price_precision,
            size_precision,
            metadata,
        })
    }

    #[getter]
    fn bar_type(&self) -> String {
        self.bar_type.to_string()
    }

    #[getter]
    const fn price_precision(&self) -> u8 {
        self.price_precision
    }

    #[getter]
    const fn size_precision(&self) -> u8 {
        self.size_precision
    }

    fn process_record_batch_bytes(&self, data: &[u8]) -> PyResult<Vec<Bar>> {
        // Create a StreamReader (from Arrow IPC)
        let cursor = Cursor::new(data);
        let reader = match StreamReader::try_new(cursor, None) {
            Ok(reader) => reader,
            Err(e) => return Err(to_pyvalue_err(e)),
        };

        let mut bars = Vec::new();

        // Read the record batches
        for maybe_batch in reader {
            let record_batch = match maybe_batch {
                Ok(record_batch) => record_batch,
                Err(e) => return Err(to_pyvalue_err(e)),
            };

            let batch_bars =
                Bar::decode_batch(&self.metadata, record_batch).map_err(to_pyvalue_err)?;
            bars.extend(batch_bars);
        }

        Ok(bars)
    }
}

#[cfg(feature = "extended_bar")]
const KEY_EXT_FIELDS: &str = "ext_fields";
#[cfg(feature = "extended_bar")]
const KEY_EXT_FIELD_PREFIX: &str = "ext_field.";
#[cfg(feature = "extended_bar")]
const KEY_EXT_FIELD_TYPE_SUFFIX: &str = ".type";
#[cfg(feature = "extended_bar")]
const KEY_EXT_FIELD_PRECISION_SUFFIX: &str = ".precision";

#[cfg(feature = "extended_bar")]
fn append_extended_bar_metadata(
    metadata: &mut HashMap<String, String>,
    price_precision: u8,
    size_precision: u8,
) {
    use nautilus_model::data::extended_bar::FieldType;

    let specs = extended_bar::field_specs();
    if specs.is_empty() {
        metadata.remove(KEY_EXT_FIELDS);
        return;
    }

    let mut order = Vec::new();
    for spec in specs {
        order.push(spec.ident);

        let type_key = format!(
            "{KEY_EXT_FIELD_PREFIX}{}{KEY_EXT_FIELD_TYPE_SUFFIX}",
            spec.ident
        );
        metadata.insert(type_key, spec.field_type.label().to_string());

        if matches!(spec.field_type, FieldType::Quantity | FieldType::Price) {
            if let Some(precision) = resolve_precision(spec, price_precision, size_precision) {
                let precision_key = format!(
                    "{KEY_EXT_FIELD_PREFIX}{}{KEY_EXT_FIELD_PRECISION_SUFFIX}",
                    spec.ident
                );
                metadata.insert(precision_key, precision.to_string());
            }
        }
    }

    metadata.insert(KEY_EXT_FIELDS.to_string(), order.join(","));
}

#[cfg(feature = "extended_bar")]
fn resolve_precision(
    spec: &extended_bar::FieldSpec,
    price_precision: u8,
    size_precision: u8,
) -> Option<u8> {
    use nautilus_model::data::extended_bar::FieldType;

    match spec.field_type {
        FieldType::Quantity => match spec.precision {
            Some("size") | None => Some(size_precision),
            Some("price") => Some(price_precision),
            Some(other) => other.parse::<u8>().ok(),
        },
        FieldType::Price => match spec.precision {
            Some("price") | None => Some(price_precision),
            Some("size") => Some(size_precision),
            Some(other) => other.parse::<u8>().ok(),
        },
        FieldType::U64 | FieldType::Bool => None,
    }
}
