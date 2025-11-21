import pathlib
import tempfile
import unittest

from nautilus_trader.adapters.binance.common.symbol import BinanceSymbol
from nautilus_trader.model.identifiers import InstrumentId

from Aurora_Lattice.aurora_hdg import AuroraHDGConfig, load_config
from Aurora_Lattice.config_loader import (
    AuroraRuntimeProfile,
    _build_leverage_map,
    build_runtime_profile,
    load_run_bundle,
)


class ConfigTests(unittest.TestCase):
    def test_load_config_returns_strategy_config(self):
        src = pathlib.Path("Aurora_Lattice/configs/default.yaml")
        cfg = load_config(src)
        self.assertIsInstance(cfg, AuroraHDGConfig)
        self.assertGreater(cfg.grid.levels, 0)
        self.assertGreater(cfg.inventory.i_max, cfg.inventory.i_soft)

    def test_run_bundle_returns_runtime_profile(self):
        src = pathlib.Path("Aurora_Lattice/configs/default.yaml")
        strategy, runtime_profile = load_run_bundle(src)
        self.assertIsInstance(strategy, AuroraHDGConfig)
        self.assertIsInstance(runtime_profile, AuroraRuntimeProfile)
        self.assertEqual(len(runtime_profile.clients), 1)
        first_client = runtime_profile.clients[0]
        self.assertIn(strategy.instrument_id, first_client.instrument_ids)
        missing_envs = runtime_profile.missing_envs()
        self.assertIn("BINANCE_API_KEY", missing_envs)
        self.assertIn("BINANCE_API_SECRET", missing_envs)

    def test_okx_sample_uses_single_okx_client(self):
        src = pathlib.Path("Aurora_Lattice/configs/sample_okx.yaml")
        _, runtime_profile = load_run_bundle(src)
        self.assertEqual(len(runtime_profile.clients), 1)
        client = runtime_profile.clients[0]
        self.assertEqual(client.venue, "OKX")
        missing = set(runtime_profile.missing_envs())
        self.assertIn("OKX_API_KEY", missing)
        self.assertIn("OKX_API_PASSPHRASE", missing)

    def test_build_leverage_map_coerces_symbol_to_string(self):
        instrument = InstrumentId.from_str("KASUSDT-PERP.BINANCE")
        result = _build_leverage_map(frozenset({instrument}), 20)
        self.assertEqual(result, {BinanceSymbol("KASUSDT-PERP"): 20})

    def test_build_leverage_map_rejects_non_positive_values(self):
        instrument = InstrumentId.from_str("KASUSDT-PERP.BINANCE")
        with self.assertRaises(ValueError):
            _build_leverage_map(frozenset({instrument}), 0)

    def test_runtime_profile_respects_custom_env_names(self):
        instrument = InstrumentId.from_str("KASUSDT-PERP.BINANCE")
        runtime = {
            "clients": {
                "BINANCE-HEDGE": {
                    "venue": "BINANCE",
                    "credentials": {
                        "api_key_env": "CUSTOM_KEY",
                        "api_secret_env": "CUSTOM_SECRET",
                    },
                },
            },
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            profile = build_runtime_profile(
                runtime,
                config_dir=pathlib.Path(tmpdir),
                default_instrument=instrument,
            )
        creds = profile.clients[0].credentials
        self.assertEqual(creds.env_map["api_key"], "CUSTOM_KEY")
        self.assertEqual(creds.env_map["api_secret"], "CUSTOM_SECRET")

    def test_runtime_profile_rejects_inline_credentials(self):
        instrument = InstrumentId.from_str("KASUSDT-PERP.BINANCE")
        runtime = {
            "clients": {
                "BINANCE-INLINE": {
                    "venue": "BINANCE",
                    "credentials": {"api_key": "should-not-be-here"},
                },
            },
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ValueError):
                build_runtime_profile(
                    runtime,
                    config_dir=pathlib.Path(tmpdir),
                    default_instrument=instrument,
                )


if __name__ == "__main__":
    unittest.main()
