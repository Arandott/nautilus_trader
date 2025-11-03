cdef class Bar(Data):
    """
    Represents an aggregated bar.

    Parameters
    ----------
    bar_type : BarType
        The bar type for this bar.
    open : Price
        The bars open price.
    high : Price
        The bars high price.
    low : Price
        The bars low price.
    close : Price
        The bars close price.
    volume : Quantity
        The bars volume.
    ts_event : uint64_t
        UNIX timestamp (nanoseconds) when the data event occurred.
    ts_init : uint64_t
        UNIX timestamp (nanoseconds) when the data object was initialized.
    is_revision : bool, default False
        If this bar is a revision of a previous bar with the same `ts_event`.

    Raises
    ------
    ValueError
        If `high` is not >= `low`.
    ValueError
        If `high` is not >= `close`.
    ValueError
        If `low` is not <= `close`.

    """

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

    def __getstate__(self):
        bar_type = BarType.from_mem_c(self._mem.bar_type)
        bart_type_state = bar_type.__getstate__()

        return bart_type_state + (
            self._mem.open.raw,
            self._mem.high.raw,
            self._mem.low.raw,
            self._mem.close.raw,
            self._mem.close.precision,
            self._mem.volume.raw,
            self._mem.volume.precision,
            self.ts_event,
            self.ts_init,
            self._mem.amt.raw,
            self._mem.amt.precision,
        )

    def __setstate__(self, state):
        cdef InstrumentId instrument_id
        cdef uint8_t price_prec
        cdef uint8_t size_prec
        cdef Quantity_t _ext_amt
        cdef Py_ssize_t expected_standard_len = 16
        cdef Py_ssize_t expected_composite_len = 19
        cdef int idx  # Index for iterating through extended fields

        if len(state) == 14 or len(state) == expected_standard_len:
            instrument_id = InstrumentId.from_str_c(state[0])
            price_prec = state[9]
            size_prec = state[11]
            # Restore extended fields from state or use defaults
            if len(state) == expected_standard_len:
                # Extended state format - restore fields
                idx = 14
                _ext_amt = quantity_new(state[idx], state[idx + 1])
                idx += 2
            else:
                # Legacy state format - use defaults
                _ext_amt = Quantity.from_str_c('0')._mem

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
        else:
            instrument_id = InstrumentId.from_str_c(state[0])
            price_prec = state[12]
            size_prec = state[14]
            # Restore extended fields from state or use defaults
            if len(state) == expected_composite_len:
                # Extended state format - restore fields
                idx = 17
                _ext_amt = quantity_new(state[idx], state[idx + 1])
                idx += 2
            else:
                # Legacy state format - use defaults
                _ext_amt = Quantity.from_str_c('0')._mem

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

    def __eq__(self, Bar other) -> bool:
        return self.to_str() == other.to_str()

    def __hash__(self) -> int:
        return hash(self.to_str())

    cdef str to_str(self):
        return cstr_to_pystr(bar_to_cstr(&self._mem))

    def __str__(self) -> str:
        return self.to_str()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self})"

    @property
    def bar_type(self) -> BarType:
        """
        Return the bar type of bar.

        Returns
        -------
        BarType

        """
        return BarType.from_mem_c(self._mem.bar_type)

    @property
    def open(self) -> Price:
        """
        Return the open price of the bar.

        Returns
        -------
        Price

        """
        return Price.from_raw_c(self._mem.open.raw, self._mem.open.precision)

    @property
    def high(self) -> Price:
        """
        Return the high price of the bar.

        Returns
        -------
        Price

        """
        return Price.from_raw_c(self._mem.high.raw, self._mem.high.precision)

    @property
    def low(self) -> Price:
        """
        Return the low price of the bar.

        Returns
        -------
        Price

        """
        return Price.from_raw_c(self._mem.low.raw, self._mem.low.precision)

    @property
    def close(self) -> Price:
        """
        Return the close price of the bar.

        Returns
        -------
        Price

        """
        return Price.from_raw_c(self._mem.close.raw, self._mem.close.precision)

    @property
    def volume(self) -> Quantity:
        """
        Return the volume of the bar.

        Returns
        -------
        Quantity

        """
        return Quantity.from_raw_c(self._mem.volume.raw, self._mem.volume.precision)

    @property
    def ts_event(self) -> int:
        """
        UNIX timestamp (nanoseconds) when the data event occurred.

        Returns
        -------
        int

        """
        return self._mem.ts_event

    @property
    def ts_init(self) -> int:
        """
        UNIX timestamp (nanoseconds) when the object was initialized.

        Returns
        -------
        int

        """
        return self._mem.ts_init

    @staticmethod
    cdef Bar from_mem_c(Bar_t mem):
        return bar_from_mem_c(mem)

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
        uint8_t amt_prec,
    ):
        cdef Price_t open_price = price_new(open, price_prec)
        cdef Price_t high_price = price_new(high, price_prec)
        cdef Price_t low_price = price_new(low, price_prec)
        cdef Price_t close_price = price_new(close, price_prec)
        cdef Quantity_t volume_qty = quantity_new(volume, size_prec)
        cdef Bar bar = Bar.__new__(Bar)
        cdef Quantity_t amt_qty = quantity_new(amt_raw, amt_prec)
        bar._mem = bar_new(
            bar_type._mem,
            open_price,
            high_price,
            low_price,
            close_price,
            volume_qty,
            ts_event,
            ts_init,
            amt_qty,
        )

        return bar

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
        double[:] amts,
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
            Quantity amt_qty
        for i in range(count):
            open_price = Price(opens[i], price_prec)
            high_price = Price(highs[i], price_prec)
            low_price = Price(lows[i], price_prec)
            close_price = Price(closes[i], price_prec)
            volume_qty = Quantity(volumes[i], size_prec)
            bar = Bar.__new__(Bar)
            amt_qty = Quantity(amts[i], size_prec)
            bar._mem = bar_new(
                bar_type._mem,
                open_price._mem,
                high_price._mem,
                low_price._mem,
                close_price._mem,
                volume_qty._mem,
                ts_events[i],
                ts_inits[i],
                amt_qty._mem,
            )
            bars.append(bar)

        return bars

    @staticmethod
    def from_raw_arrays_to_list(
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
        double[:] amts,
    ) -> list[Bar]:
        return Bar.from_raw_arrays_to_list_c(
            bar_type,
            price_prec,
            size_prec,
            opens,
            highs,
            lows,
            closes,
            volumes,
            ts_events,
            ts_inits,
            amts,
        )

    @staticmethod
    cdef Bar from_dict_c(dict values):
        Condition.not_none(values, "values")
        return Bar(
            bar_type=BarType.from_str_c(values["bar_type"]),
            open=Price.from_str_c(values["open"]),
            high=Price.from_str_c(values["high"]),
            low=Price.from_str_c(values["low"]),
            close=Price.from_str_c(values["close"]),
            volume=Quantity.from_str_c(values["volume"]),
            ts_event=values["ts_event"],
            ts_init=values["ts_init"],
                amt=Quantity.from_str_c(values.get("amt", "0")) if "amt" in values else None,
        )

    @staticmethod
    cdef dict to_dict_c(Bar obj):
        Condition.not_none(obj, "obj")
        return {
            "type": type(obj).__name__,
            "bar_type": str(obj.bar_type),
            "open": str(obj.open),
            "high": str(obj.high),
            "low": str(obj.low),
            "close": str(obj.close),
            "volume": str(obj.volume),
            "ts_event": obj._mem.ts_event,
            "ts_init": obj._mem.ts_init,
                "amt": str(obj.amt),
        }

    @staticmethod
    cdef Bar from_pyo3_c(pyo3_bar):
        # SAFETY: Do NOT deallocate the capsule here
        # It is supposed to be deallocated by the creator
        capsule = pyo3_bar.as_pycapsule()
        cdef Data_t* ptr = <Data_t*>PyCapsule_GetPointer(capsule, NULL)
        return bar_from_mem_c(ptr.bar)

    @staticmethod
    def from_raw(
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
        uint8_t amt_prec,
    ) -> Bar:
        return Bar.from_raw_c(
            bar_type,
            open,
            high,
            low,
            close,
            price_prec,
            volume,
            size_prec,
            ts_event,
            ts_init,
            amt_raw,
            amt_prec,
        )

    @staticmethod
    def from_dict(dict values) -> Bar:
        """
        Return a bar parsed from the given values.

        Parameters
        ----------
        values : dict[str, object]
            The values for initialization.

        Returns
        -------
        Bar

        """
        return Bar.from_dict_c(values)

    @staticmethod
    def to_dict(Bar obj):
        """
        Return a dictionary representation of this object.

        Returns
        -------
        dict[str, object]

        """
        return Bar.to_dict_c(obj)

    @staticmethod
    def to_pyo3_list(list bars) -> list[nautilus_pyo3.Bar]:
        """
        Return pyo3 Rust bars converted from the given legacy Cython objects.

        Parameters
        ----------
        bars : list[Bar]
            The legacy Cython bars to convert from.

        Returns
        -------
        list[nautilus_pyo3.Bar]

        """
        cdef list output = []

        pyo3_bar_type = None
        cdef uint8_t price_prec = 0
        cdef uint8_t volume_prec = 0

        cdef:
            Bar bar
            BarType bar_type
        for bar in bars:
            if pyo3_bar_type is None:
                bar_type = bar.bar_type
                pyo3_bar_type = nautilus_pyo3.BarType.from_str(bar_type.to_str())
                price_prec = bar._mem.open.precision
                volume_prec = bar._mem.volume.precision

            pyo3_bar = nautilus_pyo3.Bar(
                pyo3_bar_type,
                nautilus_pyo3.Price.from_raw(bar._mem.open.raw, price_prec),
                nautilus_pyo3.Price.from_raw(bar._mem.high.raw, price_prec),
                nautilus_pyo3.Price.from_raw(bar._mem.low.raw, price_prec),
                nautilus_pyo3.Price.from_raw(bar._mem.close.raw, price_prec),
                nautilus_pyo3.Quantity.from_raw(bar._mem.volume.raw, volume_prec),
                bar._mem.ts_event,
                bar._mem.ts_init,
                amt=nautilus_pyo3.Quantity.from_raw(bar._mem.amt.raw, bar._mem.amt.precision),
            )
            output.append(pyo3_bar)

        return output

    @staticmethod
    def from_pyo3_list(list pyo3_bars) -> list[Bar]:
        """
        Return legacy Cython bars converted from the given pyo3 Rust objects.

        Parameters
        ----------
        pyo3_bars : list[nautilus_pyo3.Bar]
            The pyo3 Rust bars to convert from.

        Returns
        -------
        list[Bar]

        """
        cdef list[Bar] output = []

        for pyo3_bar in pyo3_bars:
            output.append(Bar.from_pyo3_c(pyo3_bar))

        return output

    @staticmethod
    def from_pyo3(pyo3_bar) -> Bar:
        """
        Return a legacy Cython bar converted from the given pyo3 Rust object.

        Parameters
        ----------
        pyo3_bar : nautilus_pyo3.Bar
            The pyo3 Rust bar to convert from.

        Returns
        -------
        Bar

        """
        return Bar.from_pyo3_c(pyo3_bar)

    def to_pyo3(self) -> nautilus_pyo3.Bar:
        """
        Return a pyo3 object from this legacy Cython instance.

        Returns
        -------
        nautilus_pyo3.Bar

        """
        return nautilus_pyo3.Bar(
            nautilus_pyo3.BarType.from_str(BarType.from_mem_c(self._mem.bar_type).to_str()),
            nautilus_pyo3.Price.from_raw(self._mem.open.raw, self._mem.open.precision),
            nautilus_pyo3.Price.from_raw(self._mem.high.raw, self._mem.high.precision),
            nautilus_pyo3.Price.from_raw(self._mem.low.raw, self._mem.low.precision),
            nautilus_pyo3.Price.from_raw(self._mem.close.raw, self._mem.close.precision),
            nautilus_pyo3.Quantity.from_raw(self._mem.volume.raw, self._mem.volume.precision),
            self._mem.ts_event,
            self._mem.ts_init,
                amt=nautilus_pyo3.Quantity.from_raw(self._mem.amt.raw, self._mem.amt.precision),
        )

    cpdef bint is_single_price(self):
        """
        If the OHLC are all equal to a single price.

        Returns
        -------
        bool

        """
        return self._mem.open.raw == self._mem.high.raw == self._mem.low.raw == self._mem.close.raw


    @property
    def amt(self):
        """
        Total traded notional
        """
        return Quantity.from_raw_c(self._mem.amt.raw, self._mem.amt.precision)

    @amt.setter
    def amt(self, value) -> None:
        self._mem.amt = (<Quantity>value)._mem
