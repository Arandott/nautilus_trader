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

//! Shared definitions for compile-time extended bar fields.

#![cfg(feature = "extended_bar")]

/// Describes the Rust type backing an extended field.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum FieldType {
    Quantity,
    Price,
    U64,
    Bool,
}

impl FieldType {
    #[must_use]
    pub fn label(self) -> &'static str {
        match self {
            Self::Quantity => "quantity",
            Self::Price => "price",
            Self::U64 => "u64",
            Self::Bool => "bool",
        }
    }

    #[must_use]
    pub fn from_label(label: &str) -> Option<Self> {
        match label {
            "quantity" => Some(Self::Quantity),
            "price" => Some(Self::Price),
            "u64" => Some(Self::U64),
            "bool" => Some(Self::Bool),
            _ => None,
        }
    }
}

/// Metadata for a configured extended field.
#[derive(Clone, Debug)]
pub struct FieldSpec {
    pub ident: &'static str,
    pub field_type: FieldType,
    pub doc: &'static str,
    pub default: &'static str,
    pub precision: Option<&'static str>,
}

mod generated {
    include!(env!("EXTENDED_BAR_SPEC_PATH"));
}

/// Returns the configured extended field specs.
pub fn field_specs() -> &'static [FieldSpec] {
    generated::EXTENDED_BAR_FIELD_SPECS
}

/// Convenience accessor for a single spec by identifier.
pub fn field_spec(name: &str) -> Option<&'static FieldSpec> {
    field_specs().iter().find(|spec| spec.ident == name)
}
