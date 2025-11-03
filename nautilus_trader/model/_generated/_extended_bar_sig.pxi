# Auto-generated extended Bar class signature
# DO NOT EDIT MANUALLY

cdef class Bar(Data):
    cdef Bar_t _mem

    cdef readonly bint is_revision
    """If this bar is a revision for a previous bar with the same `ts_event`.\n\n:returns: `bool`"""

    cdef str to_str(self)

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
        QuantityRaw amt_raw,
        uint8_t amt_prec
    )

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
        double[:] amts
    )

    @staticmethod
    cdef Bar from_mem_c(Bar_t mem)

    @staticmethod
    cdef Bar from_pyo3_c(pyo3_bar)

    @staticmethod
    cdef Bar from_dict_c(dict values)

    @staticmethod
    cdef dict to_dict_c(Bar obj)

    cpdef bint is_single_price(self)
