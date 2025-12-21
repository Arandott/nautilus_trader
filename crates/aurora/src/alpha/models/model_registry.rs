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

//! Model registry for versioned alpha predictors (in-memory by default).

use std::collections::HashMap;
use std::sync::Arc;

use anyhow::{Result, bail};

use crate::alpha::{ModelHandle, Predictor};

#[derive(Debug, Clone)]
pub struct ModelMetadata {
    pub version: Arc<str>,
    pub feature_schema_hash: Arc<str>,
    pub model_kind: Arc<str>,
    pub created_at_ns: i64,
    pub notes: Option<Arc<str>>,
}

#[derive(Debug, Clone)]
pub struct ModelEntry {
    pub metadata: ModelMetadata,
    pub predictor: Arc<dyn Predictor>,
}

pub trait ModelRegistry: Send + Sync + std::fmt::Debug {
    fn register(&mut self, entry: ModelEntry) -> Result<()>;
    fn get(&self, version: &str) -> Option<&ModelEntry>;
    fn list_versions(&self) -> Vec<Arc<str>>;
    fn current(&self) -> Option<&ModelEntry>;
    fn current_version(&self) -> Option<&str>;
    fn set_current(&mut self, version: &str) -> Result<()>;
    fn apply_current(&self, handle: &dyn ModelHandle) -> Result<()>;
    fn apply_current_checked(
        &self,
        handle: &dyn ModelHandle,
        expected_feature_schema_hash: &str,
    ) -> Result<()>;
}

#[derive(Debug, Default)]
pub struct InMemoryModelRegistry {
    entries: HashMap<Arc<str>, ModelEntry>,
    current: Option<Arc<str>>,
}

impl InMemoryModelRegistry {
    pub fn new() -> Self {
        Self::default()
    }
}

impl ModelRegistry for InMemoryModelRegistry {
    fn register(&mut self, entry: ModelEntry) -> Result<()> {
        if self.entries.contains_key(&entry.metadata.version) {
            bail!(
                "model version already registered: {}",
                entry.metadata.version
            );
        }
        let version = Arc::clone(&entry.metadata.version);
        self.entries.insert(version, entry);
        Ok(())
    }

    fn get(&self, version: &str) -> Option<&ModelEntry> {
        self.entries.get(version)
    }

    fn list_versions(&self) -> Vec<Arc<str>> {
        let mut versions = self.entries.keys().cloned().collect::<Vec<_>>();
        versions.sort_by(|a, b| a.as_ref().cmp(b.as_ref()));
        versions
    }

    fn current(&self) -> Option<&ModelEntry> {
        let version = self.current.as_ref()?;
        self.entries.get(version)
    }

    fn current_version(&self) -> Option<&str> {
        self.current.as_deref()
    }

    fn set_current(&mut self, version: &str) -> Result<()> {
        let entry = self
            .entries
            .get(version)
            .ok_or_else(|| anyhow::anyhow!("model version not registered: {version}"))?;
        self.current = Some(Arc::clone(&entry.metadata.version));
        Ok(())
    }

    fn apply_current(&self, handle: &dyn ModelHandle) -> Result<()> {
        let entry = self
            .current()
            .ok_or_else(|| anyhow::anyhow!("no current model set"))?;
        handle.swap(Arc::clone(&entry.predictor));
        Ok(())
    }

    fn apply_current_checked(
        &self,
        handle: &dyn ModelHandle,
        expected_feature_schema_hash: &str,
    ) -> Result<()> {
        let entry = self
            .current()
            .ok_or_else(|| anyhow::anyhow!("no current model set"))?;
        if entry.metadata.feature_schema_hash.as_ref() != expected_feature_schema_hash {
            bail!(
                "feature schema hash mismatch: expected {expected_feature_schema_hash}, got {}",
                entry.metadata.feature_schema_hash
            );
        }
        handle.swap(Arc::clone(&entry.predictor));
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use anyhow::Result as AnyResult;
    use crate::alpha::ArcSwapModelHandle;

    #[derive(Debug)]
    struct DummyPredictor {
        value: f64,
        version: &'static str,
    }

    impl Predictor for DummyPredictor {
        fn predict(&self, _x: &[f64]) -> AnyResult<f64> {
            Ok(self.value)
        }

        fn dimension(&self) -> usize {
            1
        }

        fn version(&self) -> &str {
            self.version
        }
    }

    #[test]
    fn registry_registers_and_sets_current() {
        let p1: Arc<dyn Predictor> = Arc::new(DummyPredictor {
            value: 1.0,
            version: "v1",
        });
        let p2: Arc<dyn Predictor> = Arc::new(DummyPredictor {
            value: 2.0,
            version: "v2",
        });
        let mut registry = InMemoryModelRegistry::new();
        registry
            .register(ModelEntry {
                metadata: ModelMetadata {
                    version: Arc::from("v1"),
                    feature_schema_hash: Arc::from("schema"),
                    model_kind: Arc::from("dummy"),
                    created_at_ns: 1,
                    notes: None,
                },
                predictor: p1,
            })
            .unwrap();
        registry
            .register(ModelEntry {
                metadata: ModelMetadata {
                    version: Arc::from("v2"),
                    feature_schema_hash: Arc::from("schema"),
                    model_kind: Arc::from("dummy"),
                    created_at_ns: 2,
                    notes: None,
                },
                predictor: p2,
            })
            .unwrap();

        registry.set_current("v2").unwrap();
        assert_eq!(registry.current_version(), Some("v2"));
        let versions = registry.list_versions();
        assert_eq!(versions.len(), 2);
    }

    #[test]
    fn registry_rejects_duplicate_versions() {
        let p1: Arc<dyn Predictor> = Arc::new(DummyPredictor {
            value: 1.0,
            version: "v1",
        });
        let mut registry = InMemoryModelRegistry::new();
        registry
            .register(ModelEntry {
                metadata: ModelMetadata {
                    version: Arc::from("v1"),
                    feature_schema_hash: Arc::from("schema"),
                    model_kind: Arc::from("dummy"),
                    created_at_ns: 1,
                    notes: None,
                },
                predictor: Arc::clone(&p1),
            })
            .unwrap();
        let err = registry
            .register(ModelEntry {
                metadata: ModelMetadata {
                    version: Arc::from("v1"),
                    feature_schema_hash: Arc::from("schema"),
                    model_kind: Arc::from("dummy"),
                    created_at_ns: 2,
                    notes: None,
                },
                predictor: p1,
            })
            .unwrap_err();
        assert!(err.to_string().contains("already registered"));
    }

    #[test]
    fn registry_validates_schema_on_apply() {
        let p1: Arc<dyn Predictor> = Arc::new(DummyPredictor {
            value: 1.0,
            version: "v1",
        });
        let mut registry = InMemoryModelRegistry::new();
        registry
            .register(ModelEntry {
                metadata: ModelMetadata {
                    version: Arc::from("v1"),
                    feature_schema_hash: Arc::from("schema-a"),
                    model_kind: Arc::from("dummy"),
                    created_at_ns: 1,
                    notes: None,
                },
                predictor: p1,
            })
            .unwrap();
        registry.set_current("v1").unwrap();
        let handle = Arc::new(ArcSwapModelHandle::new(Arc::new(DummyPredictor {
            value: 0.0,
            version: "seed",
        })));

        let err = registry
            .apply_current_checked(handle.as_ref(), "schema-b")
            .unwrap_err();
        assert!(err.to_string().contains("schema hash mismatch"));
    }
}
