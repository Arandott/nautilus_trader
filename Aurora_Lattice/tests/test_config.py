import pathlib
import unittest

from aurora_hdg import AuroraHDGConfig, load_config


class ConfigTests(unittest.TestCase):
    def test_load_config_returns_strategy_config(self):
        src = pathlib.Path("Aurora_Lattice/configs/default.yaml")
        cfg = load_config(src)
        self.assertIsInstance(cfg, AuroraHDGConfig)
        self.assertGreater(cfg.grid.levels, 0)
        self.assertGreater(cfg.inventory.i_max, cfg.inventory.i_soft)


if __name__ == "__main__":
    unittest.main()
