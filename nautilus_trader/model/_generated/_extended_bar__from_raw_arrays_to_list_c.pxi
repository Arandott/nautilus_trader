    @staticmethod
    cdef list[Bar] from_raw_arrays_to_list_c(
        BarType bar_type,
        uint8_t price_prec,
        uint8_t size_prec,
        double[:] opens,
        double[:] highs,
        double[:] lows,
        double[:] closes,
        double[:] volumes,
        uint64_t[:] ts_events,
        uint64_t[:] ts_inits,
    ):
        Condition.is_true(
            len(opens) == len(highs) == len(lows) == len(lows) ==
            len(closes) == len(volumes) == len(ts_events) == len(ts_inits) ==
            len(amts),
            "Array lengths must be equal",
        )

        cdef int count = ts_events.shape[0]
        cdef list[Bar] bars = []

        cdef:
            int i
            Price open_price
            Price high_price
            Price low_price
            Price close_price
            Quantity volume_qty
            Bar bar
            Quantity_t _ext_amt_default

        _ext_amt_default = Quantity.from_str_c('0')._mem
        _ext_amt_default.precision = size_prec

        for i in range(count):
            open_price = Price(opens[i], price_prec)
            high_price = Price(highs[i], price_prec)
            low_price = Price(lows[i], price_prec)
            close_price = Price(closes[i], price_prec)
            volume_qty = Quantity(volumes[i], size_prec)
            bar = Bar.__new__(Bar)
            bar._mem = bar_new(
                bar_type._mem,
                open_price._mem,
                high_price._mem,
                low_price._mem,
                close_price._mem,
                volume_qty._mem,
                ts_events[i],
                ts_inits[i],
                _ext_amt_default,
            )
            bars.append(bar)

        return bars
