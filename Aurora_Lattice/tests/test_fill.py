import unittest

from nautilus_trader.model.enums import OrderSide

from aurora_hdg.fill import HittingQueueFillModel, QueueStats


class FillModelTests(unittest.TestCase):
    def test_fill_probability_increases_with_smaller_distance(self):
        stats = QueueStats(lambda_mo=5.0, lambda_cancel=2.0, mean_mo=1.0, var_mo=1.0)
        model = HittingQueueFillModel(min_p=0.01)
        near = model.p_fill(
            side=OrderSide.BUY,
            distance=0.5,
            mu=0.0,
            sigma_px=2.0,
            horizon_s=0.3,
            queue_ahead=1.0,
            stats=stats,
        )
        far = model.p_fill(
            side=OrderSide.BUY,
            distance=2.0,
            mu=0.0,
            sigma_px=2.0,
            horizon_s=0.3,
            queue_ahead=1.0,
            stats=stats,
        )
        self.assertGreater(near, far)


if __name__ == "__main__":
    unittest.main()
