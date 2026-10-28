"""Pure command bounds, testable in CPU CI without importing ROS."""

import math


def command_allowed(values):
    return (
        len(values) == 6
        and all(math.isfinite(v) for v in values)
        and abs(values[0]) <= 0.220001
        and abs(values[5]) <= 0.800001
        and all(abs(v) <= 1e-9 for v in values[1:5])
    )
