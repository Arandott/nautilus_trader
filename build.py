#!/usr/bin/env python3

import datetime as dt
import itertools
import os
import platform
import re
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

import numpy as np
from Cython.Build import build_ext
from Cython.Build import cythonize
from Cython.Compiler import Options
from Cython.Compiler.Version import version as cython_compiler_version
from setuptools import Distribution
from setuptools import Extension


try:  # Python ≥3.11
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover - fallback for older interpreters
    try:
        import tomli as tomllib  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:  # pragma: no cover - guidance for users
        raise RuntimeError(
            "Python `tomllib` module is required to parse extended bar configuration. "
            "Install Python 3.11+ or add the `tomli` dependency."
        ) from exc


# Platform constants
IS_LINUX = platform.system() == "Linux"
IS_MACOS = platform.system() == "Darwin"
IS_WINDOWS = platform.system() == "Windows"
IS_ARM64 = platform.machine() in ("arm64", "aarch64")


# The Rust toolchain to use for builds
RUSTUP_TOOLCHAIN = os.getenv("RUSTUP_TOOLCHAIN", "stable")
# The Cargo build mode
BUILD_MODE = os.getenv("BUILD_MODE", "release")
# If PROFILE_MODE mode is enabled, include traces necessary for coverage and profiling
PROFILE_MODE = bool(os.getenv("PROFILE_MODE", ""))
# If ANNOTATION mode is enabled, generate an annotated HTML version of the input source files
ANNOTATION_MODE = bool(os.getenv("ANNOTATION_MODE", ""))
# If PARALLEL build is enabled, uses all CPUs for compile stage of build
PARALLEL_BUILD = os.getenv("PARALLEL_BUILD", "true").lower() == "true"
# If COPY_TO_SOURCE is enabled, copy built *.so files back into the source tree
COPY_TO_SOURCE = os.getenv("COPY_TO_SOURCE", "true").lower() == "true"
# If PyO3 only then don't build C extensions to reduce compilation time
PYO3_ONLY = os.getenv("PYO3_ONLY", "").lower() != ""
# If dry run only print the commands that would be executed
DRY_RUN = bool(os.getenv("DRY_RUN", ""))

# Precision mode configuration
# https://nautilustrader.io/docs/nightly/getting_started/installation#precision-mode
HIGH_PRECISION = os.getenv("HIGH_PRECISION", "true").lower() == "true"
if IS_WINDOWS and HIGH_PRECISION:
    print(
        "Warning: high-precision mode not supported on Windows (128-bit integers unavailable)\n"
        "Forcing standard-precision (64-bit) mode",
    )
    HIGH_PRECISION = False

if PROFILE_MODE:
    # For subsequent debugging, the C source needs to be in the same tree as
    # the Cython code (not in a separate build directory).
    BUILD_DIR = None
elif ANNOTATION_MODE:
    BUILD_DIR = "build/annotated"
else:
    BUILD_DIR = "build/optimized"

################################################################################
#  RUST BUILD
################################################################################

USE_SCCACHE = "sccache" in os.environ.get("CC", "") or "sccache" in os.environ.get("CXX", "")

if IS_LINUX:
    # Use clang as the default compiler
    os.environ["CC"] = "sccache clang" if USE_SCCACHE else "clang"
    os.environ["CXX"] = "sccache clang++" if USE_SCCACHE else "clang++"
    os.environ["LDSHARED"] = "clang -shared"

if IS_MACOS and IS_ARM64:
    os.environ["CFLAGS"] = f"{os.environ.get('CFLAGS', '')} -arch arm64"
    os.environ["LDFLAGS"] = f"{os.environ.get('LDFLAGS', '')} -arch arm64 -w"

if IS_LINUX and IS_ARM64:
    os.environ["CFLAGS"] = f"{os.environ.get('CFLAGS', '')} -fPIC"
    os.environ["LDFLAGS"] = f"{os.environ.get('LDFLAGS', '')} -fPIC"

    python_lib_dir = os.environ.get("PYTHON_LIB_DIR")
    python_version = ".".join(platform.python_version_tuple()[:2])  # e.g. "3.12"

    if python_lib_dir:
        print(f"Setting RUSTFLAGS to link with Python {python_version} in {python_lib_dir}")
        rustflags = f"{os.environ.get('RUSTFLAGS', '')} -C link-arg=-L{python_lib_dir} -C link-arg=-lpython{python_version}"
        os.environ["RUSTFLAGS"] = rustflags

if IS_WINDOWS:
    # Linker error 1181
    # https://docs.microsoft.com/en-US/cpp/error-messages/tool-errors/linker-tools-error-lnk1181?view=msvc-170&viewFallbackFrom=vs-2019
    RUST_LIB_PFX = ""
    RUST_STATIC_LIB_EXT = "lib"
    RUST_DYLIB_EXT = "dll"
elif IS_MACOS:
    RUST_LIB_PFX = "lib"
    RUST_STATIC_LIB_EXT = "a"
    RUST_DYLIB_EXT = "dylib"
else:  # Linux
    RUST_LIB_PFX = "lib"
    RUST_STATIC_LIB_EXT = "a"
    RUST_DYLIB_EXT = "so"

CARGO_TARGET_DIR = os.environ.get("CARGO_TARGET_DIR", Path.cwd() / "target")
CARGO_BUILD_TARGET = os.environ.get("CARGO_BUILD_TARGET", "")
CARGO_TARGET_DIR = Path(CARGO_TARGET_DIR) / CARGO_BUILD_TARGET / BUILD_MODE

# Directories with headers to include
RUST_INCLUDES = ["nautilus_trader/core/includes"]
RUST_LIB_PATHS: list[Path] = [
    CARGO_TARGET_DIR / f"{RUST_LIB_PFX}nautilus_backtest.{RUST_STATIC_LIB_EXT}",
    CARGO_TARGET_DIR / f"{RUST_LIB_PFX}nautilus_common.{RUST_STATIC_LIB_EXT}",
    CARGO_TARGET_DIR / f"{RUST_LIB_PFX}nautilus_core.{RUST_STATIC_LIB_EXT}",
    CARGO_TARGET_DIR / f"{RUST_LIB_PFX}nautilus_model.{RUST_STATIC_LIB_EXT}",
    CARGO_TARGET_DIR / f"{RUST_LIB_PFX}nautilus_persistence.{RUST_STATIC_LIB_EXT}",
]
RUST_LIBS: list[str] = [str(path) for path in RUST_LIB_PATHS]

EXTENDED_BAR_CONFIG_PATH = Path("configs/extended_bar_fields.toml")
GENERATED_CYTHON_DIR = Path("nautilus_trader/model/_generated")


def _load_extended_bar_fields() -> list[dict[str, object]]:
    if not EXTENDED_BAR_CONFIG_PATH.exists():
        return []

    with EXTENDED_BAR_CONFIG_PATH.open("rb") as config_file:
        data = tomllib.load(config_file)

    fields = data.get("field", [])
    if not isinstance(fields, list):
        raise ValueError(
            "`field` array missing from configs/extended_bar_fields.toml",
        )

    normalized: list[dict[str, object]] = []
    for entry in fields:
        if not isinstance(entry, dict):
            raise ValueError("Each [field] entry must be a table in extended_bar_fields.toml")
        normalized.append(entry)

    return normalized


def _format_bool_default(value: str | None) -> str:
    if value is None:
        return "False"
    lowered = value.lower()
    if lowered in {"true", "1", "yes"}:
        return "True"
    if lowered in {"false", "0", "no"}:
        return "False"
    raise ValueError(f"Unsupported boolean default '{value}' in extended bar configuration")


def _generate_extended_bar_cython_files() -> None:
    fields = _load_extended_bar_fields()

    GENERATED_CYTHON_DIR.mkdir(parents=True, exist_ok=True)

    obsolete = [
        "_extended_bar__init__params.pxi",
        "_extended_bar__init__body.pxi",
        "_extended_bar__init__bar_new_args.pxi",
    ]
    for filename in obsolete:
        try:
            (GENERATED_CYTHON_DIR / filename).unlink()
        except FileNotFoundError:
            pass

    def write_fragment(name: str, content: str) -> None:
        (GENERATED_CYTHON_DIR / name).write_text(content, encoding="utf-8")

    write_fragment("extended_bar_field_specs.pxd", "# @generated\ncdef object EXTENDED_BAR_FIELD_SPECS\n")

    if not fields:
        write_fragment("extended_bar_config.pxi", "DEF HAS_EXTENDED_BAR_FIELDS = 0\n")
        write_fragment("_extended_bar__init__.pxi", "")
        write_fragment("_extended_bar__properties.pxi", "")
        write_fragment("extended_bar_field_specs.pxi", "EXTENDED_BAR_FIELD_SPECS = ()\n")
        write_fragment("_extended_bar__getstate.pxi", "")
        write_fragment("_extended_bar__setstate.pxi", "")
        write_fragment("_extended_bar__from_raw_c.pxi", "")
        write_fragment("_extended_bar__from_raw_arrays_to_list_c.pxi", "")
        # Ensure full-class includes are present (empty stubs so module-level guards still work)
        write_fragment("_extended_bar__bar.pxi", "# @generated (empty - no extended fields)\n")
        # Standard variant will be (re)generated below from the source file
        _generate_full_bar_variants()
        return

    write_fragment("extended_bar_config.pxi", "DEF HAS_EXTENDED_BAR_FIELDS = 1\n")

    property_blocks: list[str] = []
    field_specs_entries: list[str] = []
    processed_fields: list[dict[str, object]] = []

    signature_lines = [
        "    def __init__(",
        "        self,",
        "        BarType bar_type not None,",
        "        Price open not None,",
        "        Price high not None,",
        "        Price low not None,",
        "        Price close not None,",
        "        Quantity volume not None,",
        "        uint64_t ts_event,",
        "        uint64_t ts_init,",
        "        bint is_revision = False,",
        "        *,",
    ]

    init_body_lines = [
        '        Condition.is_true(high._mem.raw >= open._mem.raw, "high was < open")',
        '        Condition.is_true(high._mem.raw >= low._mem.raw, "high was < low")',
        '        Condition.is_true(high._mem.raw >= close._mem.raw, "high was < close")',
        '        Condition.is_true(low._mem.raw <= close._mem.raw, "low was > close")',
        '        Condition.is_true(low._mem.raw <= open._mem.raw, "low was > open")',
    ]

    bar_new_lines = [
        "        self._mem = bar_new(",
        "            bar_type._mem,",
        "            open._mem,",
        "            high._mem,",
        "            low._mem,",
        "            close._mem,",
        "            volume._mem,",
        "            ts_event,",
        "            ts_init,",
    ]

    for field in fields:
        ident = str(field.get("ident"))
        field_type = str(field.get("type"))
        default_literal = field.get("default")
        precision = field.get("precision")
        doc = field.get("doc", "")

        string_default = default_literal if isinstance(default_literal, str) else None

        if field_type == "quantity":
            signature_lines.append(f"        Quantity {ident}=None,")
            default_expr = f"Quantity.from_str({string_default or '0'!r})"
            init_body_lines.append(f"        if {ident} is None:")
            init_body_lines.append(f"            {ident} = {default_expr}")
            init_body_lines.append(f"        cdef Quantity_t _ext_{ident} = {ident}._mem")
            bar_new_lines.append(f"            _ext_{ident},")
            property_blocks.append(
                f"    @property\n"
                f"    def {ident}(self) -> Quantity:\n"
                f"        return Quantity.from_raw_c(self._mem.{ident}.raw, self._mem.{ident}.precision)\n\n"
                f"    @{ident}.setter\n"
                f"    def {ident}(self, Quantity value not None) -> None:\n"
                f"        self._mem.{ident} = value._mem\n"
            )
            processed_fields.append(
                {
                    "ident": ident,
                    "type": field_type,
                    "default_str": string_default or "0",
                    "precision": precision,
                }
            )
        elif field_type == "price":
            signature_lines.append(f"        Price {ident}=None,")
            default_expr = f"Price.from_str({string_default or '0'!r})"
            init_body_lines.append(f"        if {ident} is None:")
            init_body_lines.append(f"            {ident} = {default_expr}")
            init_body_lines.append(f"        cdef Price_t _ext_{ident} = {ident}._mem")
            bar_new_lines.append(f"            _ext_{ident},")
            property_blocks.append(
                f"    @property\n"
                f"    def {ident}(self) -> Price:\n"
                f"        return Price.from_raw_c(self._mem.{ident}.raw, self._mem.{ident}.precision)\n\n"
                f"    @{ident}.setter\n"
                f"    def {ident}(self, Price value not None) -> None:\n"
                f"        self._mem.{ident} = value._mem\n"
            )
            processed_fields.append(
                {
                    "ident": ident,
                    "type": field_type,
                    "default_str": string_default or "0",
                    "precision": precision,
                }
            )
        elif field_type == "u64":
            sanitized = (string_default or "0").replace("_", "").strip()
            default_int = int(sanitized or "0", 10)
            signature_lines.append(f"        uint64_t {ident}={default_int},")
            init_body_lines.append(f"        cdef uint64_t _ext_{ident} = {ident}")
            bar_new_lines.append(f"            _ext_{ident},")
            property_blocks.append(
                f"    @property\n"
                f"    def {ident}(self) -> int:\n"
                f"        return self._mem.{ident}\n\n"
                f"    @{ident}.setter\n"
                f"    def {ident}(self, uint64_t value) -> None:\n"
                f"        self._mem.{ident} = value\n"
            )
            processed_fields.append(
                {
                    "ident": ident,
                    "type": field_type,
                    "default_int": default_int,
                    "precision": precision,
                }
            )
        elif field_type == "bool":
            default_bool = _format_bool_default(string_default)
            signature_lines.append(f"        bint {ident}={default_bool},")
            init_body_lines.append(f"        cdef bint _ext_{ident} = {ident}")
            bar_new_lines.append(f"            _ext_{ident},")
            property_blocks.append(
                f"    @property\n"
                f"    def {ident}(self) -> bool:\n"
                f"        return bool(self._mem.{ident})\n\n"
                f"    @{ident}.setter\n"
                f"    def {ident}(self, bint value) -> None:\n"
                f"        self._mem.{ident} = value\n"
            )
            processed_fields.append(
                {
                    "ident": ident,
                    "type": field_type,
                    "default_bool": default_bool,
                    "precision": precision,
                }
            )
        else:
            raise ValueError(f"Unsupported extended bar field type '{field_type}'")

        field_specs_entries.append(
            "    {" + ", ".join(
                [
                    f'"name": {ident!r}',
                    f'"type": {field_type!r}',
                    f"\"default\": {string_default or ''!r}",
                    f"\"precision\": {repr(precision) if precision is not None else 'None'}",
                    f"\"doc\": {doc if isinstance(doc, str) else ''!r}",
                ]
            ) + "},"
        )

    signature_lines.append("    ) -> None:")

    init_body_lines.extend(bar_new_lines)
    init_body_lines.append("        )")
    init_body_lines.append("        self.is_revision = is_revision")

    init_content = "\n".join(signature_lines + init_body_lines) + "\n"
    properties_content = "\n".join(property_blocks) + ("\n" if property_blocks else "")

    specs_content = "EXTENDED_BAR_FIELD_SPECS = (\n" + "\n".join(field_specs_entries) + "\n)\n"

    write_fragment("_extended_bar__init__.pxi", init_content)
    write_fragment("_extended_bar__properties.pxi", properties_content)
    write_fragment("extended_bar_field_specs.pxi", specs_content)

    extra_slots = 0
    for spec in processed_fields:
        if spec["type"] in ("quantity", "price"):
            extra_slots += 2
        else:
            extra_slots += 1

    expected_standard_len = 14 + extra_slots
    expected_composite_len = 17 + extra_slots

    def _precision_adjustment_lines(var_name: str, precision: object, indent: str) -> list[str]:
        lines: list[str] = []
        if precision == "size":
            lines.append(f"{indent}{var_name}.precision = size_prec")
        elif precision == "price":
            lines.append(f"{indent}{var_name}.precision = price_prec")
        return lines

    base_state_lines = [
        "            self._mem.open.raw,",
        "            self._mem.high.raw,",
        "            self._mem.low.raw,",
        "            self._mem.close.raw,",
        "            self._mem.close.precision,",
        "            self._mem.volume.raw,",
        "            self._mem.volume.precision,",
        "            self.ts_event,",
        "            self.ts_init,",
    ]

    extra_state_lines: list[str] = []
    bar_new_extra_args: list[str] = []
    for spec in processed_fields:
        ident = spec["ident"]
        field_type = spec["type"]
        var_name = f"_ext_{ident}"
        bar_new_extra_args.append(f"                {var_name},")
        if field_type in ("quantity", "price"):
            extra_state_lines.append(f"            self._mem.{ident}.raw,")
            extra_state_lines.append(f"            self._mem.{ident}.precision,")
        elif field_type == "u64":
            extra_state_lines.append(f"            self._mem.{ident},")
        elif field_type == "bool":
            extra_state_lines.append(f"            bool(self._mem.{ident}),")

    getstate_lines = [
        "    def __getstate__(self):",
        "        bar_type = BarType.from_mem_c(self._mem.bar_type)",
        "        bart_type_state = bar_type.__getstate__()",
        "",
        "        cdef tuple base = (",
        *base_state_lines,
        "        )",
        "",
        "        cdef tuple extra = (",
        *extra_state_lines,
        "        )",
        "",
        "        return bart_type_state + base + extra",
    ]

    def _build_setstate_field_lines(length_var: str, start_index: int) -> list[str]:
        lines: list[str] = []
        if processed_fields:
            lines.append(f"            cdef Py_ssize_t idx = {start_index}")
        for spec in processed_fields:
            ident = spec["ident"]
            field_type = spec["type"]
            precision = spec.get("precision")
            default_str = spec.get("default_str", "0")
            default_bool = spec.get("default_bool", "False")
            default_int = spec.get("default_int", 0)
            var_name = f"_ext_{ident}"
            if field_type == "quantity":
                lines.append(f"            cdef Quantity_t {var_name}")
                lines.append(f"            if len(state) == {length_var}:")
                lines.append(f"                {var_name} = quantity_new(state[idx], state[idx + 1])")
                lines.append("                idx += 2")
                lines.append("            else:")
                lines.append(f"                cdef Quantity _default_{ident} = Quantity.from_str_c({default_str!r})")
                lines.append(f"                {var_name} = _default_{ident}._mem")
                for adjustment in _precision_adjustment_lines(var_name, precision, "                "):
                    lines.append(adjustment)
            elif field_type == "price":
                lines.append(f"            cdef Price_t {var_name}")
                lines.append(f"            if len(state) == {length_var}:")
                lines.append(f"                {var_name} = price_new(state[idx], state[idx + 1])")
                lines.append("                idx += 2")
                lines.append("            else:")
                lines.append(f"                cdef Price _default_{ident} = Price.from_str_c({default_str!r})")
                lines.append(f"                {var_name} = _default_{ident}._mem")
                for adjustment in _precision_adjustment_lines(var_name, precision, "                "):
                    lines.append(adjustment)
            elif field_type == "u64":
                lines.append(f"            cdef uint64_t {var_name}")
                lines.append(f"            if len(state) == {length_var}:")
                lines.append(f"                {var_name} = <uint64_t> state[idx]")
                lines.append("                idx += 1")
                lines.append("            else:")
                lines.append(f"                {var_name} = {default_int}")
            elif field_type == "bool":
                lines.append(f"            cdef bint {var_name}")
                lines.append(f"            if len(state) == {length_var}:")
                lines.append(f"                {var_name} = <bint> state[idx]")
                lines.append("                idx += 1")
                lines.append("            else:")
                lines.append(f"                {var_name} = {default_bool}")
        return lines

    standard_field_lines = _build_setstate_field_lines("expected_standard_len", 14)
    composite_field_lines = _build_setstate_field_lines("expected_composite_len", 17)

    standard_bar_new_lines = [
        "            self._mem = bar_new(",
        "                bar_type_new(",
        "                    instrument_id._mem,",
        "                    bar_specification_new(",
        "                        state[1],",
        "                        state[2],",
        "                        state[3],",
        "                    ),",
        "                    state[4],",
        "                ),",
        "                price_new(state[5], price_prec),",
        "                price_new(state[6], price_prec),",
        "                price_new(state[7], price_prec),",
        "                price_new(state[8], price_prec),",
        "                quantity_new(state[10], size_prec),",
        "                state[12],",
        "                state[13],",
    ]

    composite_bar_new_lines = [
        "            self._mem = bar_new(",
        "                bar_type_new_composite(",
        "                    instrument_id._mem,",
        "                    bar_specification_new(",
        "                        state[1],",
        "                        state[2],",
        "                        state[3]",
        "                    ),",
        "                    state[4],",
        "",
        "                    state[5],",
        "                    state[6],",
        "                    state[7]",
        "                ),",
        "                price_new(state[8], price_prec),",
        "                price_new(state[9], price_prec),",
        "                price_new(state[10], price_prec),",
        "                price_new(state[11], price_prec),",
        "                quantity_new(state[13], size_prec),",
        "                state[15],",
        "                state[16],",
    ]

    standard_bar_new_lines.extend(bar_new_extra_args)
    standard_bar_new_lines.append("            )")
    composite_bar_new_lines.extend(bar_new_extra_args)
    composite_bar_new_lines.append("            )")

    setstate_lines = [
        "    def __setstate__(self, state):",
        "        cdef InstrumentId instrument_id",
        "        cdef uint8_t price_prec",
        "        cdef uint8_t size_prec",
        f"        cdef Py_ssize_t expected_standard_len = {expected_standard_len}",
        f"        cdef Py_ssize_t expected_composite_len = {expected_composite_len}",
        "",
        "        if len(state) == 14 or len(state) == expected_standard_len:",
        "            instrument_id = InstrumentId.from_str_c(state[0])",
        "            price_prec = state[9]",
        "            size_prec = state[11]",
        *standard_field_lines,
        *standard_bar_new_lines,
        "        elif len(state) == 17 or len(state) == expected_composite_len:",
        "            instrument_id = InstrumentId.from_str_c(state[0])",
        "            price_prec = state[12]",
        "            size_prec = state[14]",
        *composite_field_lines,
        *composite_bar_new_lines,
        "        else:",
        '            raise ValueError("Invalid state length for Bar")',
    ]

    from_raw_c_lines = [
        "    @staticmethod",
        "    cdef Bar from_raw_c(",
        "        BarType bar_type,",
        "        PriceRaw open,",
        "        PriceRaw high,",
        "        PriceRaw low,",
        "        PriceRaw close,",
        "        uint8_t price_prec,",
        "        QuantityRaw volume,",
        "        uint8_t size_prec,",
        "        uint64_t ts_event,",
        "        uint64_t ts_init,",
        "    ):",
        "        cdef Price_t open_price = price_new(open, price_prec)",
        "        cdef Price_t high_price = price_new(high, price_prec)",
        "        cdef Price_t low_price = price_new(low, price_prec)",
        "        cdef Price_t close_price = price_new(close, price_prec)",
        "        cdef Quantity_t volume_qty = quantity_new(volume, size_prec)",
        "        cdef Bar bar = Bar.__new__(Bar)",
    ]

    for spec in processed_fields:
        ident = spec["ident"]
        field_type = spec["type"]
        precision = spec.get("precision")
        default_str = spec.get("default_str", "0")
        default_bool = spec.get("default_bool", "False")
        default_int = spec.get("default_int", 0)
        var_name = f"_ext_{ident}"
        if field_type == "quantity":
            from_raw_c_lines.append(f"        cdef Quantity {var_name}_obj = Quantity.from_str_c({default_str!r})")
            from_raw_c_lines.append(f"        cdef Quantity_t {var_name} = {var_name}_obj._mem")
            from_raw_c_lines.extend(_precision_adjustment_lines(var_name, precision, "        "))
        elif field_type == "price":
            from_raw_c_lines.append(f"        cdef Price {var_name}_obj = Price.from_str_c({default_str!r})")
            from_raw_c_lines.append(f"        cdef Price_t {var_name} = {var_name}_obj._mem")
            from_raw_c_lines.extend(_precision_adjustment_lines(var_name, precision, "        "))
        elif field_type == "u64":
            from_raw_c_lines.append(f"        cdef uint64_t {var_name} = {default_int}")
        elif field_type == "bool":
            from_raw_c_lines.append(f"        cdef bint {var_name} = {default_bool}")

    from_raw_c_lines.extend(
        [
            "        bar._mem = bar_new(",
            "            bar_type._mem,",
            "            open_price,",
            "            high_price,",
            "            low_price,",
            "            close_price,",
            "            volume_qty,",
            "            ts_event,",
            "            ts_init,",
        ]
    )
    from_raw_c_lines.extend(bar_new_extra_args)
    from_raw_c_lines.append("        )")
    from_raw_c_lines.append("")
    from_raw_c_lines.append("        return bar")

    from_raw_arrays_lines = [
        "    @staticmethod",
        "    cdef list[Bar] from_raw_arrays_to_list_c(",
        "        BarType bar_type,",
        "        uint8_t price_prec,",
        "        uint8_t size_prec,",
        "        double[:] opens,",
        "        double[:] highs,",
        "        double[:] lows,",
        "        double[:] closes,",
        "        double[:] volumes,",
        "        uint64_t[:] ts_events,",
        "        uint64_t[:] ts_inits,",
        "    ):",
        "        Condition.is_true(",
        "            len(opens) == len(highs) == len(lows) == len(lows) ==",
        "            len(closes) == len(volumes) == len(ts_events) == len(ts_inits)",
    ]

    # Add extended field array length checks to assertion
    if fields:
        extended_array_names = [f"len({field.get('ident')}s)" for field in fields]
        from_raw_arrays_lines[-1] += " =="
        from_raw_arrays_lines.append("            " + " == ".join(extended_array_names) + ",")
    else:
        from_raw_arrays_lines[-1] += ","

    from_raw_arrays_lines.extend([
        '            "Array lengths must be equal",',
        "        )",
        "",
        "        cdef int count = ts_events.shape[0]",
        "        cdef list[Bar] bars = []",
        "",
        "        cdef:",
        "            int i",
        "            Price open_price",
        "            Price high_price",
        "            Price low_price",
        "            Price close_price",
        "            Quantity volume_qty",
        "            Bar bar",
    ])

    for spec in processed_fields:
        ident = spec["ident"]
        field_type = spec["type"]
        if field_type in ("quantity", "price"):
            from_raw_arrays_lines.append(f"            {spec['type'].capitalize()}_t _ext_{ident}_default")
        elif field_type == "u64":
            from_raw_arrays_lines.append(f"            uint64_t _ext_{ident}_default")
        elif field_type == "bool":
            from_raw_arrays_lines.append(f"            bint _ext_{ident}_default")

    from_raw_arrays_lines.append("")

    for spec in processed_fields:
        ident = spec["ident"]
        field_type = spec["type"]
        precision = spec.get("precision")
        default_str = spec.get("default_str", "0")
        default_bool = spec.get("default_bool", "False")
        default_int = spec.get("default_int", 0)
        var_name = f"_ext_{ident}_default"
        if field_type == "quantity":
            from_raw_arrays_lines.append(f"        {var_name} = Quantity.from_str_c({default_str!r})._mem")
            from_raw_arrays_lines.extend(_precision_adjustment_lines(var_name, precision, "        "))
        elif field_type == "price":
            from_raw_arrays_lines.append(f"        {var_name} = Price.from_str_c({default_str!r})._mem")
            from_raw_arrays_lines.extend(_precision_adjustment_lines(var_name, precision, "        "))
        elif field_type == "u64":
            from_raw_arrays_lines.append(f"        {var_name} = {default_int}")
        elif field_type == "bool":
            from_raw_arrays_lines.append(f"        {var_name} = {default_bool}")

    from_raw_arrays_lines.extend(
        [
            "",
            "        for i in range(count):",
            "            open_price = Price(opens[i], price_prec)",
            "            high_price = Price(highs[i], price_prec)",
            "            low_price = Price(lows[i], price_prec)",
            "            close_price = Price(closes[i], price_prec)",
            "            volume_qty = Quantity(volumes[i], size_prec)",
            "            bar = Bar.__new__(Bar)",
            "            bar._mem = bar_new(",
            "                bar_type._mem,",
            "                open_price._mem,",
            "                high_price._mem,",
            "                low_price._mem,",
            "                close_price._mem,",
            "                volume_qty._mem,",
            "                ts_events[i],",
            "                ts_inits[i],",
        ]
    )
    for spec in processed_fields:
        ident = spec["ident"]
        from_raw_arrays_lines.append(f"                _ext_{ident}_default,")
    from_raw_arrays_lines.extend(
        [
            "            )",
            "            bars.append(bar)",
            "",
            "        return bars",
        ]
    )

    write_fragment("_extended_bar__getstate.pxi", "\n".join(getstate_lines) + "\n")
    write_fragment("_extended_bar__setstate.pxi", "\n".join(setstate_lines) + "\n")
    write_fragment("_extended_bar__from_raw_c.pxi", "\n".join(from_raw_c_lines) + "\n")
    write_fragment(
        "_extended_bar__from_raw_arrays_to_list_c.pxi",
        "\n".join(from_raw_arrays_lines) + "\n",
    )

    # With all partials emitted, synthesize complete class variants
    _generate_full_bar_variants()

    # Generate extended Bar class signature for data.pxd
    _generate_extended_bar_signature(fields)


def _generate_extended_bar_signature(fields: list[dict[str, object]]) -> None:
    """
    Generate _extended_bar_sig.pxi containing Bar class signature with extended fields.

    This file is included by data.pxd in the IF HAS_EXTENDED_BAR_FIELDS branch.
    """
    out = []
    out.append("# Auto-generated extended Bar class signature")
    out.append("# DO NOT EDIT MANUALLY")
    out.append("")
    out.append("cdef class Bar(Data):")
    out.append("    cdef Bar_t _mem")
    out.append("")
    out.append("    cdef readonly bint is_revision")
    out.append('    """If this bar is a revision for a previous bar with the same `ts_event`.\\n\\n:returns: `bool`"""')
    out.append("")
    out.append("    cdef str to_str(self)")
    out.append("")

    # Generate from_raw_c with extended parameters
    out.append("    @staticmethod")
    out.append("    cdef Bar from_raw_c(")
    out.append("        BarType bar_type,")
    out.append("        PriceRaw open,")
    out.append("        PriceRaw high,")
    out.append("        PriceRaw low,")
    out.append("        PriceRaw close,")
    out.append("        uint8_t price_prec,")
    out.append("        QuantityRaw volume,")
    out.append("        uint8_t size_prec,")
    out.append("        uint64_t ts_event,")
    out.append("        uint64_t ts_init,")

    # Add extended field parameters
    for field in fields:
        ident = field.get("ident")
        field_type = field.get("type")
        if field_type == "quantity":
            out.append(f"        QuantityRaw {ident}_raw,")
            out.append(f"        uint8_t {ident}_prec,")
        elif field_type == "price":
            out.append(f"        PriceRaw {ident}_raw,")
            out.append(f"        uint8_t {ident}_prec,")
        elif field_type == "u64":
            out.append(f"        uint64_t {ident},")
        elif field_type == "bool":
            out.append(f"        bint {ident},")

    # Remove trailing comma from last parameter
    if out[-1].endswith(","):
        out[-1] = out[-1][:-1]
    out.append("    )")
    out.append("")

    # Generate from_raw_arrays_to_list_c with extended parameters
    out.append("    @staticmethod")
    out.append("    cdef list[Bar] from_raw_arrays_to_list_c(")
    out.append("        BarType bar_type,")
    out.append("        uint8_t price_prec,")
    out.append("        uint8_t size_prec,")
    out.append("        double[:] opens,")
    out.append("        double[:] highs,")
    out.append("        double[:] lows,")
    out.append("        double[:] closes,")
    out.append("        double[:] volumes,")
    out.append("        uint64_t[:] ts_events,")
    out.append("        uint64_t[:] ts_inits,")

    # Add extended field array parameters
    for field in fields:
        ident = field.get("ident")
        field_type = field.get("type")
        if field_type in ("quantity", "price"):
            out.append(f"        double[:] {ident}s,")
        elif field_type == "u64":
            out.append(f"        uint64_t[:] {ident}s,")
        elif field_type == "bool":
            out.append(f"        object[:] {ident}s,")

    # Remove trailing comma from last parameter
    if out[-1].endswith(","):
        out[-1] = out[-1][:-1]
    out.append("    )")
    out.append("")

    # Add remaining method signatures (no changes needed)
    out.append("    @staticmethod")
    out.append("    cdef Bar from_mem_c(Bar_t mem)")
    out.append("")
    out.append("    @staticmethod")
    out.append("    cdef Bar from_pyo3_c(pyo3_bar)")
    out.append("")
    out.append("    @staticmethod")
    out.append("    cdef Bar from_dict_c(dict values)")
    out.append("")
    out.append("    @staticmethod")
    out.append("    cdef dict to_dict_c(Bar obj)")
    out.append("")
    out.append("    cpdef bint is_single_price(self)")

    # Write to file
    output_file = GENERATED_CYTHON_DIR / "_extended_bar_sig.pxi"
    output_file.write_text("\n".join(out) + "\n", encoding="utf-8")


def _generate_full_bar_variants() -> None:
    """
    Generate full Bar class include files for both extended and standard variants.

    - `_generated/_extended_bar__bar.pxi` contains a complete Bar class with
      extended fields inlined (no `include` statements inside class).
    - `_generated/_standard_bar__bar.pxi` contains a complete Bar class using
      the standard path only (no extended blocks or includes inside class).
    """
    src = Path("nautilus_trader/model/data.pyx")
    if not src.exists():
        return  # development fallback

    lines = src.read_text(encoding="utf-8").splitlines()

    # Locate Bar class block boundaries
    start = None
    end = None
    for i, ln in enumerate(lines):
        if start is None and ln.strip().startswith("cdef class Bar("):
            start = i
        if start is not None and ln.strip().startswith("cdef class DataType:"):
            end = i
            break
    if start is None or end is None or end <= start:
        return

    block = lines[start:end]

    gen_dir = GENERATED_CYTHON_DIR

    def indent_width(s: str) -> int:
        return len(s) - len(s.lstrip(" "))

    def inline_include(line: str) -> list[str]:
        # Extract path between quotes
        try:
            path = line.split('"')[1]
        except Exception:
            return [line]
        p = gen_dir / Path(path).name
        if not p.exists():
            return [line]
        content = p.read_text(encoding="utf-8").splitlines()
        return content

    # Transform helper: keep only the standard (ELSE) branch
    def transform_standard(block_lines: list[str]) -> list[str]:
        out: list[str] = []
        i = 0
        while i < len(block_lines):
            line = block_lines[i]
            stripped = line.strip()
            if stripped.startswith("IF HAS_EXTENDED_BAR_FIELDS:"):
                base = indent_width(line)
                # skip extended branch
                i += 1
                while i < len(block_lines):
                    if indent_width(block_lines[i]) == base and block_lines[i].strip().startswith("ELSE:"):
                        i += 1
                        break
                    i += 1
                # copy else branch (removing the extra indentation from being inside ELSE)
                while i < len(block_lines) and indent_width(block_lines[i]) > base:
                    line_to_copy = block_lines[i]
                    # Remove the extra 4 spaces of indentation from being inside ELSE block
                    if line_to_copy.startswith("    "):
                        line_to_copy = line_to_copy[4:]  # Remove 4 spaces
                    out.append(line_to_copy)
                    i += 1
                continue
            else:
                out.append(line)
                i += 1

        # Normalize indentation - remove any common leading spaces from all lines
        if out:
            # Find minimum indentation (excluding empty lines)
            min_indent = float("inf")
            for line in out:
                if line.strip():  # Non-empty line
                    min_indent = min(min_indent, indent_width(line))

            # Remove the common indentation from all lines
            if min_indent > 0 and min_indent != float("inf"):
                normalized = []
                for line in out:
                    if line.strip():  # Non-empty line
                        # Preserve relative indentation by subtracting minimum
                        current_indent = indent_width(line)
                        relative_indent = current_indent - min_indent
                        normalized.append(" " * relative_indent + line.lstrip())
                    else:  # Empty line
                        normalized.append("")
                return normalized

        return out

    # Generate extended Bar class with proper field support
    def generate_extended_bar_class(block_lines: list[str]) -> list[str]:
        # Load extended field configuration
        fields = _load_extended_bar_fields()
        if not fields:
            # No extended fields, use standard Bar
            return transform_standard(block_lines)

        # Start with the standard Bar class as base
        standard = transform_standard(block_lines)
        out: list[str] = []

        i = 0
        while i < len(standard):
            line = standard[i]

            # Process __init__ method
            if "def __init__" in line:
                out.append(line)
                i += 1
                # Copy parameters until we hit the closing parenthesis
                while i < len(standard) and ") -> None:" not in standard[i]:
                    # Before the closing, add extended field params
                    if "bint is_revision" in standard[i]:
                        out.append(standard[i])
                        # Add extended field parameters after is_revision
                        for field in fields:
                            ident = field.get("ident")
                            field_type = field.get("type")
                            default = field.get("default", "0")
                            if field_type == "quantity":
                                out.append(f"        Quantity {ident}=None,")
                            elif field_type == "price":
                                out.append(f"        Price {ident}=None,")
                            elif field_type == "u64":
                                default_val = default.replace("_", "")
                                out.append(f"        uint64_t {ident}={default_val},")
                            elif field_type == "bool":
                                default_bool = _format_bool_default(default)
                                out.append(f"        bint {ident}={default_bool},")
                    else:
                        out.append(standard[i])
                    i += 1

                # Add the closing parenthesis
                if i < len(standard):
                    out.append(standard[i])
                    i += 1

                # Process the body of __init__ until we find self.is_revision (end of __init__)
                init_done = False
                while i < len(standard) and not init_done:
                    if "self._mem = bar_new(" in standard[i]:
                        # Add extended field processing before bar_new
                        # This code is generated from config, not hardcoded
                        for field in fields:
                            ident = field.get("ident")
                            field_type = field.get("type")
                            default = field.get("default", "0")

                            if field_type == "quantity":
                                out.append(f"        if {ident} is None:")
                                out.append(f"            {ident} = Quantity.from_str('{default}')")
                                out.append(f"        cdef Quantity_t _ext_{ident} = {ident}._mem")
                            elif field_type == "price":
                                out.append(f"        if {ident} is None:")
                                out.append(f"            {ident} = Price.from_str('{default}')")
                                out.append(f"        cdef Price_t _ext_{ident} = {ident}._mem")
                            elif field_type == "u64":
                                out.append(f"        cdef uint64_t _ext_{ident} = {ident}")
                            elif field_type == "bool":
                                out.append(f"        cdef bint _ext_{ident} = {ident}")

                        out.append("")  # Add blank line for readability

                        # Add the bar_new call
                        out.append(standard[i])
                        i += 1
                        # Copy arguments until closing
                        while i < len(standard) and not standard[i].strip() == ")":
                            out.append(standard[i])
                            i += 1
                        # Add extended field arguments before closing
                        for field in fields:
                            ident = field.get("ident")
                            out.append(f"            _ext_{ident},")
                        # Add the closing parenthesis
                        out.append(standard[i])
                        i += 1
                    elif "self.is_revision = is_revision" in standard[i]:
                        out.append(standard[i])
                        i += 1
                        init_done = True
                    elif "def __getstate__" in standard[i]:
                        # We've gone too far, stop
                        init_done = True
                        continue  # Don't increment i, let the main loop handle this line
                    else:
                        out.append(standard[i])
                        i += 1

            # Process __getstate__ method - add extended fields to state
            elif "def __getstate__" in line:
                out.append(line)
                i += 1
                # Copy the method until return statement
                while i < len(standard):
                    if "return bart_type_state + (" in standard[i]:
                        out.append(standard[i])
                        i += 1
                        # Copy standard fields
                        while i < len(standard) and not standard[i].strip() == ")":
                            out.append(standard[i])
                            i += 1
                        # Add extended fields to the tuple
                        for field in fields:
                            ident = field.get("ident")
                            field_type = field.get("type")
                            if field_type == "quantity":
                                out.append(f"            self._mem.{ident}.raw,")
                                out.append(f"            self._mem.{ident}.precision,")
                            elif field_type == "price":
                                out.append(f"            self._mem.{ident}.raw,")
                                out.append(f"            self._mem.{ident}.precision,")
                            elif field_type == "u64":
                                out.append(f"            self._mem.{ident},")
                        out.append(standard[i])  # closing parenthesis
                        i += 1
                        break
                    else:
                        out.append(standard[i])
                        i += 1

            # Process __setstate__ method - restore extended fields
            elif "def __setstate__" in line:
                out.append(line)
                i += 1

                # Add cdef declarations at the beginning of the method
                # First, copy any existing cdef declarations
                while i < len(standard) and standard[i].strip().startswith("cdef "):
                    out.append(standard[i])
                    i += 1

                # Add extended field declarations at the beginning (before any if statements)
                for field in fields:
                    ident = field.get("ident")
                    field_type = field.get("type")
                    if field_type == "quantity":
                        out.append(f"        cdef Quantity_t _ext_{ident}")
                    elif field_type == "price":
                        out.append(f"        cdef Price_t _ext_{ident}")
                    elif field_type == "u64":
                        out.append(f"        cdef uint64_t _ext_{ident}")
                    elif field_type == "bool":
                        out.append(f"        cdef bint _ext_{ident}")

                # Calculate expected state lengths for extended fields
                if fields:
                    # Calculate how many state elements the extended fields add
                    extended_state_count = 0
                    for field in fields:
                        field_type = field.get("type")
                        if field_type in ("quantity", "price"):
                            extended_state_count += 2  # raw + prec
                        else:  # u64 or bool
                            extended_state_count += 1

                    # Declare expected length variables and index variable
                    out.append(f"        cdef Py_ssize_t expected_standard_len = {14 + extended_state_count}")
                    out.append(f"        cdef Py_ssize_t expected_composite_len = {17 + extended_state_count}")
                    out.append("        cdef int idx  # Index for iterating through extended fields")

                # Process the method body to handle extended fields in bar_new calls
                while i < len(standard):
                    # Fix indentation for if statement blocks
                    if "if len(state) ==" in standard[i]:
                        # Determine if this is standard or composite branch
                        is_standard_branch = "== 14" in standard[i]
                        expected_len_var = "expected_standard_len" if is_standard_branch else "expected_composite_len"
                        start_idx = 14 if is_standard_branch else 17

                        # Modify the if statement to support both old and new state lengths
                        if fields and is_standard_branch:
                            # For extended bars, accept both legacy 14-element and new extended-length states
                            out.append("        if len(state) == 14 or len(state) == expected_standard_len:")
                        else:
                            # Keep original condition for composite or no-fields case
                            out.append(standard[i])
                        i += 1

                        # Calculate base indent for this branch (should be 12 spaces for if block content)
                        branch_base_indent = 12

                        # Copy the block contents preserving relative indentation
                        while i < len(standard) and "self._mem = bar_new(" not in standard[i] and not standard[i].strip().startswith("else:"):
                            line_content = standard[i]
                            if line_content.strip():
                                # Preserve relative indentation from original
                                original_indent = indent_width(line_content)
                                # In standard Bar, if block starts at 12, so calculate relative
                                relative_indent = original_indent - 12 if original_indent >= 12 else 0
                                final_indent = branch_base_indent + relative_indent
                                out.append(" " * final_indent + line_content.lstrip())
                                # After reading size_prec, add extended field restoration logic
                                if "size_prec = state[" in line_content:
                                    # Add logic to restore extended fields from state or use defaults
                                    out.append("            # Restore extended fields from state or use defaults")
                                    if fields:
                                        # Check if state has extended fields (new format) or legacy format
                                        out.append(f"            if len(state) == {expected_len_var}:")
                                        out.append("                # Extended state format - restore fields")
                                        out.append(f"                idx = {start_idx}")

                                        # Restore each extended field from state
                                        for field in fields:
                                            ident = field.get("ident")
                                            field_type = field.get("type")
                                            if field_type == "quantity":
                                                out.append(f"                _ext_{ident} = quantity_new(state[idx], state[idx + 1])")
                                                out.append("                idx += 2")
                                            elif field_type == "price":
                                                out.append(f"                _ext_{ident} = price_new(state[idx], state[idx + 1])")
                                                out.append("                idx += 2")
                                            elif field_type == "u64":
                                                out.append(f"                _ext_{ident} = <uint64_t>state[idx]")
                                                out.append("                idx += 1")
                                            elif field_type == "bool":
                                                out.append(f"                _ext_{ident} = <bint>state[idx]")
                                                out.append("                idx += 1")

                                        # Else branch for legacy state without extended fields
                                        out.append("            else:")
                                        out.append("                # Legacy state format - use defaults")
                                        for field in fields:
                                            ident = field.get("ident")
                                            field_type = field.get("type")
                                            default = field.get("default", "0")
                                            if field_type == "quantity":
                                                out.append(f"                _ext_{ident} = Quantity.from_str_c('{default}')._mem")
                                            elif field_type == "price":
                                                out.append(f"                _ext_{ident} = Price.from_str_c('{default}')._mem")
                                            elif field_type == "u64":
                                                out.append(f"                _ext_{ident} = {default}")
                                            elif field_type == "bool":
                                                default_bool = _format_bool_default(default)
                                                out.append(f"                _ext_{ident} = {default_bool}")
                            else:
                                out.append(standard[i])
                            i += 1
                        # Now continue with normal processing for the bar_new call
                        continue
                    # Fix indentation for else blocks
                    elif standard[i].strip() == "else:" and i > 0:
                        # else block handles composite branch
                        expected_len_var = "expected_composite_len"
                        start_idx = 17

                        out.append(standard[i])
                        i += 1

                        # Calculate base indent for else branch
                        branch_base_indent = 12

                        # Copy else block preserving relative indentation
                        while i < len(standard) and standard[i].strip() and "self._mem = bar_new(" not in standard[i] and "def " not in standard[i]:
                            line_content = standard[i]
                            if line_content.strip():
                                # Preserve relative indentation from original
                                original_indent = indent_width(line_content)
                                # In standard Bar, else block starts at 12, calculate relative
                                relative_indent = original_indent - 12 if original_indent >= 12 else 0
                                final_indent = branch_base_indent + relative_indent
                                out.append(" " * final_indent + line_content.lstrip())
                                # After reading size_prec, add extended field restoration logic
                                if "size_prec = state[" in line_content:
                                    # Add logic to restore extended fields from state or use defaults
                                    out.append("            # Restore extended fields from state or use defaults")
                                    if fields:
                                        # Check if state has extended fields (new format) or legacy format
                                        out.append(f"            if len(state) == {expected_len_var}:")
                                        out.append("                # Extended state format - restore fields")
                                        out.append(f"                idx = {start_idx}")

                                        # Restore each extended field from state
                                        for field in fields:
                                            ident = field.get("ident")
                                            field_type = field.get("type")
                                            if field_type == "quantity":
                                                out.append(f"                _ext_{ident} = quantity_new(state[idx], state[idx + 1])")
                                                out.append("                idx += 2")
                                            elif field_type == "price":
                                                out.append(f"                _ext_{ident} = price_new(state[idx], state[idx + 1])")
                                                out.append("                idx += 2")
                                            elif field_type == "u64":
                                                out.append(f"                _ext_{ident} = <uint64_t>state[idx]")
                                                out.append("                idx += 1")
                                            elif field_type == "bool":
                                                out.append(f"                _ext_{ident} = <bint>state[idx]")
                                                out.append("                idx += 1")

                                        # Else branch for legacy state without extended fields
                                        out.append("            else:")
                                        out.append("                # Legacy state format - use defaults")
                                        for field in fields:
                                            ident = field.get("ident")
                                            field_type = field.get("type")
                                            default = field.get("default", "0")
                                            if field_type == "quantity":
                                                out.append(f"                _ext_{ident} = Quantity.from_str_c('{default}')._mem")
                                            elif field_type == "price":
                                                out.append(f"                _ext_{ident} = Price.from_str_c('{default}')._mem")
                                            elif field_type == "u64":
                                                out.append(f"                _ext_{ident} = {default}")
                                            elif field_type == "bool":
                                                default_bool = _format_bool_default(default)
                                                out.append(f"                _ext_{ident} = {default_bool}")
                            else:
                                out.append(standard[i])
                            i += 1
                        continue
                    # Check for bar_new calls in both branches (state length 14 and other)
                    elif "self._mem = bar_new(" in standard[i]:
                        # Check if we're inside an if or else block by looking at recent lines
                        in_if_block = False
                        in_else_block = False
                        for j in range(min(15, len(out))):
                            if j < len(out):
                                recent_line = out[-(j+1)]
                                if "else:" in recent_line:
                                    in_else_block = True
                                    break
                                elif "if len(state) ==" in recent_line:
                                    in_if_block = True
                                    break

                        # Determine base indentation based on context
                        base_indent = 12 if (in_if_block or in_else_block) else 8

                        # Extended field values should be restored from state at the branch level
                        # They are declared as cdef at the method start and set in each branch
                        # No default assignment needed here - values set per branch based on state length

                        # Add the bar_new call preserving relative indentation
                        bar_new_original_indent = indent_width(standard[i])
                        bar_new_relative = bar_new_original_indent - (12 if (in_if_block or in_else_block) else 8)
                        bar_new_final_indent = base_indent + bar_new_relative
                        out.append(" " * bar_new_final_indent + standard[i].lstrip())
                        i += 1

                        # Copy arguments until closing parenthesis, preserving relative indentation
                        while i < len(standard) and not standard[i].strip() == ")":
                            line_content = standard[i]
                            if line_content.strip():
                                # Calculate relative indent from bar_new's first argument
                                original_indent = indent_width(line_content)
                                # Arguments should be relative to bar_new call
                                relative_indent = original_indent - bar_new_original_indent
                                final_indent = bar_new_final_indent + relative_indent
                                out.append(" " * final_indent + line_content.lstrip())
                            else:
                                out.append(line_content)  # Empty line
                            i += 1

                        # Add extended field arguments with same indent as other bar_new args
                        # Find the indent level of bar_new's first argument
                        arg_indent_spaces = bar_new_final_indent + 4  # Standard arg indent is +4 from bar_new
                        for field in fields:
                            ident = field.get("ident")
                            if field["type"] in ["quantity", "price", "u64", "bool"]:
                                out.append(" " * arg_indent_spaces + f"_ext_{ident},")

                        # Add closing parenthesis with proper indentation
                        out.append(" " * bar_new_final_indent + ")")
                        i += 1
                    elif "def __eq__" in standard[i] or "def __hash__" in standard[i]:
                        # We've reached the next method, stop processing __setstate__
                        break
                    else:
                        out.append(standard[i])
                        i += 1

            # Process from_raw_c static method
            elif "cdef Bar from_raw_c(" in line:
                out.append(line)
                i += 1
                # Copy parameters until closing
                while i < len(standard) and not standard[i].strip().endswith("):"):
                    if "uint64_t ts_init," in standard[i]:
                        out.append(standard[i])
                        # Add extended field parameters with same indent as other params (8 spaces)
                        for field in fields:
                            ident = field.get("ident")
                            field_type = field.get("type")
                            if field_type == "quantity":
                                out.append(f"        QuantityRaw {ident}_raw,")
                                out.append(f"        uint8_t {ident}_prec,")
                            elif field_type == "price":
                                out.append(f"        PriceRaw {ident}_raw,")
                                out.append(f"        uint8_t {ident}_prec,")
                            elif field_type == "u64":
                                out.append(f"        uint64_t {ident},")
                            elif field_type == "bool":
                                out.append(f"        bint {ident},")
                    else:
                        out.append(standard[i])
                    i += 1
                # Process the closing and body
                if i < len(standard):
                    out.append(standard[i])  # ):
                    i += 1
                # Process the body
                while i < len(standard):
                    if "bar._mem = bar_new(" in standard[i]:
                        # Add extended field conversions before bar_new
                        for field in fields:
                            ident = field.get("ident")
                            field_type = field.get("type")
                            if field_type == "quantity":
                                out.append(f"        cdef Quantity_t {ident}_qty = quantity_new({ident}_raw, {ident}_prec)")
                            elif field_type == "price":
                                out.append(f"        cdef Price_t {ident}_price = price_new({ident}_raw, {ident}_prec)")

                        out.append(standard[i])
                        i += 1
                        # Copy arguments until closing
                        while i < len(standard) and not standard[i].strip() == ")":
                            out.append(standard[i])
                            i += 1
                        # Add extended field arguments
                        for field in fields:
                            ident = field.get("ident")
                            field_type = field.get("type")
                            if field_type == "quantity":
                                out.append(f"            {ident}_qty,")
                            elif field_type == "price":
                                out.append(f"            {ident}_price,")
                            elif field_type == "u64":
                                out.append(f"            {ident},")
                            elif field_type == "bool":
                                out.append(f"            {ident},")
                        out.append(standard[i])  # closing
                        i += 1
                        break
                    else:
                        out.append(standard[i])
                        i += 1

            # Process from_dict_c - add extended fields
            elif "cdef Bar from_dict_c(dict values):" in line:
                out.append(line)
                i += 1
                # Copy until return Bar(
                while i < len(standard):
                    if "return Bar(" in standard[i]:
                        out.append(standard[i])
                        i += 1
                        # Copy standard arguments
                        while i < len(standard) and not standard[i].strip() == ")":
                            out.append(standard[i])
                            i += 1
                        # Add extended field arguments from dict
                        for field in fields:
                            ident = field.get("ident")
                            field_type = field.get("type")
                            if field_type == "quantity":
                                out.append(f'                {ident}=Quantity.from_str_c(values.get("{ident}", "0")) if "{ident}" in values else None,')
                            elif field_type == "price":
                                out.append(f'                {ident}=Price.from_str_c(values.get("{ident}", "0")) if "{ident}" in values else None,')
                            elif field_type == "u64":
                                out.append(f'                {ident}=values.get("{ident}", 0),')
                            elif field_type == "bool":
                                default_bool = _format_bool_default(field.get("default"))
                                out.append(f'                {ident}=values.get("{ident}", {default_bool}),')
                        out.append(standard[i])  # closing
                        i += 1
                        break
                    else:
                        out.append(standard[i])
                        i += 1

            # Process to_dict_c - add extended fields to output
            elif "cdef dict to_dict_c(Bar obj):" in line:
                out.append(line)
                i += 1
                # Copy until return {
                while i < len(standard):
                    if "return {" in standard[i]:
                        out.append(standard[i])
                        i += 1
                        # Copy standard fields
                        while i < len(standard) and not standard[i].strip() == "}":
                            out.append(standard[i])
                            i += 1
                        # Add extended fields to dict
                        for field in fields:
                            ident = field.get("ident")
                            out.append(f'                "{ident}": str(obj.{ident}),')
                        out.append(standard[i])  # closing }
                        i += 1
                        break
                    else:
                        out.append(standard[i])
                        i += 1

            # Process from_raw_arrays_to_list_c - needs extended array parameters
            elif "cdef list[Bar] from_raw_arrays_to_list_c(" in line:
                out.append(line)
                i += 1
                # Copy parameters until closing
                while i < len(standard) and not standard[i].strip().endswith("):"):
                    if "uint64_t[:] ts_inits," in standard[i]:
                        out.append(standard[i])
                        # Add extended field array parameters (8 spaces to match other params)
                        for field in fields:
                            ident = field.get("ident")
                            field_type = field.get("type")
                            if field_type == "quantity":
                                out.append(f"        double[:] {ident}s,")
                            elif field_type == "price":
                                out.append(f"        double[:] {ident}s,")
                            elif field_type == "u64":
                                out.append(f"        uint64_t[:] {ident}s,")
                            elif field_type == "bool":
                                out.append(f"        object[:] {ident}s,")
                    else:
                        out.append(standard[i])
                    i += 1
                # Process closing and body
                if i < len(standard):
                    out.append(standard[i])  # ):
                    i += 1

                # Process assertion to add extended field array length checks
                while i < len(standard):
                    if "Condition.is_true(" in standard[i]:
                        out.append(standard[i])
                        i += 1
                        # Copy assertion lines until we find the line with ts_inits
                        while i < len(standard) and "ts_inits)" not in standard[i]:
                            out.append(standard[i])
                            i += 1
                        # Found the line with ts_inits) - modify it to add extended arrays
                        if i < len(standard):
                            line_content = standard[i]
                            if fields:
                                # Remove the closing comma and parenthesis, add ==
                                modified_line = line_content.replace("ts_inits),", "ts_inits) ==")
                                out.append(modified_line)
                                # Add extended field array checks
                                extended_checks = [f"len({field.get('ident')}s)" for field in fields]
                                out.append("            " + " == ".join(extended_checks) + ",")
                            else:
                                out.append(line_content)
                            i += 1
                        break
                    else:
                        out.append(standard[i])
                        i += 1

                # Look for the cdef block to add extended field declarations
                while i < len(standard):
                    if "Bar bar" in standard[i]:
                        # Add this line (Bar bar)
                        out.append(standard[i])
                        # Add extended field declarations right after Bar bar
                        # Use 12 spaces to align with other cdef variables in the block
                        for field in fields:
                            ident = field.get("ident")
                            field_type = field.get("type")
                            if field_type == "quantity":
                                out.append(f"            Quantity {ident}_qty")
                            elif field_type == "price":
                                out.append(f"            Price {ident}_price")
                        i += 1
                        break
                    else:
                        out.append(standard[i])
                        i += 1

                # Process the rest of the body to handle extended arrays in bar creation loop
                while i < len(standard):
                    # Look for the bar_new call inside the loop
                    if "bar._mem = bar_new(" in standard[i]:
                        # Add extended field conversions before bar_new for each iteration
                        # Use 12 spaces to match other assignments in the loop
                        for field in fields:
                            ident = field.get("ident")
                            field_type = field.get("type")
                            # Note: these need to use the array index [i]
                            if field_type == "quantity":
                                out.append(f"            {ident}_qty = Quantity({ident}s[i], size_prec)")
                            elif field_type == "price":
                                out.append(f"            {ident}_price = Price({ident}s[i], price_prec)")
                            # u64 and bool don't need conversion

                        out.append(standard[i])
                        i += 1
                        # Copy arguments until closing
                        while i < len(standard) and not standard[i].strip() == ")":
                            out.append(standard[i])
                            i += 1
                        # Add extended field arguments
                        for field in fields:
                            ident = field.get("ident")
                            field_type = field.get("type")
                            if field_type == "quantity":
                                out.append(f"                {ident}_qty._mem,")
                            elif field_type == "price":
                                out.append(f"                {ident}_price._mem,")
                            elif field_type == "u64":
                                out.append(f"                {ident}s[i],")
                            elif field_type == "bool":
                                out.append(f"                <bint>{ident}s[i],")
                        out.append(standard[i])  # closing
                        i += 1
                    elif "return bars" in standard[i]:
                        # return should be AFTER the loop, not inside it (8 spaces, not 12)
                        # Preserve original indentation from standard Bar
                        out.append(standard[i])
                        i += 1
                        break
                    else:
                        out.append(standard[i])
                        i += 1

            # Process from_raw wrapper method - add extended parameters
            elif "def from_raw(" in line:
                out.append(line)
                i += 1
                # Copy parameters until closing
                while i < len(standard) and ") -> Bar:" not in standard[i]:
                    if "uint64_t ts_init," in standard[i]:
                        out.append(standard[i])
                        # Add extended field parameters matching from_raw_c (8 spaces)
                        for field in fields:
                            ident = field.get("ident")
                            field_type = field.get("type")
                            if field_type == "quantity":
                                out.append(f"        QuantityRaw {ident}_raw,")
                                out.append(f"        uint8_t {ident}_prec,")
                            elif field_type == "price":
                                out.append(f"        PriceRaw {ident}_raw,")
                                out.append(f"        uint8_t {ident}_prec,")
                            elif field_type == "u64":
                                out.append(f"        uint64_t {ident},")
                            elif field_type == "bool":
                                out.append(f"        bint {ident},")
                    else:
                        out.append(standard[i])
                    i += 1
                # Process closing and body
                if i < len(standard):
                    out.append(standard[i])  # ) -> Bar:
                    i += 1
                # Process the body - should be return Bar.from_raw_c(...)
                while i < len(standard):
                    if "return Bar.from_raw_c(" in standard[i]:
                        out.append(standard[i])
                        i += 1
                        # Copy arguments until closing
                        while i < len(standard) and not standard[i].strip() == ")":
                            out.append(standard[i])
                            i += 1
                        # Add extended field arguments
                        for field in fields:
                            ident = field.get("ident")
                            field_type = field.get("type")
                            if field_type == "quantity":
                                out.append(f"            {ident}_raw,")
                                out.append(f"            {ident}_prec,")
                            elif field_type == "price":
                                out.append(f"            {ident}_raw,")
                                out.append(f"            {ident}_prec,")
                            elif field_type == "u64":
                                out.append(f"            {ident},")
                            elif field_type == "bool":
                                out.append(f"            {ident},")
                        out.append(standard[i])  # closing
                        i += 1
                        break
                    else:
                        out.append(standard[i])
                        i += 1

            # Process from_raw_arrays_to_list wrapper method - add extended parameters
            elif "def from_raw_arrays_to_list(" in line:
                out.append(line)
                i += 1
                # Copy parameters until closing
                while i < len(standard) and ") -> list[Bar]:" not in standard[i]:
                    if "uint64_t[:] ts_inits," in standard[i]:
                        out.append(standard[i])
                        # Add extended field array parameters (8 spaces to match other params)
                        for field in fields:
                            ident = field.get("ident")
                            field_type = field.get("type")
                            if field_type == "quantity":
                                out.append(f"        double[:] {ident}s,")
                            elif field_type == "price":
                                out.append(f"        double[:] {ident}s,")
                            elif field_type == "u64":
                                out.append(f"        uint64_t[:] {ident}s,")
                            elif field_type == "bool":
                                out.append(f"        object[:] {ident}s,")
                    else:
                        out.append(standard[i])
                    i += 1
                # Process closing and body
                if i < len(standard):
                    out.append(standard[i])  # ) -> list[Bar]:
                    i += 1
                # Process the body - should be return Bar.from_raw_arrays_to_list_c(...)
                while i < len(standard):
                    if "return Bar.from_raw_arrays_to_list_c(" in standard[i]:
                        out.append(standard[i])
                        i += 1
                        # Copy arguments until closing
                        while i < len(standard) and not standard[i].strip() == ")":
                            out.append(standard[i])
                            i += 1
                        # Add extended field array arguments
                        for field in fields:
                            ident = field.get("ident")
                            out.append(f"            {ident}s,")
                        out.append(standard[i])  # closing
                        i += 1
                        break
                    else:
                        out.append(standard[i])
                        i += 1

            # Process to_pyo3_list method - add extended fields as kwargs
            elif "def to_pyo3_list(list bars)" in line:
                out.append(line)
                i += 1
                # Copy method body until we find nautilus_pyo3.Bar construction
                while i < len(standard):
                    # Check if we found the Bar construction line
                    if "pyo3_bar = nautilus_pyo3.Bar(" in standard[i]:
                        out.append(standard[i])
                        i += 1
                        # Copy all positional arguments (OHLCV + timestamps)
                        # until we find the closing parenthesis
                        bar_construction_lines = []
                        while i < len(standard) and not standard[i].strip() == ")":
                            bar_construction_lines.append(standard[i])
                            i += 1

                        # Output all the positional argument lines
                        out.extend(bar_construction_lines)

                        # Now inject extended field keyword arguments
                        # The indentation should match the other arguments (bar._mem.ts_init line)
                        arg_indent = "                "  # Match bar._mem.ts_init indentation
                        for field in fields:
                            ident = field.get("ident")
                            field_type = field.get("type")
                            if field_type == "quantity":
                                out.append(f"{arg_indent}{ident}=nautilus_pyo3.Quantity.from_raw(bar._mem.{ident}.raw, bar._mem.{ident}.precision),")
                            elif field_type == "price":
                                out.append(f"{arg_indent}{ident}=nautilus_pyo3.Price.from_raw(bar._mem.{ident}.raw, bar._mem.{ident}.precision),")
                            elif field_type == "u64":
                                out.append(f"{arg_indent}{ident}=bar._mem.{ident},")
                            elif field_type == "bool":
                                out.append(f"{arg_indent}{ident}=bar._mem.{ident},")

                        # Add the closing parenthesis
                        out.append(standard[i])
                        i += 1
                        # After processing the Bar construction, continue copying the rest of the method
                        continue

                    # Check if we've reached the next method definition (not cdef)
                    if i > 0 and standard[i].strip().startswith("def ") and "def to_pyo3_list" not in standard[i]:
                        # We've reached the next method without finding Bar construction
                        break

                    # Regular line - just copy it
                    out.append(standard[i])
                    i += 1

            # Process to_pyo3 instance method - add extended fields as kwargs
            elif "def to_pyo3(self)" in line:
                out.append(line)
                i += 1
                # Copy method until we find the return statement with nautilus_pyo3.Bar
                while i < len(standard):
                    if "return nautilus_pyo3.Bar(" in standard[i]:
                        out.append(standard[i])
                        i += 1
                        # Copy all positional arguments until closing parenthesis
                        return_construction_lines = []
                        while i < len(standard) and not standard[i].strip() == ")":
                            return_construction_lines.append(standard[i])
                            i += 1

                        # Output all positional argument lines
                        out.extend(return_construction_lines)

                        # Inject extended field keyword arguments
                        # Match indentation of other arguments
                        arg_indent = "                "  # Match nautilus_pyo3.Price indentation in to_pyo3
                        for field in fields:
                            ident = field.get("ident")
                            field_type = field.get("type")
                            if field_type == "quantity":
                                out.append(f"{arg_indent}{ident}=nautilus_pyo3.Quantity.from_raw(self._mem.{ident}.raw, self._mem.{ident}.precision),")
                            elif field_type == "price":
                                out.append(f"{arg_indent}{ident}=nautilus_pyo3.Price.from_raw(self._mem.{ident}.raw, self._mem.{ident}.precision),")
                            elif field_type == "u64":
                                out.append(f"{arg_indent}{ident}=self._mem.{ident},")
                            elif field_type == "bool":
                                out.append(f"{arg_indent}{ident}=self._mem.{ident},")

                        # Add the closing parenthesis
                        out.append(standard[i])
                        i += 1
                        break  # End of return statement, exit method processing
                    else:
                        out.append(standard[i])
                        i += 1

            else:
                # Check for the specific indentation issue with return bar_from_mem_c
                if "return bar_from_mem_c(ptr.bar)" in line and line.startswith("            "):
                    # This line has 12 spaces but should have 8
                    out.append("        return bar_from_mem_c(ptr.bar)")
                else:
                    out.append(line)
                i += 1

        # Add extended field properties at the end of class
        # Use 4 spaces for class-level decorators and method definitions
        for field in fields:
            ident = field.get("ident")
            field_type = field.get("type")
            doc = field.get("doc", "")

            out.append("")  # Empty line separator (truly empty)
            out.append("    @property")
            out.append(f"    def {ident}(self):")
            if doc:
                out.append('        """')
                out.append(f"        {doc}")
                out.append('        """')

            if field_type == "quantity":
                out.append(f"        return Quantity.from_raw_c(self._mem.{ident}.raw, self._mem.{ident}.precision)")
            elif field_type == "price":
                out.append(f"        return Price.from_raw_c(self._mem.{ident}.raw, self._mem.{ident}.precision)")
            elif field_type == "u64":
                out.append(f"        return self._mem.{ident}")
            elif field_type == "bool":
                out.append(f"        return self._mem.{ident}")

            out.append("")  # Empty line separator (truly empty)
            out.append(f"    @{ident}.setter")
            out.append(f"    def {ident}(self, value) -> None:")

            if field_type == "quantity":
                out.append(f"        self._mem.{ident} = (<Quantity>value)._mem")
            elif field_type == "price":
                out.append(f"        self._mem.{ident} = (<Price>value)._mem")
            elif field_type == "u64":
                out.append(f"        self._mem.{ident} = <uint64_t>value")
            elif field_type == "bool":
                out.append(f"        self._mem.{ident} = value")

        return out

    # Generate the extended bar class with proper field support
    extended_full = generate_extended_bar_class(block)
    standard_full = transform_standard(block)

    # Write outputs (ensure trailing newline)
    (gen_dir / "_extended_bar__bar.pxi").write_text("\n".join(extended_full) + "\n", encoding="utf-8")
    (gen_dir / "_standard_bar__bar.pxi").write_text("\n".join(standard_full) + "\n", encoding="utf-8")


def _set_feature_flags() -> list[str]:
    features = "ffi,python,extension-module,postgres,extended_bar"
    flags = ["--no-default-features", "--features"]

    if HIGH_PRECISION:
        features += ",high-precision"

    flags.append(features)

    return flags


def _build_rust_libs() -> None:
    print("Compiling Rust libraries...")

    try:
        # Build the Rust libraries using Cargo
        if RUSTUP_TOOLCHAIN not in ("stable", "nightly"):
            raise ValueError(f"Invalid `RUSTUP_TOOLCHAIN` '{RUSTUP_TOOLCHAIN}'")

        needed_crates = [
            "nautilus-backtest",
            "nautilus-common",
            "nautilus-core",
            "nautilus-factorexp",
            "nautilus-infrastructure",
            "nautilus-model",
            "nautilus-persistence",
            "nautilus-pyo3",
        ]

        build_options = " --release" if BUILD_MODE == "release" else ""
        features = _set_feature_flags()

        cmd_args = [
            "cargo",
            "build",
            "--lib",
            *itertools.chain.from_iterable(("-p", p) for p in needed_crates),
            *build_options.split(),
            *features,
        ]

        if RUSTUP_TOOLCHAIN == "nightly":
            cmd_args.insert(1, "+nightly")

        print(" ".join(cmd_args))

        subprocess.run(
            cmd_args,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"Error running cargo: {e}",
        ) from e


################################################################################
#  CYTHON BUILD
################################################################################
# https://cython.readthedocs.io/en/latest/src/userguide/source_files_and_compilation.html

Options.docstrings = True  # Include docstrings in modules
Options.fast_fail = True  # Abort the compilation on the first error occurred
Options.annotate = ANNOTATION_MODE  # Create annotated HTML files for each .pyx
if ANNOTATION_MODE:
    Options.annotate_coverage_xml = "coverage.xml"

CYTHON_COMPILER_DIRECTIVES = {
    "language_level": "3",
    "cdivision": True,  # If division is as per C with no check for zero (35% speed up)
    "nonecheck": True,  # Insert extra check for field access on C extensions
    "embedsignature": True,  # If docstrings should be embedded into C signatures
    "profile": PROFILE_MODE,  # If we're debugging or profiling
    "linetrace": PROFILE_MODE,  # If we're debugging or profiling
    "warn.maybe_uninitialized": True,
}

# TODO: Temporarily separate Cython configuration while we require v3.0.11 for coverage
if cython_compiler_version == "3.1.2":
    Options.warning_errors = True  # Treat compiler warnings as errors
    Options.extra_warnings = True
    CYTHON_COMPILER_DIRECTIVES["warn.deprecated.IF"] = False


def _build_extensions() -> list[Extension]:
    # Regarding the compiler warning: #warning "Using deprecated NumPy API,
    # disable it with " "#define NPY_NO_DEPRECATED_API NPY_1_7_API_VERSION"
    # https://stackoverflow.com/questions/52749662/using-deprecated-numpy-api
    # From the Cython docs: "For the time being, it is just a warning that you can ignore."
    define_macros: list[tuple[str, str | None]] = [
        ("NPY_NO_DEPRECATED_API", "NPY_1_7_API_VERSION"),
    ]
    if PROFILE_MODE or ANNOTATION_MODE:
        # Profiling requires special macro directives
        define_macros.append(("CYTHON_TRACE", "1"))

    extra_compile_args = []
    extra_link_args = RUST_LIBS

    if not IS_WINDOWS:
        # Suppress warnings produced by Cython boilerplate
        extra_compile_args.append("-Wno-unreachable-code")
        if BUILD_MODE == "release":
            extra_compile_args.append("-O2")
            extra_compile_args.append("-pipe")

    if IS_WINDOWS:
        # Standard Windows system libraries required when linking Cython extensions.
        # Keep this list lowercase and alphabetically sorted for easy maintenance
        # and to avoid duplicates sneaking in.
        extra_link_args += [
            "advapi32.lib",
            "bcrypt.lib",
            "crypt32.lib",
            "iphlpapi.lib",
            "kernel32.lib",
            "ncrypt.lib",
            "netapi32.lib",
            "ntdll.lib",
            "ole32.lib",
            "oleaut32.lib",
            "pdh.lib",
            "powrprof.lib",
            "propsys.lib",
            "psapi.lib",
            "runtimeobject.lib",
            "schannel.lib",
            "secur32.lib",
            "shell32.lib",
            "user32.lib",
            "userenv.lib",
            "ws2_32.lib",
        ]

    print("Creating C extension modules...")
    print(f"define_macros={define_macros}")
    print(f"extra_compile_args={extra_compile_args}")

    return [
        Extension(
            name=str(pyx.relative_to(".")).replace(os.path.sep, ".")[:-4],
            sources=[str(pyx)],
            include_dirs=[np.get_include(), *RUST_INCLUDES],
            define_macros=define_macros,
            language="c",
            extra_link_args=extra_link_args,
            extra_compile_args=extra_compile_args,
        )
        for pyx in itertools.chain(Path("nautilus_trader").rglob("*.pyx"))
    ]


def _build_distribution(extensions: list[Extension]) -> Distribution:
    nthreads = os.cpu_count() or 1
    if IS_WINDOWS:
        nthreads = min(nthreads, 60)
    print(f"nthreads={nthreads}")

    distribution = Distribution(
        {
            "name": "nautilus_trader",
            "ext_modules": cythonize(
                module_list=extensions,
                compiler_directives=CYTHON_COMPILER_DIRECTIVES,
                nthreads=nthreads,
                build_dir=BUILD_DIR,
                gdb_debug=PROFILE_MODE,
            ),
            "zip_safe": False,
        },
    )
    return distribution


def _copy_build_dir_to_project(cmd: build_ext) -> None:
    # Copy built extensions back to the project tree
    for output in cmd.get_outputs():
        relative_extension = Path(output).relative_to(cmd.build_lib)
        if not Path(output).exists():
            continue

        # Copy the file and set permissions
        shutil.copyfile(output, relative_extension)
        mode = relative_extension.stat().st_mode
        mode |= (mode & 0o444) >> 2
        relative_extension.chmod(mode)

    print("Copied all compiled dynamic library files into source")


def _copy_rust_dylibs_to_project() -> None:
    # https://pyo3.rs/latest/building-and-distribution#manual-builds
    ext_suffix = sysconfig.get_config_var("EXT_SUFFIX")
    src = Path(CARGO_TARGET_DIR) / f"{RUST_LIB_PFX}nautilus_pyo3.{RUST_DYLIB_EXT}"
    dst = Path("nautilus_trader/core") / f"nautilus_pyo3{ext_suffix}"
    shutil.copyfile(src=src, dst=dst)

    print(f"Copied {src} to {dst}")


def _get_nautilus_version() -> str:
    with open("pyproject.toml", encoding="utf-8") as f:
        pyproject_content = f.read().strip()
    if not pyproject_content:
        raise ValueError("pyproject.toml is empty or not properly formatted")

    version_match = re.search(r'version\s*=\s*"(.*?)"', pyproject_content)
    if not version_match:
        raise ValueError("Version not found in pyproject.toml")

    return version_match.group(1)


def _get_clang_version() -> str:
    try:
        result = subprocess.run(
            ["clang", "--version"],  # noqa
            check=True,
            capture_output=True,
        )
        output = (
            result.stdout.decode()
            .splitlines()[0]
            .lstrip("Apple ")
            .lstrip("Ubuntu ")
            .lstrip("clang version ")
        )
        return output
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        err_msg = str(e) if isinstance(e, FileNotFoundError) else e.stderr.decode()
        raise RuntimeError(
            "You are installing from source which requires the Clang compiler to be installed.\n"
            f"Error running clang: {err_msg}",
        ) from e


def _get_rustc_version() -> str:
    try:
        result = subprocess.run(
            ["rustc", "--version"],  # noqa
            check=True,
            capture_output=True,
        )
        output = result.stdout.decode().lstrip("rustc ").strip()
        return output
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        err_msg = str(e) if isinstance(e, FileNotFoundError) else e.stderr.decode()
        raise RuntimeError(
            "You are installing from source which requires the Rust compiler to be installed.\n"
            "Find more information at https://www.rust-lang.org/tools/install\n"
            f"Error running rustc: {err_msg}",
        ) from e


def _ensure_windows_python_import_lib() -> None:
    """
    Ensure that the *t* suffixed Python import library exists on Windows.

    On some official CPython Windows builds the import library is named
    ``pythonXY.lib`` (for example ``python313.lib``). However, when building
    C-extensions ``distutils``/``setuptools`` may ask the MSVC linker for the
    file ``pythonXYt.lib`` - note the additional *t* suffix. The *t* variant
    historically referred to a *thread-safe* build but is no longer shipped.

    When the file is missing the linker exits with
    ``LINK : fatal error LNK1104: cannot open file 'pythonXYt.lib'`` which
    breaks the CI build on Windows. To work around this we simply create a
    copy of the existing import library with the expected name **before** the
    extension build starts.

    """
    if not IS_WINDOWS:
        return

    try:
        # The virtual environment as well as the base installation may both
        # participate in the link search path.  Attempt the fix in both
        # locations to maximise the chance of success.
        candidate_roots = {Path(sys.base_prefix), Path(sys.prefix)}

        # Example: for Python 3.13 -> '313'
        major, minor, *_ = platform.python_version_tuple()
        version_compact = f"{major}{minor}"

        for root in candidate_roots:
            libs_dir = root / "libs"
            if not libs_dir.exists():
                continue

            src = libs_dir / f"python{version_compact}.lib"
            dst = libs_dir / f"python{version_compact}t.lib"

            if src.exists() and not dst.exists():
                print(
                    "Creating missing Windows import lib " f"{dst} (copying from {src})",
                )
                shutil.copyfile(src, dst)
    except Exception as exc:  # pragma: no cover - defensive
        # Never fail the build because of this helper, just show the warning
        print(f"Warning: failed to create *t* suffixed Python import library: {exc}")


def _strip_unneeded_symbols() -> None:
    try:
        print("Stripping unneeded symbols from binaries...")
        for so in itertools.chain(Path("nautilus_trader").rglob("*.so")):
            if IS_LINUX:
                strip_cmd = ["strip", "--strip-unneeded", so]
            elif IS_MACOS:
                strip_cmd = ["strip", "-x", so]
            else:
                raise RuntimeError(f"Cannot strip symbols for platform {platform.system()}")
            subprocess.run(
                strip_cmd,  # type: ignore [arg-type]
                check=True,
                capture_output=True,
            )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Error when stripping symbols.\n{e}") from e


def show_rustanalyzer_settings() -> None:
    """
    Show appropriate vscode settings for the build.
    """
    import json

    # Set environment variables
    settings: dict[str, object] = {}
    for key in [
        "rust-analyzer.check.extraEnv",
        "rust-analyzer.runnables.extraEnv",
        "rust-analyzer.cargo.features",
    ]:
        settings[key] = {
            "CC": os.environ["CC"],
            "CXX": os.environ["CXX"],
            "VIRTUAL_ENV": os.environ["VIRTUAL_ENV"],
        }

    # Set features
    features = _set_feature_flags()
    if features[0] == "--all-features":
        settings["rust-analyzer.cargo.features"] = "all"
        settings["rust-analyzer.check.features"] = "all"
    else:
        settings["rust-analyzer.cargo.features"] = features[1].split(",")
        settings["rust-analyzer.check.features"] = features[1].split(",")

    print("Set these rust analyzer settings in .vscode/settings.json")
    print(json.dumps(settings, indent=2))


def build() -> None:
    """
    Construct the extensions and distribution.
    """
    _ensure_windows_python_import_lib()
    _generate_extended_bar_cython_files()
    _build_rust_libs()
    _copy_rust_dylibs_to_project()

    if not PYO3_ONLY:
        # Create C Extensions to feed into cythonize()
        extensions = _build_extensions()
        distribution = _build_distribution(extensions)

        # Build and run the command
        print("Compiling C extension modules...")
        cmd: build_ext = build_ext(distribution)
        if PARALLEL_BUILD:
            cmd.parallel = os.cpu_count()
        cmd.ensure_finalized()
        cmd.run()

        if COPY_TO_SOURCE:
            # Copy the build back into the source tree for development and wheel packaging
            _copy_build_dir_to_project(cmd)

    if BUILD_MODE == "release" and (IS_LINUX or IS_MACOS):
        # Only strip symbols for release builds
        _strip_unneeded_symbols()


def print_env_var_if_exists(key: str) -> None:
    value = os.environ.get(key)
    if value is not None:
        print(f"{key}={value}")


if __name__ == "__main__":
    print("\033[36m")
    print("=====================================================================")
    print(f"Nautilus Builder {_get_nautilus_version()}")
    print("=====================================================================\033[0m")
    print(f"System: {platform.system()} {platform.machine()}")
    print(f"Clang:  {_get_clang_version()}")
    print(f"Rust:   {_get_rustc_version()}")
    print(f"Python: {platform.python_version()} ({sys.executable})")
    print(f"Cython: {cython_compiler_version}")
    print(f"NumPy:  {np.__version__}")

    print(f"\nRUSTUP_TOOLCHAIN={RUSTUP_TOOLCHAIN}")
    print(f"BUILD_MODE={BUILD_MODE}")
    print(f"BUILD_DIR={BUILD_DIR}")
    print(f"HIGH_PRECISION={HIGH_PRECISION}")
    print(f"PROFILE_MODE={PROFILE_MODE}")
    print(f"ANNOTATION_MODE={ANNOTATION_MODE}")
    print(f"PARALLEL_BUILD={PARALLEL_BUILD}")
    print(f"COPY_TO_SOURCE={COPY_TO_SOURCE}")
    print(f"PYO3_ONLY={PYO3_ONLY}")
    print_env_var_if_exists("CC")
    print_env_var_if_exists("CXX")
    print_env_var_if_exists("LDSHARED")
    print_env_var_if_exists("CFLAGS")
    print_env_var_if_exists("LDFLAGS")
    print_env_var_if_exists("LD_LIBRARY_PATH")
    print_env_var_if_exists("PYO3_PYTHON")
    print_env_var_if_exists("PYTHONHOME")
    print_env_var_if_exists("RUSTFLAGS")
    print_env_var_if_exists("DRY_RUN")

    if DRY_RUN:
        show_rustanalyzer_settings()
    else:
        print("\nStarting build...")
        ts_start = dt.datetime.now(dt.UTC)
        build()
        print(f"Build time: {dt.datetime.now(dt.UTC) - ts_start}")
        print("\033[32m" + "Build completed" + "\033[0m")
