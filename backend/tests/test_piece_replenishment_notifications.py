from controllers.parts import _is_stock_replenishment, _optional_int


def test_stock_increase_from_zero_triggers_availability_notification():
    assert _is_stock_replenishment(0, 1) is True


def test_stock_increase_from_positive_value_also_triggers_notification():
    assert _is_stock_replenishment(2, 5) is True


def test_unchanged_or_decreased_stock_does_not_trigger_notification():
    assert _is_stock_replenishment(3, 3) is False
    assert _is_stock_replenishment(3, 1) is False


def test_nullable_technician_id_conversion():
    assert _optional_int(12.0) == 12
    assert _optional_int(float("nan")) is None
    assert _optional_int(None) is None
