import ScrapeTariff

if __name__ == "__main__":
    scraper = ScrapeTariff.ScrapeTariff()

    try:
        postcode = input("Enter postcode: ").strip()

        address_index = input("Enter address index [0]: ").strip()
        address_index = int(address_index) if address_index else 0

        fuel_type = input(
            "Fuel type (gas / electricity / gas_and_electricity) "
            "[gas_and_electricity]: "
        ).strip() or "gas_and_electricity"

        current_supplier = input(
            "Current supplier [Octopus]: "
        ).strip() or "Octopus"

        pay_method = input(
            "Payment method [monthly_direct_debit]: "
        ).strip() or "monthly_direct_debit"

        has_ev = input(
            "EV status [No but interested]: "
        ).strip() or "No but interested"

        tariffs = scraper.scrape(
            postcode=postcode,
            address_index=address_index,
            fuel_type=fuel_type,
            current_supplier=current_supplier,
            pay_method=pay_method,
            has_ev=has_ev
        )

        print(f"\nFound {len(tariffs)} tariffs\n{'=' * 50}")
        for i, tariff in enumerate(tariffs, start=1):
            print(f"[{i}] {tariff.new_supplier_name} - {tariff.tariff_name}")
            print(f"    Annual cost: £{tariff.annual_cost_new}")
            print(
                f"    Unit rate: {tariff.unit_rate}p, "
                f"Standing charge: {tariff.standing_charge_day}p\n"
            )

    except Exception as e:
        print(f"❌ Error scraping tariffs: {e}")
