"""
Created 02-03-26
Updated to use Camoufox
@author: Tom Osborne
"""

from camoufox.sync_api import Camoufox
from bs4 import BeautifulSoup
from Tariff import Tariff
import time
from datetime import datetime
import re
from typing import List
import re

class ScrapeTariff:

    def __init__(self):
        self.soup = None
        self.tariff = None
        self.browser = None
        self.page = None

    def scrape(self,
               postcode: str,
               address_index: int = 0,
               fuel_type: str = 'both',
               current_supplier: str = '',
               pay_method: str = 'monthly_direct_debit',
               has_ev: str = 'No',
               email: str = '') -> List[Tariff]:

        url = "https://www.moneysupermarket.com/gas-and-electricity/"

        print(f"-- Starting scrape for {postcode} --")

        try:
            # Use Camoufox with humanized settings
            print("Launching Camoufox browser...")
            with Camoufox(
                    headless=False,
                    humanize=False,  # Try disabling humanize
            ) as browser:
                self.browser = browser
                self.page = browser.new_page()

                # Set headers to request uncompressed content
                self.page.set_extra_http_headers({
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Encoding': 'identity',  # Request uncompressed
                    'Accept-Language': 'en-GB,en;q=0.9',
                })

                print("Loading page...")
                self.page.goto(url, wait_until='load')
                time.sleep(5)

                print(f"Page title: {self.page.title()}")

                # DEBUG: Save what we're seeing
                with open("debug_page.html", "w", encoding="utf-8") as f:
                    f.write(self.page.content())
                print("Saved page content to debug_page.html")

                # Take screenshot
                self.page.screenshot(path="debug_screenshot.png")
                print("Saved screenshot to debug_screenshot.png")

                print(f"Page title: {self.page.title()}")
                print(f"URL: {self.page.url}")

                # Check JavaScript is working
                try:
                    js_test = self.page.evaluate("() => true")
                    print(f"JavaScript enabled: {js_test}")
                except Exception as e:
                    print(f"⚠️  JavaScript error: {e}")

                # Check for Cloudflare or encoding issues
                page_content = self.page.content()

                # Check if we got garbled content
                if page_content[:100].count('�') > 5 or page_content[:100].count('\\x') > 5:
                    print("⚠️  Garbled content detected - trying reload...")
                    self.page.reload(wait_until='networkidle')
                    time.sleep(3)
                    page_content = self.page.content()

                if "cloudflare" in page_content.lower() or "verify you are human" in page_content.lower():
                    print("⚠️  Cloudflare detected - waiting for auto-resolution...")
                    time.sleep(10)

                # STEP 0: Handle cookies and start quote button
                self._step0_cookies_and_start()

                # STEP 1: Enter email
                self._step1_enter_email()

                # STEP 2: Postcode and address
                self._step2_postcode_and_address(postcode, address_index)

                # STEP 3: Home or Business (optional)
                self._step3_home_or_business()

                # STEP 4: Select fuel type
                self._step4_select_fuel_type(fuel_type)

                # STEP 5: Select EV option
                self._step5_select_ev(has_ev)

                # STEP 6: See results
                self._step6_see_results()

                # Wait for results
                print("Waiting for results...")
                time.sleep(5)

                # Get results HTML
                html = self.page.content()
                self.soup = BeautifulSoup(html, 'lxml')

                # Save for debugging
                with open('results_page.html', 'w', encoding='utf-8') as f:
                    f.write(self.soup.prettify())
                print("💾 Saved results to 'results_page.html'")

                # Extract tariff data for all result cards
                self.tariff = self._extract_tariff_data()

                # Persist each tariff to the database
                for t in self.tariff:
                    try:
                        t.save(current_supplier, pay_method, has_ev)
                    except Exception as db_err:
                        print(f"⚠ Failed to save tariff '{t.new_supplier_name} - {t.tariff_name}': {db_err}")

                return self.tariff

        except Exception as e:
            print(f"❌ Error: {e}")
            if self.page:
                self.page.screenshot(path='error_screenshot.png')
                with open('error_page.html', 'w', encoding='utf-8') as f:
                    f.write(self.page.content())
                print("📸 Saved error screenshot and HTML")
            raise

        finally:
            print("Browser closed")

    def _step0_cookies_and_start(self):
        """STEP 0: Handle cookie banner and click 'Start a quote' button"""

        print("\n--- STEP 0: Cookies & Start Quote ---")

        try:
            # 1. HANDLE COOKIES
            cookie_button_selectors = [
                "#onetrust-accept-btn-handler",
                "button:has-text('Accept')",
                "button:has-text('accept')",
                "button[class*='accept']",
                "#onetrust-reject-all-handler",
                "button:has-text('Reject')",
                "button:has-text('reject')",
                "button[class*='reject']",
                "button:has-text('Close')",
                "button:has-text('Dismiss')"
            ]

            cookie_handled = False
            for selector in cookie_button_selectors:
                try:
                    cookie_btn = self.page.locator(selector).first
                    if cookie_btn.is_visible(timeout=2000):
                        cookie_btn.click()
                        print(f"✓ Clicked cookie button using: {selector}")
                        cookie_handled = True
                        time.sleep(2)
                        break
                except:
                    continue

            if not cookie_handled:
                print("⚠ No cookie banner found (or already dismissed)")

            # DEBUG: Let's see what's actually on the page
            print("\n--- DEBUG: Checking page state ---")
            print(f"Current URL: {self.page.url}")

            # Wait a bit for page to fully load
            time.sleep(2)

            # Check for various CTA buttons
            all_cta_buttons = self.page.locator("a[class*='cta']").count()
            print(f"Found {all_cta_buttons} elements with 'cta' in class")

            all_links_with_quote = self.page.locator("a:has-text('quote')").count()
            print(f"Found {all_links_with_quote} links containing 'quote'")

            # Try to get the actual HTML of CTA buttons
            try:
                cta_elements = self.page.locator("a[class*='cta']").all()
                for i, elem in enumerate(cta_elements[:3]):  # Just first 3
                    try:
                        html = elem.evaluate("el => el.outerHTML")
                        print(f"\nCTA Element {i + 1}:")
                        print(html[:200])  # First 200 chars
                    except:
                        pass
            except:
                pass

            # 2. CLICK "START A QUOTE" BUTTON
            start_quote_selectors = [
                "a.cta-button.cta-button--primary-mega",
                "a[class*='cta-button--primary-mega']",
                "a[class*='cta-button'][class*='primary']",
                "a:has-text('Start a quote')",
                "a:has-text('Start quote')",
                "button:has-text('Start a quote')",
                "button:has-text('Start quote')",
                "a[class*='cta']",
            ]

            quote_started = False
            for selector in start_quote_selectors:
                try:
                    print(f"Trying selector: {selector}")
                    start_btn = self.page.locator(selector).first
                    if start_btn.is_visible(timeout=3000):
                        start_btn.scroll_into_view_if_needed()
                        time.sleep(1)

                        try:
                            start_btn.click(timeout=5000)
                        except:
                            print(f"  Regular click failed, trying force click...")
                            start_btn.click(force=True)

                        print(f"✓ Clicked 'Start a quote' using: {selector}")
                        quote_started = True
                        time.sleep(3)
                        break
                except Exception as e:
                    print(f"  Failed: {type(e).__name__}")
                    continue

            if not quote_started:
                print("\n✗ Failed to find 'Start a quote' button")
                print("Taking screenshot for debugging...")
                self.page.screenshot(path="debug_no_start_button.png")

                # Also save the full HTML
                html_content = self.page.content()
                with open("debug_page_content.html", "w", encoding="utf-8") as f:
                    f.write(html_content)
                print("✓ Saved debug_no_start_button.png and debug_page_content.html")

                # Don't raise error - maybe we're already on the form
                print("⚠ Could not find 'Start a quote' button - may already be on form")

        except Exception as e:
            print(f"✗ Error in step 0: {str(e)}")
            raise

    def _step1_enter_email(self):
        """STEP 1: Enter randomly generated email address"""

        print("\n--- STEP 1: Enter Email ---")

        try:
            # Generate random email
            import random
            import string

            random_string = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
            random_email = f"user{random_string}@example.com"

            print(f"Generated email: {random_email}")

            # Wait for email input to be visible
            time.sleep(2)

            # Try different selectors for email input
            email_selectors = [
                "input[type='email']",
                "input[name*='email']",
                "input[id*='email']",
                "input[placeholder*='email']",
                "input[placeholder*='Email']",
                "input[name='email']",
                "input#email",
            ]

            email_entered = False
            for selector in email_selectors:
                try:
                    email_input = self.page.locator(selector).first
                    if email_input.is_visible(timeout=3000):
                        email_input.scroll_into_view_if_needed()
                        time.sleep(0.5)

                        # Clear any existing text and enter email
                        email_input.click()
                        email_input.fill(random_email)

                        print(f"✓ Entered email using: {selector}")
                        email_entered = True
                        time.sleep(1)
                        break
                except Exception as e:
                    continue

            if not email_entered:
                print("✗ Failed to find email input field")
                self.page.screenshot(path="debug_no_email_field.png")
                raise Exception("Could not locate email input field")

            # Now click submit/continue button
            submit_selectors = [
                "button[type='submit']",
                "button:has-text('Continue')",
                "button:has-text('Next')",
                "button:has-text('Get quotes')",
                "button:has-text('Submit')",
                "input[type='submit']",
                "button[class*='submit']",
                "button[class*='continue']",
                "a:has-text('Continue')",
            ]

            submitted = False
            for selector in submit_selectors:
                try:
                    submit_btn = self.page.locator(selector).first
                    if submit_btn.is_visible(timeout=2000):
                        submit_btn.scroll_into_view_if_needed()
                        time.sleep(0.5)
                        submit_btn.click()
                        print(f"✓ Clicked submit using: {selector}")
                        submitted = True
                        time.sleep(3)
                        break
                except:
                    continue

            if not submitted:
                print("⚠ Could not find submit button - may need to press Enter")
                # Try pressing Enter on the email field
                try:
                    email_input = self.page.locator("input[type='email']").first
                    email_input.press("Enter")
                    print("✓ Pressed Enter on email field")
                    time.sleep(3)
                except:
                    print("✗ Failed to submit form")
                    self.page.screenshot(path="debug_no_submit.png")

            print(f"✓ Step 1 complete - email entered: {random_email}")

        except Exception as e:
            print(f"✗ Error in step 1: {str(e)}")
            raise

    def _step2_postcode_and_address(self, postcode: str, address_index: int):
        """STEP 2: Enter postcode and select address"""

        print("\n--- STEP 2: Postcode & Address ---")

        try:
            # Find and fill postcode input
            postcode_input = None
            selectors = [
                "#postcode",
                "input[name='postcode']",
                "input[name*='postcode']",
                "input[id*='postcode']",
                "input[placeholder*='postcode' i]",
                "input[type='text']"
            ]

            for selector in selectors:
                try:
                    postcode_input = self.page.locator(selector).first
                    if postcode_input.is_visible(timeout=5000):
                        print(f"✓ Found postcode input using: {selector}")
                        break
                except:
                    continue

            if not postcode_input:
                raise Exception("Could not find postcode input field")

            # Type slowly like a human
            postcode_input.clear()
            postcode_input.type(postcode, delay=100)  # 100ms delay between keystrokes

            print(f"✓ Entered postcode: {postcode}")

            # Submit postcode
            time.sleep(1)
            try:
                postcode_input.press("Enter")
                print("✓ Submitted postcode (Enter key)")
            except:
                try:
                    submit_btn = self.page.locator(
                        "button[type='submit'], button:has-text('Continue'), button:has-text('Next'), button:has-text('Find')"
                    ).first
                    submit_btn.click()
                    print("✓ Submitted postcode (button click)")
                except:
                    print("⚠ Could not submit - trying to continue anyway")

            # Wait for address dropdown to appear
            time.sleep(3)

            # Select address from dropdown - try multiple selectors
            address_selected = False
            dropdown_selectors = [
                "#address",
                "select[name*='address']",
                "select[id*='address']",
                "select[class*='address']",
                "select",  # Generic select as fallback
            ]

            for selector in dropdown_selectors:
                try:
                    address_dropdown = self.page.locator(selector).first
                    if address_dropdown.is_visible(timeout=5000):
                        print(f"✓ Found address dropdown using: {selector}")

                        # Scroll into view
                        address_dropdown.scroll_into_view_if_needed()
                        time.sleep(0.5)

                        # Get available addresses
                        options = address_dropdown.locator("option").all()
                        print(f"✓ Found {len(options)} address options:")

                        # Display first few options
                        for i, option in enumerate(options[:5]):
                            text = option.text_content()
                            print(f"  {i}: {text[:60]}")

                        # Check if first option is placeholder
                        first_option_text = options[0].text_content().lower()
                        is_placeholder = any(word in first_option_text for word in ['select', 'choose', 'please', '--'])

                        if is_placeholder:
                            # Skip placeholder, select address_index + 1
                            actual_index = address_index + 1
                            if len(options) > actual_index:
                                address_dropdown.select_option(index=actual_index)
                                selected_text = options[actual_index].text_content()
                                print(
                                    f"✓ Selected address {address_index} (actual index {actual_index}, skipped placeholder): {selected_text[:60]}")
                                address_selected = True
                            else:
                                print(f"⚠ Not enough addresses (found {len(options)}, need {actual_index + 1})")
                        else:
                            # No placeholder, select directly
                            if len(options) > address_index:
                                address_dropdown.select_option(index=address_index)
                                selected_text = options[address_index].text_content()
                                print(f"✓ Selected address {address_index}: {selected_text[:60]}")
                                address_selected = True
                            else:
                                print(f"⚠ Not enough addresses (found {len(options)}, need {address_index + 1})")

                        if address_selected:
                            time.sleep(1)
                            break

                except Exception as e:
                    print(f"  Failed with {selector}: {type(e).__name__}")
                    continue

            if not address_selected:
                print("✗ Failed to select address")
                self.page.screenshot(path='step2_address_error.png')
                with open("step2_address_page.html", "w", encoding="utf-8") as f:
                    f.write(self.page.content())
                print("Saved debug files: step2_address_error.png and step2_address_page.html")
                raise Exception("Could not select address from dropdown")

            # Submit address selection
            time.sleep(1)
            continue_clicked = False
            continue_selectors = [
                "button:has-text('Continue')",
                "button:has-text('Next')",
                "button[type='submit']",
                "button:has-text('Proceed')",
                "input[type='submit']",
            ]

            for selector in continue_selectors:
                try:
                    continue_btn = self.page.locator(selector).first
                    if continue_btn.is_visible(timeout=2000):
                        continue_btn.scroll_into_view_if_needed()
                        time.sleep(0.5)
                        continue_btn.click()
                        print(f"✓ Clicked continue button using: {selector}")
                        continue_clicked = True
                        break
                except:
                    continue

            if not continue_clicked:
                print("⚠ No continue button found after address - may auto-submit")

            time.sleep(3)
            print("✓ Step 2 complete")

        except Exception as e:
            print(f"✗ Error in Step 2: {e}")
            self.page.screenshot(path='step2_error.png')
            raise

    def _step3_home_or_business(self):
        """STEP 3: Select 'Home' if business/home choice appears (optional step)"""

        print("\n--- STEP 3: Home or Business (Optional) ---")

        try:
            # Wait a moment for page to load
            time.sleep(2)

            # Try to find home/business buttons
            home_selectors = [
                "button:has-text('Home')",
                "button:has-text('home')",
                "a:has-text('Home')",
                "label:has-text('Home')",
                "input[value='home']",
                "input[value='Home']",
                "button[data-value='home']",
                "div:has-text('Home')",
            ]

            home_found = False
            for selector in home_selectors:
                try:
                    home_btn = self.page.locator(selector).first
                    if home_btn.is_visible(timeout=2000):
                        home_btn.scroll_into_view_if_needed()
                        time.sleep(0.5)
                        home_btn.click()
                        print(f"✓ Selected 'Home' using: {selector}")
                        home_found = True
                        time.sleep(2)
                        break
                except:
                    continue

            if not home_found:
                print("⚠ No Home/Business selection found - skipping this step")

        except Exception as e:
            print(f"⚠ Error in step 3 (non-critical): {str(e)}")
            # Don't raise - this step is optional

    def _step4_select_fuel_type(self, fuel_type: str):
        """STEP 4: Select fuel type (Gas, Gas & Electricity, or Electricity)"""

        print("\n--- STEP 4: Select Fuel Type ---")

        try:
            # Wait for fuel type options to appear
            time.sleep(2)

            # Map fuel_type parameter to button text
            fuel_type_map = {
                'gas': ['Gas', 'gas', 'Gas only'],
                'both': ['Gas & Electricity', 'Gas and Electricity', 'Both', 'Dual fuel', 'Gas & Electric'],
                'electricity': ['Electricity', 'electricity', 'Electric', 'Electricity only', 'Electric only'],
            }

            # Get the list of possible button texts for this fuel type
            if fuel_type.lower() not in fuel_type_map:
                print(f"⚠ Invalid fuel_type: {fuel_type}. Using 'both' as default.")
                fuel_type = 'both'

            possible_texts = fuel_type_map[fuel_type.lower()]
            print(f"Looking for fuel type: {fuel_type} (possible texts: {possible_texts})")

            # Try to find and click the appropriate button
            fuel_selected = False

            for text in possible_texts:
                if fuel_selected:
                    break

                # Try different element types
                selectors = [
                    f"button:has-text('{text}')",
                    f"a:has-text('{text}')",
                    f"label:has-text('{text}')",
                    f"div[role='button']:has-text('{text}')",
                    f"input[value='{text}']",
                ]

                for selector in selectors:
                    try:
                        fuel_btn = self.page.locator(selector).first
                        if fuel_btn.is_visible(timeout=2000):
                            fuel_btn.scroll_into_view_if_needed()
                            time.sleep(0.5)

                            # Click the button/label
                            fuel_btn.click()
                            print(f"✓ Selected fuel type '{text}' using: {selector}")
                            fuel_selected = True
                            time.sleep(2)
                            break
                    except:
                        continue

            if not fuel_selected:
                print("✗ Failed to find fuel type selection")
                self.page.screenshot(path='step4_fuel_type_error.png')
                with open("step4_fuel_page.html", "w", encoding="utf-8") as f:
                    f.write(self.page.content())
                print("Saved debug files: step4_fuel_type_error.png and step4_fuel_page.html")
                raise Exception(f"Could not find fuel type option for: {fuel_type}")

            # Look for continue button
            time.sleep(1)
            continue_selectors = [
                "button:has-text('Continue')",
                "button:has-text('Next')",
                "button[type='submit']",
                "input[type='submit']",
            ]

            for selector in continue_selectors:
                try:
                    continue_btn = self.page.locator(selector).first
                    if continue_btn.is_visible(timeout=2000):
                        continue_btn.scroll_into_view_if_needed()
                        time.sleep(0.5)
                        continue_btn.click()
                        print(f"✓ Clicked continue button")
                        break
                except:
                    continue

            time.sleep(3)
            print("✓ Step 4 complete")

        except Exception as e:
            print(f"✗ Error in Step 4: {str(e)}")
            self.page.screenshot(path='step4_error.png')
            raise

    def _step5_select_ev(self, has_ev: str):
        """STEP 5: Select EV (electric vehicle) option"""

        print("\n--- STEP 5: Select EV Option ---")

        try:
            # Wait for EV options to appear
            time.sleep(2)

            # Determine which option to select based on has_ev parameter
            # Normalize the input to handle variations
            ev_question_lower = has_ev.lower().strip()
            
            # Determine which option to select based on EV_question parameter
            if ev_question_lower in ['yes', 'y']:
                ev_options = ['Yes', 'yes', 'I have an EV', 'I have an electric vehicle']
                print("Selecting: Yes (has EV)")
            elif ev_question_lower in ['no but interested', 'no but considering', 'interested', 'considering']:
                ev_options = ['No, but considering', 'No but considering', 'Considering', 'Maybe',
                              'Planning to get one', 'No but interested']
                print("Selecting: No, but interested")
            else:  # Default to "No"
                ev_options = ['No', 'no', 'I don\'t have an EV', 'I do not have an EV']
                print("Selecting: No")

            # Try to find and click the appropriate option
            ev_selected = False

            for text in ev_options:
                if ev_selected:
                    break

                # Try different element types
                selectors = [
                    f"button:has-text('{text}')",
                    f"a:has-text('{text}')",
                    f"label:has-text('{text}')",
                    f"div[role='button']:has-text('{text}')",
                    f"input[value*='{text}' i]",
                    f"label:text-is('{text}')",
                ]

                for selector in selectors:
                    try:
                        ev_btn = self.page.locator(selector).first
                        if ev_btn.is_visible(timeout=2000):
                            ev_btn.scroll_into_view_if_needed()
                            time.sleep(0.5)

                            # Click the button/label
                            ev_btn.click()
                            print(f"✓ Selected EV option '{text}' using: {selector}")
                            ev_selected = True
                            time.sleep(2)
                            break
                    except:
                        continue

            # If still not selected, try a simpler "No" option as last resort
            if not ev_selected and not has_ev:
                no_options = ['No', 'no', 'I don\'t have an EV']
                print("Trying simple 'No' option as fallback...")

                for text in no_options:
                    selectors = [
                        f"button:has-text('{text}')",
                        f"label:has-text('{text}')",
                    ]

                    for selector in selectors:
                        try:
                            no_btn = self.page.locator(selector).first
                            if no_btn.is_visible(timeout=2000):
                                no_btn.scroll_into_view_if_needed()
                                time.sleep(0.5)
                                no_btn.click()
                                print(f"✓ Selected '{text}' as fallback")
                                ev_selected = True
                                time.sleep(2)
                                break
                        except:
                            continue
                    if ev_selected:
                        break

            if not ev_selected:
                print("⚠ Failed to find EV selection - may be optional")
                self.page.screenshot(path='step5_ev_error.png')
                # Don't raise error - EV question might be optional
                print("⚠ Continuing without EV selection")
                return

            # Look for continue button
            time.sleep(1)
            continue_selectors = [
                "button:has-text('Continue')",
                "button:has-text('Next')",
                "button[type='submit']",
                "input[type='submit']",
                "button:has-text('Get quotes')",
                "button:has-text('Show results')",
            ]

            continue_clicked = False
            for selector in continue_selectors:
                try:
                    continue_btn = self.page.locator(selector).first
                    if continue_btn.is_visible(timeout=2000):
                        continue_btn.scroll_into_view_if_needed()
                        time.sleep(0.5)
                        continue_btn.click()
                        print(f"✓ Clicked continue button")
                        continue_clicked = True
                        break
                except:
                    continue

            if not continue_clicked:
                print("⚠ No continue button found - may auto-proceed")

            time.sleep(3)
            print("✓ Step 5 complete")

        except Exception as e:
            print(f"⚠ Error in Step 5 (non-critical): {str(e)}")
            # Don't raise - this might be optional
            print("Continuing to next step...")

    def _step6_see_results(self):
        """STEP 6: See quote results by selecting button"""

        print("\n--- STEP 6: See results ---")

        try:
            # 1. HANDLE COOKIES
            results_button_selectors = [
                "#onetrust-results-btn-handler",
                "button:has-text('See results')",
                "button:has-text('results')",
                "button[class*='reslts']"
            ]

            results_handled = False
            for selector in results_button_selectors:
                try:
                    results_btn = self.page.locator(selector).first
                    if results_btn.is_visible(timeout=2000):
                        results_btn.click()
                        print(f"✓ Clicked results button using: {selector}")
                        results_handled = True
                        time.sleep(2)
                        break
                except:
                    continue

            if not results_handled:
                print("⚠ No cookie banner found (or already dismissed)")

        except Exception as e:
            print(f"✗ Error in step 6: {str(e)}")
            raise


    def _extract_tariff_data(self) -> List[Tariff]:
        """Extract tariff data for all tariff result cards on the page."""

        cards = self.soup.select(".results-new-item")
        if not cards:
            raise Exception("Could not find any tariff result cards in results_page.html")

        def build_tariff_from_card(card) -> Tariff:
            # Helper: get text within this card
            def get_card_text(selector: str, default: str = "") -> str:
                        # Extract annual usage from the page-level usage section
                annual_electricity_kwh = 0
                annual_gas_kwh = 0
                
                usage_overview = self.soup.select_one(".current-usage-overview")
                if usage_overview:
                    fuel_sections = usage_overview.select(".current-usage-overview__fuel")
                    for fuel_section in fuel_sections:
                        fuel_type_el = fuel_section.select_one(".current-usage-overview__consumption__type")
                        consumption_el = fuel_section.select_one(".current-usage-overview__consumption")
                        
                        if fuel_type_el and consumption_el:
                            fuel_type_text = fuel_type_el.get_text(strip=True).lower()
                            consumption_text = consumption_el.get_text(strip=True)
                            
                            # Extract number from "7974 kWh / year" format
                            match = re.search(r"([\d,]+)\s*kwh", consumption_text, re.IGNORECASE)
                            if match:
                                try:
                                    value = int(match.group(1).replace(",", ""))
                                    if "gas" in fuel_type_text:
                                        annual_gas_kwh = value
                                    elif "electric" in fuel_type_text:
                                        annual_electricity_kwh = value
                                except ValueError:
                                    pass
                el = card.select_one(selector)
                return el.get_text(strip=True) if el else default

            # --- Supplier & tariff names ---
            new_supplier_name = get_card_text(
                ".results-new-item-brand__provider-name", "Unknown Supplier"
            )
            tariff_name = get_card_text(
                ".results-new-item-brand__tariff-name", "Unknown Tariff"
            )

            # --- Tariff type & fixed length ---
            fixed_price_length_months = 0
            tariff_type = "Unknown"

            rate_label_el = card.select_one(".results-new-item-rate-type__label")
            rate_value_el = card.select_one(".results-new-item-rate-type__value")

            rate_label_text = (
                rate_label_el.get_text(strip=True).lower() if rate_label_el else ""
            )
            rate_value_text = (
                rate_value_el.get_text(" ", strip=True).lower() if rate_value_el else ""
            )

            if "fixed" in rate_label_text or "fixed" in rate_value_text:
                tariff_type = "Fixed"
            elif "variable" in rate_label_text or "variable" in rate_value_text:
                tariff_type = "Variable"

            if rate_value_text:
                m = re.search(r"(\d+)", rate_value_text)
                if m:
                    try:
                        fixed_price_length_months = int(m.group(1))
                    except ValueError:
                        fixed_price_length_months = 0

            # --- Payment method (from strapline if available) ---
            pay_method = "Unknown"
            strapline_el = card.find_next("div", class_="results-new-item-strapline")
            strapline_text = (
                strapline_el.get_text(" ", strip=True).lower() if strapline_el else ""
            )
            if "direct debit" in strapline_text:
                pay_method = "Direct Debit"

            # --- Exit fee & yearly saving / annual cost ---
            exit_fee = 0.0
            annual_cost_new = 0.0

            # Exit fee lives in the callouts section
            callout_cells = card.select(".results-new-item-callouts__cells__cell")
            for cell in callout_cells:
                label_el = cell.select_one(
                    ".results-new-item-callouts__cells__cell__label"
                )
                if not label_el:
                    continue
                label = label_el.get_text(strip=True).lower()
                if "early exit fee" in label:
                    value_el = cell.select_one(
                        ".results-new-item-callouts__cells__cell__value"
                    )
                    if value_el:
                        text = value_el.get_text(" ", strip=True)
                        cleaned = text.replace("£", "").replace(",", "").strip()
                        try:
                            exit_fee = float(cleaned)
                        except ValueError:
                            exit_fee = 0.0
                    break

            # Annual cost is in the "or £1,234 a year" text
            cost_sub_value = get_card_text(".results-new-item-cost__sub_value", "")
            if cost_sub_value:
                m = re.search(r"£\s*([\d,]+)", cost_sub_value)
                if m:
                    try:
                        annual_cost_new = float(m.group(1).replace(",", ""))
                    except ValueError:
                        annual_cost_new = 0.0

            # --- Unit rate & standing charge (take Electricity column if present) ---
            unit_rate = 0.0
            standing_charge_day = 0.0
            fuel_type = "Unknown"

            table = card.select_one(".results-new-item-charges-breakdown__table")
            if table:
                # Determine fuel type from table headers
                header_cells = table.select("thead tr th")
                header_texts = [h.get_text(strip=True).lower() for h in header_cells]

                has_gas = any("gas" in t for t in header_texts)
                has_elec = any("electric" in t for t in header_texts)

                if has_gas and has_elec:
                    fuel_type = "gas_and_electricity"
                elif has_elec:
                    fuel_type = "electricity"
                elif has_gas:
                    fuel_type = "gas"

                # When both present, the last column is Electricity
                # We read standing charge and unit rate from that column
                rows = table.select("tbody tr")
                for row in rows:
                    header_el = row.select_one("th")
                    if not header_el:
                        continue
                    label = header_el.get_text(strip=True).lower()
                    cells = row.select("td")
                    if not cells:
                        continue

                    # Prefer electricity column = last cell
                    value_el = cells[-1]
                    text = value_el.get_text(" ", strip=True)

                    if "standing charge" in label:
                        m = re.search(r"([\d.]+)", text)
                        if m:
                            try:
                                standing_charge_day = float(m.group(1))
                            except ValueError:
                                standing_charge_day = 0.0
                    elif "unit rate" in label:
                        m = re.search(r"([\d.]+)", text)
                        if m:
                            try:
                                unit_rate = float(m.group(1))
                            except ValueError:
                                unit_rate = 0.0
                        # --- Check if tariff is green/renewable ---
            is_green = False
            # Check for green-electricity-decal within tariff-decals
            decals_section = card.select_one(".tariff-decals")
            if decals_section:
                green_decal = decals_section.select_one(".green-electricity-decal")
                if green_decal:
                    # Check if it contains "Green electricity" text
                    decal_text = green_decal.get_text(strip=True).lower()
                    if "green" in decal_text or "renewable" in decal_text:
                        is_green = True


            # --- Build Tariff object ---
            now = datetime.now()

            tariff = Tariff(
                # Tariff details
                new_supplier_name=new_supplier_name,
                tariff_name=tariff_name,
                tariff_type=tariff_type,
                pay_method=pay_method,
                fixed_price_length_months=fixed_price_length_months,
                is_green=is_green,

                # Location details (not available in markup yet – defaulted)
                region_code=self._get_text(".region-code", ""),
                region_name=self._get_text(".region-name", ""),
                dno_name=self._get_text(".dno-name", ""),
                dno_id=self._get_text(".dno-id", ""),
                postcode=self._get_text(".postcode", ""),
                outward_code=self._get_text(".outward-code", ""),
                latitude=self._get_float(".latitude", 0.0),
                longitude=self._get_float(".longitude", 0.0),

                fuel_type=fuel_type,

                # Search details
                search_date=now,
                month=now.month,
                year=now.year,

                # Cost details
                annual_electricity_kwh=self._get_int(".electricity-kwh", 0),
                annual_gas_kwh=self._get_int(".gas-kwh", 0),
                unit_rate=unit_rate,
                standing_charge_day=standing_charge_day,
                exit_fee=exit_fee,
                annual_cost_current=self._get_float(".cost-current", 0.0),
                annual_cost_new=annual_cost_new,
                valid_from=self._get_datetime(".valid-from"),
                valid_to=self._get_datetime(".valid-to"),
                created_at=now,
                last_updated=now,
            )

            return tariff

        tariffs: List[Tariff] = []
        for idx, card in enumerate(cards):
            try:
                tariffs.append(build_tariff_from_card(card))
            except Exception as e:
                print(f"⚠ Skipping result card {idx} due to error: {e}")

        return tariffs

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
        tariffs = scraper.scrape(
            postcode="N4 2JR",
            address_index=0,  # Select first address
            fuel_type="gas_and_electricity",  # 'gas', 'electricity', or 'gas_and_electricity'
            current_supplier="Octopus",
            pay_method="monthly_direct_debit",
            has_ev="No but interested",
            email="test@example.com",
        )

        print(f"\nFound {len(tariffs)} tariffs\n{'='*50}")
        for i, tariff in enumerate(tariffs, start=1):
            print(f"[{i}] {tariff.new_supplier_name} - {tariff.tariff_name}")
            print(f"    Annual cost: £{tariff.annual_cost_new}")
            print(f"    Unit rate: {tariff.unit_rate}p, Standing charge: {tariff.standing_charge_day}p\n")

        # Example: save all tariffs
        # for t in tariffs:
        #     t.save("Current Supplier", "Direct Debit", False)

    except Exception as e:
        print(f"\n❌ Failed to scrape: {e}")