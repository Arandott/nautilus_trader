    @property
    def amt(self) -> Quantity:
        return Quantity.from_raw_c(self._mem.amt.raw, self._mem.amt.precision)

    @amt.setter
    def amt(self, Quantity value not None) -> None:
        self._mem.amt = value._mem

