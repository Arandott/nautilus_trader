    def __init__(
        self,
        BarType bar_type not None,
        Price open not None,
        Price high not None,
        Price low not None,
        Price close not None,
        Quantity volume not None,
        uint64_t ts_event,
        uint64_t ts_init,
        bint is_revision = False,
        *,
        Quantity amt=None,
    ) -> None:
        Condition.is_true(high._mem.raw >= open._mem.raw, "high was < open")
        Condition.is_true(high._mem.raw >= low._mem.raw, "high was < low")
        Condition.is_true(high._mem.raw >= close._mem.raw, "high was < close")
        Condition.is_true(low._mem.raw <= close._mem.raw, "low was > close")
        Condition.is_true(low._mem.raw <= open._mem.raw, "low was > open")
        if amt is None:
            amt = Quantity.from_str('0')
        cdef Quantity_t _ext_amt = amt._mem
        self._mem = bar_new(
            bar_type._mem,
            open._mem,
            high._mem,
            low._mem,
            close._mem,
            volume._mem,
            ts_event,
            ts_init,
            _ext_amt,
        )
        self.is_revision = is_revision
