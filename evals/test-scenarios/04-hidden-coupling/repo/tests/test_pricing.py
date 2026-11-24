import os

from shop import pricing


def test_round_total():
    os.environ["ROUNDING_MODE"] = "half_up"
    assert str(pricing.round_total("2.665")) == "2.67"
