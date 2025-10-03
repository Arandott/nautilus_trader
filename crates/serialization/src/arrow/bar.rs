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

use std::{collections::HashMap, str::FromStr, sync::Arc};

use arrow::{
    array::{
        Array, ArrayRef, BooleanArray, BooleanBuilder, FixedSizeBinaryArray, FixedSizeBinaryBuilder,
        UInt64Array, UInt64Builder,
    },
    datatypes::{DataType, Field, Schema},
    error::ArrowError,
    record_batch::RecordBatch,
};
#[cfg(feature = "extended_bar")]
use extended_bar_macros::{
    bool_get_by_name, bool_set_by_name, price_get_by_name, price_set_by_name,
    quantity_get_by_name, quantity_set_by_name, u64_get_by_name, u64_set_by_name,
};
#[cfg(feature = "extended_bar")]
use nautilus_model::data::extended_bar;
use nautilus_model::{
    data::{Bar, BarType},
    types::{Price, Quantity, fixed::PRECISION_BYTES},
};

use super::{
    DecodeDataFromRecordBatch, EncodingError, KEY_BAR_TYPE, KEY_PRICE_PRECISION,
    KEY_SIZE_PRECISION, extract_column, get_raw_quantity,
};
use crate::arrow::{
    ArrowSchemaProvider, Data, DecodeFromRecordBatch, EncodeToRecordBatch, get_raw_price,
};

#[cfg(feature = "extended_bar")]
const KEY_EXT_FIELDS: &str = "ext_fields";
#[cfg(feature = "extended_bar")]
const KEY_EXT_FIELD_PREFIX: &str = "ext_field.";
#[cfg(feature = "extended_bar")]
const KEY_EXT_FIELD_TYPE_SUFFIX: &str = ".type";
#[cfg(feature = "extended_bar")]
const KEY_EXT_FIELD_PRECISION_SUFFIX: &str = ".precision";

const BASE_BAR_COLUMN_COUNT: usize = 7;

#[cfg(feature = "extended_bar")]
#[derive(Clone, Debug)]
struct ExtColumn {
    spec: &'static extended_bar::FieldSpec,
    precision: Option<u8>,
}

#[cfg(feature = "extended_bar")]
impl ExtColumn {
    fn ident(&self) -> &'static str {
        self.spec.ident
    }

    fn field_type(&self) -> extended_bar::FieldType {
        self.spec.field_type
    }

    fn arrow_field(&self) -> Field {
        match self.field_type() {
            extended_bar::FieldType::Quantity | extended_bar::FieldType::Price => Field::new(
                self.ident(),
                DataType::FixedSizeBinary(PRECISION_BYTES),
                true,
            ),
            extended_bar::FieldType::U64 => Field::new(self.ident(), DataType::UInt64, true),
            extended_bar::FieldType::Bool => Field::new(self.ident(), DataType::Boolean, true),
        }
    }
}

#[cfg(feature = "extended_bar")]
enum ExtColumnBuilder {
    Quantity(FixedSizeBinaryBuilder),
    Price(FixedSizeBinaryBuilder),
    U64(UInt64Builder),
    Bool(BooleanBuilder),
}

#[cfg(feature = "extended_bar")]
impl ExtColumnBuilder {
    fn new(column: &ExtColumn, capacity: usize) -> Self {
        match column.field_type() {
            extended_bar::FieldType::Quantity => Self::Quantity(FixedSizeBinaryBuilder::with_capacity(
                capacity,
                PRECISION_BYTES,
            )),
            extended_bar::FieldType::Price => Self::Price(FixedSizeBinaryBuilder::with_capacity(
                capacity,
                PRECISION_BYTES,
            )),
            extended_bar::FieldType::U64 => Self::U64(UInt64Builder::with_capacity(capacity)),
            extended_bar::FieldType::Bool => Self::Bool(BooleanBuilder::with_capacity(capacity)),
        }
    }

    fn append_value(&mut self, column: &mut ExtColumn, bar: &Bar) {
        match (self, column.field_type()) {
            (Self::Quantity(builder), extended_bar::FieldType::Quantity) => {
                if let Some(value) = quantity_get_by_name!(bar, column.ident()) {
                    let quantity: ::nautilus_model::types::Quantity = value;
                    let raw_bytes = quantity.raw.to_le_bytes();
                    let _ = builder.append_value(raw_bytes);
                    column.precision = column.precision.or(Some(quantity.precision));
                } else {
                    let _ = builder.append_null();
                }
            }
            (Self::Price(builder), extended_bar::FieldType::Price) => {
                if let Some(value) = price_get_by_name!(bar, column.ident()) {
                    let price: ::nautilus_model::types::Price = value;
                    let raw_bytes = price.raw.to_le_bytes();
                    let _ = builder.append_value(raw_bytes);
                    column.precision = column.precision.or(Some(price.precision));
                } else {
                    let _ = builder.append_null();
                }
            }
            (Self::U64(builder), extended_bar::FieldType::U64) => {
                if let Some(value) = u64_get_by_name!(bar, column.ident()) {
                    let _ = builder.append_value(value);
                } else {
                    let _ = builder.append_null();
                }
            }
            (Self::Bool(builder), extended_bar::FieldType::Bool) => {
                if let Some(value) = bool_get_by_name!(bar, column.ident()) {
                    let _ = builder.append_value(value);
                } else {
                    let _ = builder.append_null();
                }
            }
            _ => unreachable!("builder variant does not match extended field type"),
        }
    }

    fn finish(self) -> ArrayRef {
        match self {
            Self::Quantity(mut builder) => Arc::new(builder.finish()) as ArrayRef,
            Self::Price(mut builder) => Arc::new(builder.finish()) as ArrayRef,
            Self::U64(mut builder) => Arc::new(builder.finish()) as ArrayRef,
            Self::Bool(mut builder) => Arc::new(builder.finish()) as ArrayRef,
        }
    }
}

#[cfg(feature = "extended_bar")]
enum ExtColumnArray<'a> {
    Fixed(&'a FixedSizeBinaryArray),
    U64(&'a UInt64Array),
    Bool(&'a BooleanArray),
}

impl ArrowSchemaProvider for Bar {
    fn get_schema(metadata: Option<HashMap<String, String>>) -> Schema {
        #[allow(unused_mut)]
        let mut fields = vec![
            Field::new("open", DataType::FixedSizeBinary(PRECISION_BYTES), false),
            Field::new("high", DataType::FixedSizeBinary(PRECISION_BYTES), false),
            Field::new("low", DataType::FixedSizeBinary(PRECISION_BYTES), false),
            Field::new("close", DataType::FixedSizeBinary(PRECISION_BYTES), false),
            Field::new("volume", DataType::FixedSizeBinary(PRECISION_BYTES), false),
            Field::new("ts_event", DataType::UInt64, false),
            Field::new("ts_init", DataType::UInt64, false),
        ];

        match metadata {
            Some(metadata) => {
                #[cfg(feature = "extended_bar")]
                {
                    let ext_columns = parse_ext_fields_from_metadata(&metadata);
                    for column in &ext_columns {
                        fields.push(column.arrow_field());
                    }
                }

                Schema::new_with_metadata(fields, metadata)
            }
            None => Schema::new(fields),
        }
    }
}

struct ParsedBarMetadata {
    bar_type: BarType,
    price_precision: u8,
    size_precision: u8,
    #[cfg(feature = "extended_bar")]
    ext_columns: Vec<ExtColumn>,
}

fn parse_metadata(metadata: &HashMap<String, String>) -> Result<ParsedBarMetadata, EncodingError> {
    let bar_type_str = metadata
        .get(KEY_BAR_TYPE)
        .ok_or_else(|| EncodingError::MissingMetadata(KEY_BAR_TYPE))?;
    let bar_type = BarType::from_str(bar_type_str)
        .map_err(|e| EncodingError::ParseError(KEY_BAR_TYPE, e.to_string()))?;

    let price_precision = metadata
        .get(KEY_PRICE_PRECISION)
        .ok_or_else(|| EncodingError::MissingMetadata(KEY_PRICE_PRECISION))?
        .parse::<u8>()
        .map_err(|e| EncodingError::ParseError(KEY_PRICE_PRECISION, e.to_string()))?;

    let size_precision = metadata
        .get(KEY_SIZE_PRECISION)
        .ok_or_else(|| EncodingError::MissingMetadata(KEY_SIZE_PRECISION))?
        .parse::<u8>()
        .map_err(|e| EncodingError::ParseError(KEY_SIZE_PRECISION, e.to_string()))?;

    #[cfg(feature = "extended_bar")]
    let ext_columns = parse_ext_fields_from_metadata(metadata);

    Ok(ParsedBarMetadata {
        bar_type,
        price_precision,
        size_precision,
        #[cfg(feature = "extended_bar")]
        ext_columns,
    })
}

impl EncodeToRecordBatch for Bar {
    fn encode_batch(
        metadata: &HashMap<String, String>,
        data: &[Self],
    ) -> Result<RecordBatch, ArrowError> {
        let mut open_builder = FixedSizeBinaryBuilder::with_capacity(data.len(), PRECISION_BYTES);
        let mut high_builder = FixedSizeBinaryBuilder::with_capacity(data.len(), PRECISION_BYTES);
        let mut low_builder = FixedSizeBinaryBuilder::with_capacity(data.len(), PRECISION_BYTES);
        let mut close_builder = FixedSizeBinaryBuilder::with_capacity(data.len(), PRECISION_BYTES);
        let mut volume_builder = FixedSizeBinaryBuilder::with_capacity(data.len(), PRECISION_BYTES);
        let mut ts_event_builder = UInt64Array::builder(data.len());
        let mut ts_init_builder = UInt64Array::builder(data.len());

        #[cfg(feature = "extended_bar")]
        let mut ext_columns = collect_ext_columns_from_data(data);
        #[cfg(feature = "extended_bar")]
        let mut ext_builders: Vec<ExtColumnBuilder> = ext_columns
            .iter()
            .map(|column| ExtColumnBuilder::new(column, data.len()))
            .collect();

        for bar in data {
            open_builder
                .append_value(bar.open.raw.to_le_bytes())
                .unwrap();
            high_builder
                .append_value(bar.high.raw.to_le_bytes())
                .unwrap();
            low_builder.append_value(bar.low.raw.to_le_bytes()).unwrap();
            close_builder
                .append_value(bar.close.raw.to_le_bytes())
                .unwrap();
            volume_builder
                .append_value(bar.volume.raw.to_le_bytes())
                .unwrap();
            ts_event_builder.append_value(bar.ts_event.as_u64());
            ts_init_builder.append_value(bar.ts_init.as_u64());

            #[cfg(feature = "extended_bar")]
            for (column, builder) in ext_columns.iter_mut().zip(ext_builders.iter_mut()) {
                builder.append_value(column, bar);
            }
        }

        let open_array = open_builder.finish();
        let high_array = high_builder.finish();
        let low_array = low_builder.finish();
        let close_array = close_builder.finish();
        let volume_array = volume_builder.finish();
        let ts_event_array = ts_event_builder.finish();
        let ts_init_array = ts_init_builder.finish();

        #[allow(unused_mut)]
        let mut columns: Vec<ArrayRef> = vec![
            Arc::new(open_array) as ArrayRef,
            Arc::new(high_array) as ArrayRef,
            Arc::new(low_array) as ArrayRef,
            Arc::new(close_array) as ArrayRef,
            Arc::new(volume_array) as ArrayRef,
            Arc::new(ts_event_array) as ArrayRef,
            Arc::new(ts_init_array) as ArrayRef,
        ];

        #[cfg(feature = "extended_bar")]
        for builder in ext_builders {
            columns.push(builder.finish());
        }

        RecordBatch::try_new(Self::get_schema(Some(metadata.clone())).into(), columns)
    }

    fn metadata(&self) -> HashMap<String, String> {
        #[allow(unused_mut)]
        let mut metadata =
            Bar::get_metadata(&self.bar_type, self.open.precision, self.volume.precision);
        #[cfg(feature = "extended_bar")]
        {
            let columns = collect_ext_columns_from_data(std::slice::from_ref(self));
            insert_ext_columns_into_metadata(&mut metadata, &columns);
        }
        metadata
    }

    fn chunk_metadata(chunk: &[Self]) -> HashMap<String, String> {
        assert!(
            !chunk.is_empty(),
            "Chunk must have atleast one element to encode"
        );
        let first = &chunk[0];
        #[allow(unused_mut)]
        let mut metadata = Bar::get_metadata(
            &first.bar_type,
            first.open.precision,
            first.volume.precision,
        );

        #[cfg(feature = "extended_bar")]
        {
            let columns = collect_ext_columns_from_data(chunk);
            insert_ext_columns_into_metadata(&mut metadata, &columns);
        }

        metadata
    }
}

impl DecodeFromRecordBatch for Bar {
    fn decode_batch(
        metadata: &HashMap<String, String>,
        record_batch: RecordBatch,
    ) -> Result<Vec<Self>, EncodingError> {
        let parsed = parse_metadata(metadata)?;
        let bar_type = parsed.bar_type;
        let price_precision = parsed.price_precision;
        let size_precision = parsed.size_precision;
        let cols = record_batch.columns();

        let open_values = extract_column::<FixedSizeBinaryArray>(
            cols,
            "open",
            0,
            DataType::FixedSizeBinary(PRECISION_BYTES),
        )?;
        let high_values = extract_column::<FixedSizeBinaryArray>(
            cols,
            "high",
            1,
            DataType::FixedSizeBinary(PRECISION_BYTES),
        )?;
        let low_values = extract_column::<FixedSizeBinaryArray>(
            cols,
            "low",
            2,
            DataType::FixedSizeBinary(PRECISION_BYTES),
        )?;
        let close_values = extract_column::<FixedSizeBinaryArray>(
            cols,
            "close",
            3,
            DataType::FixedSizeBinary(PRECISION_BYTES),
        )?;
        let volume_values = extract_column::<FixedSizeBinaryArray>(
            cols,
            "volume",
            4,
            DataType::FixedSizeBinary(PRECISION_BYTES),
        )?;
        let ts_event_values = extract_column::<UInt64Array>(cols, "ts_event", 5, DataType::UInt64)?;
        let ts_init_values = extract_column::<UInt64Array>(cols, "ts_init", 6, DataType::UInt64)?;

        #[cfg(feature = "extended_bar")]
        let ext_arrays: Vec<ExtColumnArray<'_>> = parsed
            .ext_columns
            .iter()
            .enumerate()
            .map(|(idx, column)| {
                let column_index = BASE_BAR_COLUMN_COUNT + idx;
                match column.field_type() {
                    extended_bar::FieldType::Quantity | extended_bar::FieldType::Price => {
                        extract_column::<FixedSizeBinaryArray>(
                            cols,
                            column.ident(),
                            column_index,
                            DataType::FixedSizeBinary(PRECISION_BYTES),
                        )
                        .map(ExtColumnArray::Fixed)
                    }
                    extended_bar::FieldType::U64 => extract_column::<UInt64Array>(
                        cols,
                        column.ident(),
                        column_index,
                        DataType::UInt64,
                    )
                    .map(ExtColumnArray::U64),
                    extended_bar::FieldType::Bool => extract_column::<BooleanArray>(
                        cols,
                        column.ident(),
                        column_index,
                        DataType::Boolean,
                    )
                    .map(ExtColumnArray::Bool),
                }
            })
            .collect::<Result<_, _>>()?;

        let result: Result<Vec<Self>, EncodingError> = (0..record_batch.num_rows())
            .map(|i| {
                let open = Price::from_raw(get_raw_price(open_values.value(i)), price_precision);
                let high = Price::from_raw(get_raw_price(high_values.value(i)), price_precision);
                let low = Price::from_raw(get_raw_price(low_values.value(i)), price_precision);
                let close = Price::from_raw(get_raw_price(close_values.value(i)), price_precision);
                let volume =
                    Quantity::from_raw(get_raw_quantity(volume_values.value(i)), size_precision);
                let ts_event = ts_event_values.value(i).into();
                let ts_init = ts_init_values.value(i).into();

                let mut bar = nautilus_model::bar_new_with_defaults!(
                    bar_type, open, high, low, close, volume, ts_event, ts_init,
                );

                #[cfg(feature = "extended_bar")]
                for (column, array) in parsed.ext_columns.iter().zip(ext_arrays.iter()) {
                    match (column.field_type(), array) {
                        (extended_bar::FieldType::Quantity, ExtColumnArray::Fixed(values)) => {
                            if values.is_null(i) {
                                continue;
                            }
                            let raw = get_raw_quantity(values.value(i));
                            let precision = column.precision.unwrap_or(size_precision);
                            let quantity = Quantity::from_raw(raw, precision);
                            let set = quantity_set_by_name!(bar, column.ident(), quantity);
                            debug_assert!(
                                set,
                                "Failed to assign extended bar field {}",
                                column.ident()
                            );
                        }
                        (extended_bar::FieldType::Price, ExtColumnArray::Fixed(values)) => {
                            if values.is_null(i) {
                                continue;
                            }
                            let raw = get_raw_price(values.value(i));
                            let precision = column.precision.unwrap_or(price_precision);
                            let _price = Price::from_raw(raw, precision);
                            let set = price_set_by_name!(bar, column.ident(), _price);
                            debug_assert!(
                                set,
                                "Failed to assign extended bar field {}",
                                column.ident()
                            );
                        }
                        (extended_bar::FieldType::U64, ExtColumnArray::U64(values)) => {
                            if values.is_null(i) {
                                continue;
                            }
                            let _value = values.value(i);
                            let set = u64_set_by_name!(bar, column.ident(), _value);
                            debug_assert!(
                                set,
                                "Failed to assign extended bar field {}",
                                column.ident()
                            );
                        }
                        (extended_bar::FieldType::Bool, ExtColumnArray::Bool(values)) => {
                            if values.is_null(i) {
                                continue;
                            }
                            let _value = values.value(i);
                            let set = bool_set_by_name!(bar, column.ident(), _value);
                            debug_assert!(
                                set,
                                "Failed to assign extended bar field {}",
                                column.ident()
                            );
                        }
                        _ => unreachable!("extended column array does not match field type"),
                    }
                }

                Ok(bar)
            })
            .collect();

        result
    }
}

impl DecodeDataFromRecordBatch for Bar {
    fn decode_data_batch(
        metadata: &HashMap<String, String>,
        record_batch: RecordBatch,
    ) -> Result<Vec<Data>, EncodingError> {
        let bars: Vec<Self> = Self::decode_batch(metadata, record_batch)?;
        Ok(bars.into_iter().map(Data::from).collect())
    }
}

#[cfg(feature = "extended_bar")]
fn collect_ext_columns_from_data(data: &[Bar]) -> Vec<ExtColumn> {
    let mut columns: Vec<ExtColumn> = extended_bar::field_specs()
        .iter()
        .map(|spec| ExtColumn {
            spec,
            precision: None,
        })
        .collect();

    for bar in data {
        for column in &mut columns {
            match column.field_type() {
                extended_bar::FieldType::Quantity => {
                    if let Some(value) = quantity_get_by_name!(bar, column.ident()) {
                        let quantity: ::nautilus_model::types::Quantity = value;
                        column.precision = column.precision.or(Some(quantity.precision));
                    }
                }
                extended_bar::FieldType::Price => {
                    if let Some(value) = price_get_by_name!(bar, column.ident()) {
                        let price: ::nautilus_model::types::Price = value;
                        column.precision = column.precision.or(Some(price.precision));
                    }
                }
                extended_bar::FieldType::U64 | extended_bar::FieldType::Bool => {}
            }
        }
    }

    columns
}

#[cfg(feature = "extended_bar")]
fn insert_ext_columns_into_metadata(metadata: &mut HashMap<String, String>, columns: &[ExtColumn]) {
    if columns.is_empty() {
        metadata.remove(KEY_EXT_FIELDS);
        return;
    }

    let order = columns
        .iter()
        .map(|column| column.ident())
        .collect::<Vec<_>>()
        .join(",");

    metadata.insert(KEY_EXT_FIELDS.to_string(), order);

    for column in columns {
        let type_key = format!(
            "{KEY_EXT_FIELD_PREFIX}{}{KEY_EXT_FIELD_TYPE_SUFFIX}",
            column.ident()
        );
        metadata.insert(type_key, column.field_type().label().to_string());

        if let Some(precision) = column.precision {
            let precision_key = format!(
                "{KEY_EXT_FIELD_PREFIX}{}{KEY_EXT_FIELD_PRECISION_SUFFIX}",
                column.ident()
            );
            metadata.insert(precision_key, precision.to_string());
        }
    }
}

#[cfg(feature = "extended_bar")]
fn parse_ext_fields_from_metadata(metadata: &HashMap<String, String>) -> Vec<ExtColumn> {
    let names = metadata
        .get(KEY_EXT_FIELDS)
        .map(|value| {
            value
                .split(',')
                .filter(|name| !name.is_empty())
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();

    names
        .into_iter()
        .filter_map(|name| {
            let spec = extended_bar::field_spec(name)?;

            let type_key = format!("{KEY_EXT_FIELD_PREFIX}{name}{KEY_EXT_FIELD_TYPE_SUFFIX}");
            let resolved_type = metadata
                .get(&type_key)
                .and_then(|label| extended_bar::FieldType::from_label(label))
                .unwrap_or(spec.field_type);

            // If metadata signals a different type than the spec, skip to avoid mismatched decoding.
            if resolved_type != spec.field_type {
                return None;
            }

            let precision = if matches!(
                spec.field_type,
                extended_bar::FieldType::Quantity | extended_bar::FieldType::Price
            ) {
                let precision_key =
                    format!("{KEY_EXT_FIELD_PREFIX}{name}{KEY_EXT_FIELD_PRECISION_SUFFIX}");
                metadata
                    .get(&precision_key)
                    .and_then(|value| value.parse::<u8>().ok())
            } else {
                None
            };

            Some(ExtColumn { spec, precision })
        })
        .collect()
}

////////////////////////////////////////////////////////////////////////////////
// Tests
////////////////////////////////////////////////////////////////////////////////
#[cfg(test)]
mod tests {
    use std::sync::Arc;

    use arrow::{array::Array, record_batch::RecordBatch};
    use nautilus_model::types::{fixed::FIXED_SCALAR, price::PriceRaw, quantity::QuantityRaw};
    use rstest::rstest;

    use super::*;
    use crate::arrow::get_raw_price;

    #[rstest]
    fn test_get_schema() {
        let bar_type = BarType::from_str("AAPL.XNAS-1-MINUTE-LAST-INTERNAL").unwrap();
        let metadata = Bar::get_metadata(&bar_type, 2, 0);
        let schema = Bar::get_schema(Some(metadata.clone()));
        let expected_fields = vec![
            Field::new("open", DataType::FixedSizeBinary(PRECISION_BYTES), false),
            Field::new("high", DataType::FixedSizeBinary(PRECISION_BYTES), false),
            Field::new("low", DataType::FixedSizeBinary(PRECISION_BYTES), false),
            Field::new("close", DataType::FixedSizeBinary(PRECISION_BYTES), false),
            Field::new("volume", DataType::FixedSizeBinary(PRECISION_BYTES), false),
            Field::new("ts_event", DataType::UInt64, false),
            Field::new("ts_init", DataType::UInt64, false),
        ];
        let expected_schema = Schema::new_with_metadata(expected_fields, metadata);
        assert_eq!(schema, expected_schema);
    }

    #[rstest]
    fn test_get_schema_map() {
        let schema_map = Bar::get_schema_map();
        let mut expected_map = HashMap::new();
        let fixed_size_binary = format!("FixedSizeBinary({PRECISION_BYTES})");
        expected_map.insert("open".to_string(), fixed_size_binary.clone());
        expected_map.insert("high".to_string(), fixed_size_binary.clone());
        expected_map.insert("low".to_string(), fixed_size_binary.clone());
        expected_map.insert("close".to_string(), fixed_size_binary.clone());
        expected_map.insert("volume".to_string(), fixed_size_binary.clone());
        expected_map.insert("ts_event".to_string(), "UInt64".to_string());
        expected_map.insert("ts_init".to_string(), "UInt64".to_string());
        assert_eq!(schema_map, expected_map);
    }

    #[rstest]
    fn test_encode_batch() {
        let bar_type = BarType::from_str("AAPL.XNAS-1-MINUTE-LAST-INTERNAL").unwrap();
        let metadata = Bar::get_metadata(&bar_type, 2, 0);

        let bar1 = nautilus_model::bar_new_with_defaults!(
            bar_type,
            Price::from("100.10"),
            Price::from("102.00"),
            Price::from("100.00"),
            Price::from("101.00"),
            Quantity::from(1100),
            1.into(),
            3.into(),
        );
        let bar2 = nautilus_model::bar_new_with_defaults!(
            bar_type,
            Price::from("100.00"),
            Price::from("100.10"),
            Price::from("100.00"),
            Price::from("100.10"),
            Quantity::from(1110),
            2.into(),
            4.into(),
        );

        let data = vec![bar1, bar2];
        let record_batch = Bar::encode_batch(&metadata, &data).unwrap();

        let columns = record_batch.columns();
        let open_values = columns[0]
            .as_any()
            .downcast_ref::<FixedSizeBinaryArray>()
            .unwrap();
        let high_values = columns[1]
            .as_any()
            .downcast_ref::<FixedSizeBinaryArray>()
            .unwrap();
        let low_values = columns[2]
            .as_any()
            .downcast_ref::<FixedSizeBinaryArray>()
            .unwrap();
        let close_values = columns[3]
            .as_any()
            .downcast_ref::<FixedSizeBinaryArray>()
            .unwrap();
        let volume_values = columns[4]
            .as_any()
            .downcast_ref::<FixedSizeBinaryArray>()
            .unwrap();
        let ts_event_values = columns[5].as_any().downcast_ref::<UInt64Array>().unwrap();
        let ts_init_values = columns[6].as_any().downcast_ref::<UInt64Array>().unwrap();

        assert_eq!(columns.len(), 7);
        assert_eq!(open_values.len(), 2);
        assert_eq!(
            get_raw_price(open_values.value(0)),
            (100.10 * FIXED_SCALAR) as PriceRaw
        );
        assert_eq!(
            get_raw_price(open_values.value(1)),
            (100.00 * FIXED_SCALAR) as PriceRaw
        );
        assert_eq!(high_values.len(), 2);
        assert_eq!(
            get_raw_price(high_values.value(0)),
            (102.00 * FIXED_SCALAR) as PriceRaw
        );
        assert_eq!(
            get_raw_price(high_values.value(1)),
            (100.10 * FIXED_SCALAR) as PriceRaw
        );
        assert_eq!(low_values.len(), 2);
        assert_eq!(
            get_raw_price(low_values.value(0)),
            (100.00 * FIXED_SCALAR) as PriceRaw
        );
        assert_eq!(
            get_raw_price(low_values.value(1)),
            (100.00 * FIXED_SCALAR) as PriceRaw
        );
        assert_eq!(close_values.len(), 2);
        assert_eq!(
            get_raw_price(close_values.value(0)),
            (101.00 * FIXED_SCALAR) as PriceRaw
        );
        assert_eq!(
            get_raw_price(close_values.value(1)),
            (100.10 * FIXED_SCALAR) as PriceRaw
        );
        assert_eq!(volume_values.len(), 2);
        assert_eq!(
            get_raw_quantity(volume_values.value(0)),
            (1100.0 * FIXED_SCALAR) as QuantityRaw
        );
        assert_eq!(
            get_raw_quantity(volume_values.value(1)),
            (1110.0 * FIXED_SCALAR) as QuantityRaw
        );
        assert_eq!(ts_event_values.len(), 2);
        assert_eq!(ts_event_values.value(0), 1);
        assert_eq!(ts_event_values.value(1), 2);
        assert_eq!(ts_init_values.len(), 2);
        assert_eq!(ts_init_values.value(0), 3);
        assert_eq!(ts_init_values.value(1), 4);
    }

    #[rstest]
    fn test_decode_batch() {
        use nautilus_model::types::{price::PriceRaw, quantity::QuantityRaw};

        let bar_type = BarType::from_str("AAPL.XNAS-1-MINUTE-LAST-INTERNAL").unwrap();
        let metadata = Bar::get_metadata(&bar_type, 2, 0);

        let open = FixedSizeBinaryArray::from(vec![
            &(100_100_000_000 as PriceRaw).to_le_bytes(),
            &(10_000_000_000 as PriceRaw).to_le_bytes(),
        ]);
        let high = FixedSizeBinaryArray::from(vec![
            &(102_000_000_000 as PriceRaw).to_le_bytes(),
            &(10_000_000_000 as PriceRaw).to_le_bytes(),
        ]);
        let low = FixedSizeBinaryArray::from(vec![
            &(100_000_000_000 as PriceRaw).to_le_bytes(),
            &(10_000_000_000 as PriceRaw).to_le_bytes(),
        ]);
        let close = FixedSizeBinaryArray::from(vec![
            &(101_000_000_000 as PriceRaw).to_le_bytes(),
            &(10_010_000_000 as PriceRaw).to_le_bytes(),
        ]);
        let volume = FixedSizeBinaryArray::from(vec![
            &(11_000_000_000 as QuantityRaw).to_le_bytes(),
            &(10_000_000_000 as QuantityRaw).to_le_bytes(),
        ]);
        let ts_event = UInt64Array::from(vec![1, 2]);
        let ts_init = UInt64Array::from(vec![3, 4]);

        let record_batch = RecordBatch::try_new(
            Bar::get_schema(Some(metadata.clone())).into(),
            vec![
                Arc::new(open),
                Arc::new(high),
                Arc::new(low),
                Arc::new(close),
                Arc::new(volume),
                Arc::new(ts_event),
                Arc::new(ts_init),
            ],
        )
        .unwrap();

        let decoded_data = Bar::decode_batch(&metadata, record_batch).unwrap();
        assert_eq!(decoded_data.len(), 2);
    }
}
