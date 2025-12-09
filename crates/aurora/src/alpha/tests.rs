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

use super::{AlphaModel, RlsAlpha, RlsParams};
#[test]
fn rls_new_rejects_bad_params() {
    assert!(RlsAlpha::new(0, RlsParams::default()).is_err());
    assert!(
        RlsAlpha::new(
            2,
            RlsParams {
                ridge: 0.0,
                ..Default::default()
            }
        )
        .is_err()
    );
    assert!(
        RlsAlpha::new(
            2,
            RlsParams {
                a_max_bps: -1.0,
                ..Default::default()
            }
        )
        .is_err()
    );
    assert!(
        RlsAlpha::new(
            2,
            RlsParams {
                forgetting: 1.5,
                ..Default::default()
            }
        )
        .is_err()
    );
}

#[test]
fn rls_dimension_mismatch_errors() {
    let mut model = RlsAlpha::new(2, RlsParams::default()).unwrap();
    assert!(model.predict(&[1.0]).is_err());
    assert!(model.update(&[1.0], 0.0).is_err());
}

#[test]
fn rls_clips_prediction() {
    let mut model = RlsAlpha::new(
        1,
        RlsParams {
            a_max_bps: 1.0,
            ..Default::default()
        },
    )
    .unwrap();
    // Drive weight upward with a large target then ensure prediction is clipped.
    model.update(&[10.0], 100.0).unwrap();
    let out = model.predict(&[10.0]).unwrap();
    assert_eq!(out, 1.0);
}

#[test]
fn rls_learns_simple_signal() {
    let mut model = RlsAlpha::new(
        1,
        RlsParams {
            forgetting: 0.9,
            ridge: 1.0,
            a_max_bps: 10.0,
        },
    )
    .unwrap();
    for _ in 0..50 {
        model.update(&[1.0], 5.0).unwrap();
    }
    let w = model.weights()[0];
    assert!((w - 5.0).abs() < 0.5);
    let pred = model.predict(&[1.0]).unwrap();
    assert!((pred - 5.0).abs() < 0.5);
}
