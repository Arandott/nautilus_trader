    @staticmethod
    cdef Bar from_raw_c(
        BarType bar_type,
        PriceRaw open,
        PriceRaw high,
        PriceRaw low,
        PriceRaw close,
        uint8_t price_prec,
        QuantityRaw volume,
        uint8_t size_prec,
        uint64_t ts_event,
        uint64_t ts_init,
    ):
        cdef Price_t open_price = price_new(open, price_prec)
        cdef Price_t high_price = price_new(high, price_prec)
        cdef Price_t low_price = price_new(low, price_prec)
        cdef Price_t close_price = price_new(close, price_prec)
        cdef Quantity_t volume_qty = quantity_new(volume, size_prec)
        cdef Bar bar = Bar.__new__(Bar)
        cdef Quantity _ext_amt_obj = Quantity.from_str_c('0')
        cdef Quantity_t _ext_amt = _ext_amt_obj._mem
        _ext_amt.precision = size_prec
        bar._mem = bar_new(
            bar_type._mem,
            open_price,
            high_price,
            low_price,
            close_price,
            volume_qty,
            ts_event,
            ts_init,
                _ext_amt,
        )

        return bar
