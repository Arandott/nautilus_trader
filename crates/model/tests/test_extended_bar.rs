#[cfg(all(test, feature = "extended_bar"))]
mod tests {
    use std::{num::NonZeroUsize, str::FromStr};

    use nautilus_core::UnixNanos;
    use nautilus_model::data::bar::{Bar, BarSpecification, BarType};
    use nautilus_model::data::extended_bar;
    use nautilus_model::enums::{AggregationSource, BarAggregation, PriceType};
    use nautilus_model::identifiers::InstrumentId;
    use nautilus_model::types::{Price, Quantity};
    fn make_bar_type() -> BarType {
        let instrument_id = InstrumentId::from_str("BTCUSDT.BINANCE").unwrap();
        let bar_spec = BarSpecification {
            step: NonZeroUsize::new(1).unwrap(),
            aggregation: BarAggregation::Minute,
            price_type: PriceType::Last,
        };
        BarType::Standard {
            instrument_id,
            spec: bar_spec,
            aggregation_source: AggregationSource::External,
        }
    }

    fn base_prices() -> (Price, Price, Price, Price, Quantity) {
        (
            Price::from_str("50000.00").unwrap(),
            Price::from_str("50100.00").unwrap(),
            Price::from_str("49900.00").unwrap(),
            Price::from_str("50050.00").unwrap(),
            Quantity::from_str("100.0").unwrap(),
        )
    }

    #[test]
    fn new_checked_accepts_extended_fields() {
        let bar_type = make_bar_type();
        let (open, high, low, close, volume) = base_prices();
        let amt = Quantity::from_str("123456.78").unwrap();

        let bar = Bar::new_checked(
            bar_type,
            open,
            high,
            low,
            close,
            volume,
            UnixNanos::from(1_000_000_000u64),
            UnixNanos::from(1_000_000_500u64),
            amt,
        )
        .expect("bar should construct with explicit extended fields");

        assert_eq!(bar.amt, amt);
    }

    #[test]
    fn new_provides_default_extended_values() {
        let bar_type = make_bar_type();
        let (open, high, low, close, volume) = base_prices();

        let bar = nautilus_model::bar_new_with_defaults!(
            bar_type, open, high, low, close, volume, UnixNanos::from(1), UnixNanos::from(2),
        );

        let specs = extended_bar::field_specs();
        assert!(!specs.is_empty(), "extended field specs must not be empty");
        let amt_spec = specs
            .iter()
            .find(|spec| spec.ident == "amt")
            .expect("amt field should be configured");

        let expected = Quantity::from_str(amt_spec.default).unwrap();
        assert_eq!(bar.amt, expected);
    }

    #[test]
    fn extended_fields_participate_in_equality_and_serde() {
        let bar_type = make_bar_type();
        let (open, high, low, close, volume) = base_prices();
        let amt = Quantity::from_str("98765.4321").unwrap();

        let mut bar = nautilus_model::bar_new_with_defaults!(
            bar_type, open, high, low, close, volume, UnixNanos::from(10), UnixNanos::from(20),
        );
        bar.amt = amt;

        let json = serde_json::to_string(&bar).expect("serialize bar");
        let decoded: Bar = serde_json::from_str(&json).expect("deserialize bar");

        assert_eq!(decoded.amt, amt);
        assert_eq!(decoded, bar);
    }
}
