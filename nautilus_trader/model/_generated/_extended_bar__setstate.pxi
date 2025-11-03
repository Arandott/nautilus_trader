    def __setstate__(self, state):
        cdef InstrumentId instrument_id
        cdef uint8_t price_prec
        cdef uint8_t size_prec
        cdef Py_ssize_t expected_standard_len = 16
        cdef Py_ssize_t expected_composite_len = 19

        if len(state) == 14 or len(state) == expected_standard_len:
            instrument_id = InstrumentId.from_str_c(state[0])
            price_prec = state[9]
            size_prec = state[11]
            cdef Py_ssize_t idx = 14
            cdef Quantity_t _ext_amt
            if len(state) == expected_standard_len:
                _ext_amt = quantity_new(state[idx], state[idx + 1])
                idx += 2
            else:
                cdef Quantity _default_amt = Quantity.from_str_c('0')
                _ext_amt = _default_amt._mem
                _ext_amt.precision = size_prec
            self._mem = bar_new(
                bar_type_new(
                    instrument_id._mem,
                    bar_specification_new(
                        state[1],
                        state[2],
                        state[3],
                    ),
                    state[4],
                ),
                price_new(state[5], price_prec),
                price_new(state[6], price_prec),
                price_new(state[7], price_prec),
                price_new(state[8], price_prec),
                quantity_new(state[10], size_prec),
                state[12],
                state[13],
                _ext_amt,
            )
        elif len(state) == 17 or len(state) == expected_composite_len:
            instrument_id = InstrumentId.from_str_c(state[0])
            price_prec = state[12]
            size_prec = state[14]
            cdef Py_ssize_t idx = 17
            cdef Quantity_t _ext_amt
            if len(state) == expected_composite_len:
                _ext_amt = quantity_new(state[idx], state[idx + 1])
                idx += 2
            else:
                cdef Quantity _default_amt = Quantity.from_str_c('0')
                _ext_amt = _default_amt._mem
                _ext_amt.precision = size_prec
            self._mem = bar_new(
                bar_type_new_composite(
                    instrument_id._mem,
                    bar_specification_new(
                        state[1],
                        state[2],
                        state[3]
                    ),
                    state[4],

                    state[5],
                    state[6],
                    state[7]
                ),
                price_new(state[8], price_prec),
                price_new(state[9], price_prec),
                price_new(state[10], price_prec),
                price_new(state[11], price_prec),
                quantity_new(state[13], size_prec),
                state[15],
                state[16],
                _ext_amt,
            )
        else:
            raise ValueError("Invalid state length for Bar")
