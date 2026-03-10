from src.api.energyScraping import ScrapeTariff

if __name__ == "__main__":
    import sys
    from pathlib import Path
    # Ensure project root is on path so recommend_from_scrape can import src.models
    _project_root = Path(__file__).resolve().parents[3]
    if _project_root.exists() and str(_project_root) not in sys.path:
        sys.path.insert(0, str(_project_root))

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

        # Tariff recommendation using optimisation (solar/wind sizing + cost over 5 years)
        do_recommend = input(
            "Get tariff recommendation with solar/wind optimisation? [y/N]: "
        ).strip().lower() == "y"
        if do_recommend and tariffs:
            try:
                from src.api.energyScraping.recommend_from_scrape import recommend_after_scrape
                rec = recommend_after_scrape(
                    tariffs,
                    annual_consumption_kwh=None,  # use first tariff's annual_electricity_kwh
                    export_price_per_kwh=0.05,
                    optimize_over_years=5.0,
                    prefer_green=False,
                )
                if rec.get("error"):
                    print("Recommendation:", rec["error"])
                else:
                    opt = rec["optimisation_result"]
                    best = rec["recommended_tariff"]
                    print("\n" + "=" * 50)
                    print("TARIFF RECOMMENDATION (with optimal solar/wind)")
                    print("=" * 50)
                    print(f"Optimal system: solar {opt['optimal_solar_kw']} kW, wind {opt['optimal_wind_kw']} kW")
                    print(f"Annual import: {opt['annual_import_kwh']:.0f} kWh  |  export: {opt['annual_export_kwh']:.0f} kWh")
                    print(f"Capex: £{opt['capex']:.0f}")
                    print()
                    print(f"Recommended tariff: {best.get('supplier_name', '')} - {best.get('tariff_name', '')}")
                    print(f"  Unit rate: {best.get('unit_rate_p_per_kwh', 0):.1f}p/kWh  |  Standing charge: {best.get('standing_charge_p_per_day', 0):.1f}p/day")
                    print(f"  Total cost over {rec['optimize_over_years']} years: £{rec['ranking'][0]['total_cost_gbp']:.2f}")
                    print("\nTop 5 tariffs by total cost (capex + grid cost - export over 5 years):")
                    for r in rec["ranking"][:5]:
                        t = r["tariff"]
                        print(f"  {r['rank']}. {t.get('supplier_name', '')} - {t.get('tariff_name', '')}: £{r['total_cost_gbp']:.2f}")
            except Exception as e:
                print(f"Recommendation failed: {e}")

    except Exception as e:
        msg = str(e)
        # Prefer the real error; "Event loop is closed" is a cleanup artifact
        if "Event loop is closed" in msg or "Playwright already stopped" in msg:
            print("❌ Error scraping tariffs: (browser closed after an error — check messages above)")
        else:
            print(f"❌ Error scraping tariffs: {e}")
