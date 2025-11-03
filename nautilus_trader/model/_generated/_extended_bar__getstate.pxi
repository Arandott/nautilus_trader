    def __getstate__(self):
        bar_type = BarType.from_mem_c(self._mem.bar_type)
        bart_type_state = bar_type.__getstate__()

        cdef tuple base = (
            self._mem.open.raw,
            self._mem.high.raw,
            self._mem.low.raw,
            self._mem.close.raw,
            self._mem.close.precision,
            self._mem.volume.raw,
            self._mem.volume.precision,
            self.ts_event,
            self.ts_init,
        )

        cdef tuple extra = (
            self._mem.amt.raw,
            self._mem.amt.precision,
        )

        return bart_type_state + base + extra
