"""
Created 02-03-26
@author: Tom Osborne
"""

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from bs4 import BeautifulSoup
from Tariff import Tariff
import time
from datetime import datetime

class ScrapeTariff:

    def __init__(self):
        self.soup = None
        self.tariff = None
        self.driver = None

    def scrape(self,
               postcode: str,
               address_index: int = 0,
               fuel_type: str = 'both',
               current_supplier: str = '',
               payment_method: str = 'monthly_direct_debit',
               has_ev: bool = False,
               email: str = '') -> Tariff:

        url = "https://www.moneysupermarket.com/gas-and-electricity/"

        print(f"-- Starting scrape for {postcode} --")

        try:
            # Use undetected_chromedriver with version specification
            options = uc.ChromeOptions()
            # options.add_argument('--headless')  # Don't use headless - easier to detect

            # Specify Chrome version to match your browser (144)
            self.driver = uc.Chrome(
                options=options,
                version_main=144  # Match your Chrome version
            )

            # Navigate to the page
            print("Loading page...")
            self.driver.get(url)

            # Add human-like delay
            time.sleep(3)

            print(f"✅ Page loaded: {self.driver.title}")

            # Check for Cloudflare
            if "cloudflare" in self.driver.page_source.lower() or "verify you are human" in self.driver.page_source.lower():
                print("⚠️  Cloudflare detected - waiting for auto-resolution...")
                time.sleep(10)

            # Wait helper
            wait = WebDriverWait(self.driver, 20)

            # STEP 0: Handle cookies and start quote button
            self._step0_cookies_and_start(wait)

            # STEP 1: Enter postcode and select address
            self._step1_postcode_and_address(postcode, address_index, wait)

            # STEP 2: Fill in details
            self._step2_energy_details(fuel_type, current_supplier, payment_method,
                                       has_ev, email, wait)

            # Wait for results
            print("Waiting for results...")
            time.sleep(5)

            # Get results HTML
            html = self.driver.page_source
            self.soup = BeautifulSoup(html, 'lxml')

            # Save for debugging
            with open('results_page.html', 'w', encoding='utf-8') as f:
                f.write(self.soup.prettify())
            print("💾 Saved results to 'results_page.html'")

            # Extract tariff data
            self.tariff = self._extract_tariff_data()

            return self.tariff

        except Exception as e:
            print(f"❌ Error: {e}")
            if self.driver:
                self.driver.save_screenshot('error_screenshot.png')
                with open('error_page.html', 'w', encoding='utf-8') as f:
                    f.write(self.driver.page_source)
                print("📸 Saved error screenshot and HTML")
            raise

        finally:
            if self.driver:
                time.sleep(2)
                self.driver.quit()
                print("Browser closed")

    def _step0_cookies_and_start(self, wait):
        """STEP 0: Handle cookie banner and click 'Start a quote' button"""

        print("\n--- STEP 0: Cookies & Start Quote ---")

        try:
            # 1. HANDLE COOKIES
            # Try to find and click Accept/Reject cookies button
            cookie_button_selectors = [
                # Accept cookies
                (By.ID, "onetrust-accept-btn-handler"),
                (By.XPATH, "//button[contains(text(), 'Accept') or contains(text(), 'accept')]"),
                (By.CSS_SELECTOR, "button[class*='accept']"),
                # Reject cookies
                (By.ID, "onetrust-reject-all-handler"),
                (By.XPATH, "//button[contains(text(), 'Reject') or contains(text(), 'reject')]"),
                (By.CSS_SELECTOR, "button[class*='reject']"),
                # Close/Dismiss
                (By.XPATH, "//button[contains(text(), 'Close') or contains(text(), 'Dismiss')]")
            ]

            cookie_handled = False
            for selector_type, selector_value in cookie_button_selectors:
                try:
                    cookie_btn = wait.until(
                        EC.element_to_be_clickable((selector_type, selector_value))
                    )
                    cookie_btn.click()
                    print(f"✓ Clicked cookie button using: {selector_type}")
                    cookie_handled = True
                    time.sleep(2)
                    break
                except:
                    continue

            if not cookie_handled:
                print("⚠ No cookie banner found (or already dismissed)")

            # 2. CLICK "START A QUOTE" BUTTON
            start_quote_selectors = [
                (By.XPATH, "//button[contains(text(), 'Start a quote') or contains(text(), 'Start quote')]"),
                (By.XPATH, "//a[contains(text(), 'Start a quote') or contains(text(), 'Start quote')]"),
                (By.CSS_SELECTOR, "button[class*='start-quote']"),
                (By.CSS_SELECTOR, "a[class*='start-quote']"),
                (By.XPATH, "//button[contains(@class, 'cta') or contains(@class, 'primary')]"),
                # Try finding by text content more broadly
                (By.XPATH, "//*[contains(text(), 'Start') and contains(text(), 'quote')]")
            ]

            quote_started = False
            for selector_type, selector_value in start_quote_selectors:
                try:
                    start_btn = wait.until(
                        EC.element_to_be_clickable((selector_type, selector_value))
                    )
                    # Scroll to button
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", start_btn)
                    time.sleep(1)

                    start_btn.click()
                    print(f"✓ Clicked 'Start a quote' using: {selector_type}")
                    quote_started = True
                    time.sleep(3)
                    break
                except:
                    continue

            if not quote_started:
                print("⚠ Could not find 'Start a quote' button - may already be on form")

        except Exception as e:
            print(f"⚠ Error in Step 0: {e}")
            print("Attempting to continue anyway...")
            self.driver.save_screenshot('step0_error.png')

    def _step1_postcode_and_address(self, postcode: str, address_index: int, wait):
        """STEP 1: Enter postcode and select address"""

        print("\n--- STEP 1: Postcode & Address ---")

        try:
            # Find and fill postcode input
            postcode_input = None
            selectors = [
                (By.ID, "postcode"),
                (By.NAME, "postcode"),
                (By.CSS_SELECTOR, "input[placeholder*='postcode' i]"),
                (By.CSS_SELECTOR, "input[type='text']"),
                (By.XPATH, "//input[contains(@placeholder, 'postcode') or contains(@name, 'postcode')]")
            ]

            for selector_type, selector_value in selectors:
                try:
                    postcode_input = wait.until(
                        EC.presence_of_element_located((selector_type, selector_value))
                    )
                    print(f"✓ Found postcode input using: {selector_type}")
                    break
                except:
                    continue

            if not postcode_input:
                raise Exception("Could not find postcode input field")

            # Type slowly like a human
            postcode_input.clear()
            for char in postcode:
                postcode_input.send_keys(char)
                time.sleep(0.1)

            print(f"✓ Entered postcode: {postcode}")

            # Submit postcode
            time.sleep(1)
            try:
                postcode_input.send_keys(Keys.RETURN)
                print("✓ Submitted postcode (Enter key)")
            except:
                try:
                    submit_btn = self.driver.find_element(
                        By.XPATH, "//button[@type='submit' or contains(text(), 'Continue') or contains(text(), 'Next') or contains(text(), 'Find')]"
                    )
                    submit_btn.click()
                    print("✓ Submitted postcode (button click)")
                except:
                    print("⚠ Could not submit - trying to continue anyway")

            # Wait for address dropdown
            time.sleep(3)

            # Select address from dropdown
            try:
                address_dropdown = wait.until(
                    EC.presence_of_element_located((By.ID, "address"))
                )

                from selenium.webdriver.support.ui import Select
                select = Select(address_dropdown)

                # Show available addresses
                options = select.options
                print(f"✓ Found {len(options)} addresses:")
                for i, option in enumerate(options[:5]):  # Show first 5
                    print(f"  {i}: {option.text[:60]}")

                # Select the requested address
                select.select_by_index(address_index)
                print(f"✓ Selected address {address_index}: {options[address_index].text[:60]}")

                time.sleep(1)

                # Submit address selection
                try:
                    continue_btn = self.driver.find_element(
                        By.XPATH, "//button[contains(text(), 'Continue') or contains(text(), 'Next')]"
                    )
                    continue_btn.click()
                    print("✓ Submitted address")
                except:
                    print("⚠ No continue button found after address")

            except Exception as e:
                print(f"⚠ Address selection issue: {e}")
                print("Attempting to continue anyway...")

            time.sleep(3)

        except Exception as e:
            print(f"❌ Error in Step 1: {e}")
            self.driver.save_screenshot('step1_error.png')
            raise

    def _step2_energy_details(self, fuel_type: str, current_supplier: str,
                              payment_method: str, has_ev: bool, email: str, wait):
        """STEP 2: Fill in fuel type, supplier, payment, EV, email"""

        print("\n--- STEP 2: Energy Details ---")

        try:
            # 1. FUEL TYPE
            print("Setting fuel type...")
            fuel_selectors = {
                'gas': [
                    (By.ID, "fuel-gas"),
                    (By.CSS_SELECTOR, "input[value='gas']"),
                    (By.XPATH, "//input[@type='radio' and contains(@id, 'gas')]")
                ],
                'electricity': [
                    (By.ID, "fuel-electricity"),
                    (By.CSS_SELECTOR, "input[value='electricity']"),
                    (By.XPATH, "//input[@type='radio' and contains(@id, 'electric')]")
                ],
                'both': [
                    (By.ID, "fuel-both"),
                    (By.CSS_SELECTOR, "input[value='both']"),
                    (By.XPATH, "//input[@type='radio' and contains(@id, 'both')]")
                ]
            }

            fuel_found = False
            for selector_type, selector_value in fuel_selectors.get(fuel_type.lower(), fuel_selectors['both']):
                try:
                    fuel_radio = self.driver.find_element(selector_type, selector_value)
                    fuel_radio.click()
                    print(f"✓ Selected fuel type: {fuel_type}")
                    fuel_found = True
                    break
                except:
                    continue

            if not fuel_found:
                print(f"⚠ Could not find fuel type selector for: {fuel_type}")

            time.sleep(1)

            # 2. CURRENT SUPPLIER
            if current_supplier:
                print("Setting current supplier...")
                try:
                    supplier_dropdown = wait.until(
                        EC.presence_of_element_located((By.ID, "current-supplier"))
                    )
                    from selenium.webdriver.support.ui import Select
                    select = Select(supplier_dropdown)
                    select.select_by_visible_text(current_supplier)
                    print(f"✓ Selected supplier: {current_supplier}")
                except Exception as e:
                    print(f"⚠ Could not set supplier: {e}")

            time.sleep(1)

            # 3. PAYMENT METHOD
            if payment_method:
                print("Setting payment method...")
                payment_selectors = [
                    (By.ID, f"payment-{payment_method}"),
                    (By.CSS_SELECTOR, f"input[value*='{payment_method}']"),
                    (By.XPATH, f"//input[contains(@id, 'payment') and contains(@value, '{payment_method}')]")
                ]

                for selector_type, selector_value in payment_selectors:
                    try:
                        payment_radio = self.driver.find_element(selector_type, selector_value)
                        payment_radio.click()
                        print(f"✓ Selected payment: {payment_method}")
                        break
                    except:
                        continue

            time.sleep(1)

            # 4. ELECTRIC VEHICLE
            print(f"Setting EV status: {has_ev}")
            ev_selectors = [
                (By.ID, "has-ev-yes" if has_ev else "has-ev-no"),
                (By.CSS_SELECTOR, f"input[name='ev'][value='{'yes' if has_ev else 'no'}']"),
                (By.XPATH, f"//input[contains(@name, 'ev') and @value='{'yes' if has_ev else 'no'}']")
            ]

            for selector_type, selector_value in ev_selectors:
                try:
                    ev_radio = self.driver.find_element(selector_type, selector_value)
                    ev_radio.click()
                    print(f"✓ Set EV: {'Yes' if has_ev else 'No'}")
                    break
                except:
                    continue

            time.sleep(1)

            # 5. EMAIL
            if email:
                print("Entering email...")
                email_selectors = [
                    (By.ID, "email"),
                    (By.NAME, "email"),
                    (By.CSS_SELECTOR, "input[type='email']")
                ]

                for selector_type, selector_value in email_selectors:
                    try:
                        email_input = self.driver.find_element(selector_type, selector_value)
                        email_input.clear()
                        # Type slowly like a human
                        for char in email:
                            email_input.send_keys(char)
                            time.sleep(0.05)
                        print(f"✓ Entered email: {email}")
                        break
                    except:
                        continue

            time.sleep(1)

            # 6. SUBMIT FORM
            print("Submitting form...")
            submit_selectors = [
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.XPATH, "//button[contains(text(), 'Compare') or contains(text(), 'Continue') or contains(text(), 'Submit') or contains(text(), 'Get')]"),
                (By.ID, "submit-btn")
            ]

            for selector_type, selector_value in submit_selectors:
                try:
                    submit_btn = self.driver.find_element(selector_type, selector_value)
                    submit_btn.click()
                    print("✓ Clicked submit button")
                    break
                except:
                    continue

        except Exception as e:
            print(f"❌ Error in Step 2: {e}")
            self.driver.save_screenshot('step2_error.png')
            raise

    def _extract_tariff_data(self) -> Tariff:
        """Extract tariff data from the parsed HTML"""

        tariff = Tariff(
            # Tariff details
            new_supplier_name=self._get_text('.supplier-name', 'Unknown Supplier'),
            tariff_name=self._get_text('.tariff-name', 'Unknown Tariff'),
            tariff_type=self._get_text('.tariff-type', 'Unknown'),
            payment_method=self._get_text('.payment-method', 'Unknown'),
            fixed_price_length_months=self._get_int('.fixed-length', 0),
            is_green=self._get_bool('.is-green', False),

            # Location details
            region_code=self._get_text('.region-code', ''),
            region_name=self._get_text('.region-name', ''),
            dno_name=self._get_text('.dno-name', ''),
            dno_id=self._get_text('.dno-id', ''),
            postcode=self._get_text('.postcode', ''),
            outward_code=self._get_text('.outward-code', ''),
            latitude=self._get_float('.latitude', 0.0),
            longitude=self._get_float('.longitude', 0.0),

            fuel_type=self._get_text('.fuel-type', 'Unknown'),

            # Search details
            search_date=datetime.now(),
            month=datetime.now().month,
            year=datetime.now().year,

            # Cost details
            annual_electricity_kwh=self._get_int('.electricity-kwh', 0),
            annual_gas_kwh=self._get_int('.gas-kwh', 0),
            unit_rate=self._get_float('.unit-rate', 0.0),
            standing_charge_day=self._get_float('.standing-charge', 0.0),
            exit_fee=self._get_float('.exit-fee', 0.0),
            annual_cost_current=self._get_float('.cost-current', 0.0),
            annual_cost_new=self._get_float('.cost-new', 0.0),
            valid_from=self._get_datetime('.valid-from'),
            valid_to=self._get_datetime('.valid-to'),
            created_at=datetime.now(),
            last_updated=datetime.now()
        )

        return tariff

    # Helper methods for extracting data
    def _get_text(self, selector: str, default: str = '') -> str:
        """Get text content from CSS selector"""
        element = self.soup.select_one(selector)
        return element.get_text(strip=True) if element else default

    def _get_int(self, selector: str, default: int = 0) -> int:
        """Get integer value from CSS selector"""
        text = self._get_text(selector)
        try:
            return int(text.replace(',', ''))
        except (ValueError, AttributeError):
            return default

    def _get_float(self, selector: str, default: float = 0.0) -> float:
        """Get float value from CSS selector"""
        text = self._get_text(selector)
        try:
            cleaned = text.replace('£', '').replace(',', '').strip()
            return float(cleaned)
        except (ValueError, AttributeError):
            return default

    def _get_bool(self, selector: str, default: bool = False) -> bool:
        """Get boolean value from CSS selector"""
        element = self.soup.select_one(selector)
        if not element:
            return default

        text = element.get_text(strip=True).lower()
        return text in ['true', 'yes', '1', 'green', 'renewable']

    def _get_datetime(self, selector: str) -> datetime:
        """Get datetime value from CSS selector"""
        text = self._get_text(selector)
        try:
            return datetime.strptime(text, '%Y-%m-%d')
        except (ValueError, AttributeError):
            return datetime.now()


# Usage example
if __name__ == "__main__":
    scraper = ScrapeTariff()

    try:
        tariff = scraper.scrape(
            postcode="SW1A 1AA",
            address_index=0,  # Select first address
            fuel_type="both",  # 'gas', 'electricity', or 'both'
            current_supplier="British Gas",
            payment_method="monthly_direct_debit",
            has_ev=False,
            email="test@example.com"
        )

        print(f"\n{'='*50}")
        print(f"Scraped tariff: {tariff.tariff_name}")
        print(f"Supplier: {tariff.new_supplier_name}")
        print(f"Annual cost: £{tariff.annual_cost_new}")
        print(f"{'='*50}")

        # Save to database
        # tariff.save("Current Supplier", "Direct Debit", False)

    except Exception as e:
        print(f"\n❌ Failed to scrape: {e}")