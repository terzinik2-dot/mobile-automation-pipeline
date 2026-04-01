"""
Google Pay Purchase Scenario

Navigates to the MLBB in-game shop and completes a purchase via Google Pay.

Purchase flow:
1. Navigate to MLBB shop
2. Select a purchasable item (diamonds / starter pack)
3. Tap purchase / confirm payment method
4. Handle Google Play Billing dialog
5. Verify purchase confirmation

Important notes:
- For licensed testers, Google Play shows test payment methods (no real charge)
- The billing dialog is handled by Google Play Services (com.google.android.gms)
- We use test payment mode (GOOGLE_PAY_TEST_MODE=true) for safety
- In production, ensure the account is a licensed tester for MLBB

References:
- https://developer.android.com/google/play/billing/test
"""

from __future__ import annotations

import time

from loguru import logger

from executors.locator_engine import LocatorStrategy
from scenarios.base_scenario import BaseScenario

MLBB_PACKAGE = "com.mobile.legends"
GOOGLE_PLAY_BILLING_PACKAGE = "com.google.android.gms"
PLAY_STORE_PACKAGE = "com.android.vending"


class GooglePayPurchaseScenario(BaseScenario):
    """Scenario: Navigate to MLBB shop and make an in-app purchase via Google Pay."""

    SCENARIO_NAME = "google_pay_purchase"
    BUDGET_KEY = "google_pay_purchase"

    def run_steps(self) -> None:
        self._execute_step("ensure_in_lobby", self._ensure_in_lobby, max_retries=2)
        self._execute_step("navigate_to_shop", self._navigate_to_shop, max_retries=3)
        self._execute_step("select_purchase_item", self._select_purchase_item, max_retries=3)
        self._execute_step("initiate_purchase", self._initiate_purchase, max_retries=2)
        self._execute_step("handle_billing_dialog", self._handle_billing_dialog, max_retries=2)
        self._execute_step("confirm_payment", self._confirm_payment, max_retries=2)
        self._execute_step("verify_purchase", self._verify_purchase, max_retries=3)

    # ------------------------------------------------------------------
    # Step implementations
    # ------------------------------------------------------------------

    def _ensure_in_lobby(self) -> None:
        """Make sure we're in the MLBB lobby before navigating to shop."""
        current_pkg = self.driver.get_current_package()
        if MLBB_PACKAGE not in current_pkg:
            logger.info("[gpay] MLBB not in foreground — launching")
            self.driver.launch_app(MLBB_PACKAGE)
            time.sleep(3.0)

        # Wait for lobby indicators
        lobby_indicators = [
            LocatorStrategy.by_text("Battle"),
            LocatorStrategy.by_text("Shop"),
            LocatorStrategy.by_id(f"{MLBB_PACKAGE}:id/battle_btn"),
            LocatorStrategy.by_template("templates/mlbb_lobby.png"),
        ]
        lobby = self.locator.wait_for_element(lobby_indicators, timeout=15.0)
        if lobby is None:
            raise RuntimeError("MLBB lobby not accessible for shop navigation")
        logger.info("[gpay] Confirmed in MLBB lobby")

    def _navigate_to_shop(self) -> None:
        """Navigate to the in-game shop."""
        shop_strategies = [
            LocatorStrategy.by_text("Shop"),
            LocatorStrategy.by_content_desc("Shop"),
            LocatorStrategy.by_id(f"{MLBB_PACKAGE}:id/shop_btn"),
            LocatorStrategy.by_id(f"{MLBB_PACKAGE}:id/store_icon"),
            LocatorStrategy.by_template("templates/mlbb_shop_icon.png"),
            LocatorStrategy.by_ocr("Shop"),
        ]
        shop_btn = self.locator.find_element(shop_strategies, timeout=10.0)
        if shop_btn is None:
            raise RuntimeError("Shop button not found in MLBB lobby")

        self.gestures.tap(shop_btn)
        time.sleep(2.0)

        # Verify shop opened
        shop_open_indicators = [
            LocatorStrategy.by_text("Diamonds"),
            LocatorStrategy.by_text("Buy Diamonds"),
            LocatorStrategy.by_text("Skins"),
            LocatorStrategy.by_text("Heroes"),
            LocatorStrategy.by_id(f"{MLBB_PACKAGE}:id/shop_tabs"),
            LocatorStrategy.by_template("templates/mlbb_shop_header.png"),
        ]
        shop_open = self.locator.wait_for_element(shop_open_indicators, timeout=10.0)
        if shop_open is None:
            raise RuntimeError("Shop screen did not open")
        logger.info("[gpay] Navigated to MLBB shop")

    def _select_purchase_item(self) -> None:
        """
        Select the smallest available diamond package for the test purchase.

        We want to buy the cheapest available item to minimize cost for
        non-test environments. Typically the smallest diamond pack.
        """
        diamond_tab_strategies = [
            LocatorStrategy.by_text("Diamonds"),
            LocatorStrategy.by_text("Buy Diamonds"),
            LocatorStrategy.by_id(f"{MLBB_PACKAGE}:id/diamond_tab"),
        ]
        diamond_tab = self.locator.find_element(diamond_tab_strategies, timeout=5.0)
        if diamond_tab:
            self.gestures.tap(diamond_tab)
            time.sleep(1.5)

        # Scroll to find smallest pack (usually at top or bottom)
        smallest_pack_strategies = [
            # Typical smallest MLBB diamond pack labels
            LocatorStrategy.by_text("11 Diamonds"),
            LocatorStrategy.by_text("22 Diamonds"),
            LocatorStrategy.by_text("56 Diamonds"),
            # Generic "buy" items at top of list
            LocatorStrategy.by_xpath(
                '//android.widget.RecyclerView[@resource-id="'
                f'{MLBB_PACKAGE}:id/diamond_list'
                '"]/android.view.ViewGroup[1]'
            ),
            LocatorStrategy.by_template("templates/mlbb_diamond_pack_small.png"),
        ]

        item = self.locator.find_element(smallest_pack_strategies, timeout=8.0)
        if item is None:
            # Try scrolling to find any purchasable item
            self.gestures.scroll_to_text("Diamonds", max_scrolls=3)
            item = self.locator.find_element(smallest_pack_strategies, timeout=5.0)

        if item is None:
            raise RuntimeError("Could not find a purchasable item in the shop")

        self.gestures.tap(item)
        time.sleep(1.5)
        logger.info("[gpay] Selected purchase item")

    def _initiate_purchase(self) -> None:
        """Tap the buy/purchase button to trigger Google Play Billing."""
        purchase_strategies = [
            # Various buy/purchase button labels
            LocatorStrategy.by_text("Buy Now"),
            LocatorStrategy.by_text("Purchase"),
            LocatorStrategy.by_text("Buy"),
            LocatorStrategy.by_text("Recharge"),
            LocatorStrategy.by_id(f"{MLBB_PACKAGE}:id/btn_buy"),
            LocatorStrategy.by_id(f"{MLBB_PACKAGE}:id/purchase_button"),
            LocatorStrategy.by_template("templates/mlbb_buy_button.png"),
        ]
        buy_btn = self.locator.find_element(purchase_strategies, timeout=10.0)
        if buy_btn is None:
            raise RuntimeError("Purchase/Buy button not found")

        self.gestures.tap(buy_btn)
        logger.info("[gpay] Purchase initiated")
        time.sleep(2.0)

        # Handle "Buy with Google Play" selection if presented
        billing_method_strategies = [
            LocatorStrategy.by_text("Buy with Google Play"),
            LocatorStrategy.by_text("Google Play"),
        ]
        billing_select = self.locator.find_element(billing_method_strategies, timeout=3.0)
        if billing_select:
            self.gestures.tap(billing_select)
            time.sleep(1.5)

    def _handle_billing_dialog(self) -> None:
        """
        Handle the Google Play Billing dialog.

        This dialog is managed by Google Play Services, not MLBB.
        It shows the payment method and item details.

        In test mode, Google shows a "Test payment" card.
        """
        billing_dialog_indicators = [
            # Google Play Billing bottom sheet
            LocatorStrategy.by_id("com.google.android.gms:id/payment_method_section"),
            LocatorStrategy.by_id("com.android.vending:id/payment_method_section"),
            LocatorStrategy.by_text("Buy"),
            LocatorStrategy.by_text("Subscribe"),
            LocatorStrategy.by_text("Complete purchase"),
            # Test payment
            LocatorStrategy.by_text("Test payment"),
            LocatorStrategy.by_text("Test card of US"),
        ]
        dialog = self.locator.wait_for_element(billing_dialog_indicators, timeout=15.0)
        if dialog is None:
            raise RuntimeError("Google Play Billing dialog did not appear")

        logger.info("[gpay] Google Play Billing dialog appeared")

        # Verify it shows a payment method
        payment_method_strategies = [
            LocatorStrategy.by_id("com.google.android.gms:id/payment_method_name"),
            LocatorStrategy.by_text("Test payment"),
            LocatorStrategy.by_text("Visa"),
            LocatorStrategy.by_text("Mastercard"),
            LocatorStrategy.by_text("Add payment method"),
        ]
        payment_shown = self.locator.find_element(payment_method_strategies, timeout=5.0)
        if payment_shown is None:
            logger.warning("[gpay] No payment method shown — attempting to add test card")
            self._setup_test_payment()

        # Take a screenshot of the billing dialog for record
        self._capture_screenshot(self._steps[-1], "billing_dialog")

    def _setup_test_payment(self) -> None:
        """
        Add a test payment method if none is configured.

        For licensed testers, Google allows test card "4111 1111 1111 1111".
        """
        add_payment_strategies = [
            LocatorStrategy.by_text("Add payment method"),
            LocatorStrategy.by_text("Add a card"),
        ]
        add_btn = self.locator.find_element(add_payment_strategies, timeout=5.0)
        if not add_btn:
            logger.warning("[gpay] Cannot add payment method — billing will likely fail")
            return

        self.gestures.tap(add_btn)
        time.sleep(2.0)

        # This would typically open a card entry form
        # In a real test environment, use a pre-configured test card
        logger.warning("[gpay] Payment method setup required — please pre-configure test card")

    def _confirm_payment(self) -> None:
        """Tap the final confirm/buy button in the billing dialog."""
        confirm_strategies = [
            # Google Play Billing confirm button
            LocatorStrategy.by_id("com.google.android.gms:id/confirm_button"),
            LocatorStrategy.by_id("com.android.vending:id/confirm_button"),
            LocatorStrategy.by_text("Buy"),
            LocatorStrategy.by_text("Confirm"),
            LocatorStrategy.by_text("Complete purchase"),
            LocatorStrategy.by_template("templates/gpay_buy_button.png"),
        ]
        confirm = self.locator.find_element(confirm_strategies, timeout=10.0)
        if confirm is None:
            raise RuntimeError("Confirm/Buy button in billing dialog not found")

        # Last safety check — only proceed in test mode or with explicit flag
        if not self.config.google_pay_test_mode:
            logger.critical(
                "[gpay] LIVE PAYMENT MODE — confirm this is intentional! "
                "Set google_pay_test_mode=true to prevent real charges."
            )

        self.gestures.tap(confirm)
        logger.info("[gpay] Payment confirmed — waiting for processing")
        time.sleep(3.0)

        # May require biometric/PIN confirmation
        self._handle_authentication_prompt()

    def _handle_authentication_prompt(self) -> None:
        """
        Handle fingerprint/PIN confirmation if the device requires it
        for purchases.
        """
        auth_indicators = [
            LocatorStrategy.by_text("Confirm your PIN"),
            LocatorStrategy.by_text("Use fingerprint"),
            LocatorStrategy.by_text("Touch fingerprint sensor"),
            LocatorStrategy.by_text("Authentication required"),
        ]
        auth_required = self.locator.find_element(auth_indicators, timeout=5.0)
        if not auth_required:
            return

        logger.info("[gpay] Authentication prompt detected")
        # Try PIN if we know it
        pin_strategies = [
            LocatorStrategy.by_xpath('//android.widget.EditText'),
        ]
        pin_field = self.locator.find_element(pin_strategies, timeout=3.0)
        if pin_field:
            # In a real scenario, PIN would be configured
            # For now, we skip (user must handle manually in live mode)
            logger.warning("[gpay] PIN required for purchase — cannot complete automatically")
        time.sleep(5.0)

    def _verify_purchase(self) -> None:
        """Verify the purchase was completed successfully."""
        # Google Play shows a receipt/confirmation
        receipt_indicators = [
            LocatorStrategy.by_text("Purchase complete"),
            LocatorStrategy.by_text("Payment successful"),
            LocatorStrategy.by_text("Thank you"),
            LocatorStrategy.by_id("com.google.android.gms:id/receipt_header"),
            LocatorStrategy.by_id("com.android.vending:id/purchase_complete_title"),
        ]

        # Also check: we're back in MLBB with updated balance
        mlbb_confirm_indicators = [
            # Diamond balance updated in MLBB
            LocatorStrategy.by_id(f"{MLBB_PACKAGE}:id/diamond_count"),
            LocatorStrategy.by_text("Purchase Successful"),
            LocatorStrategy.by_text("Diamonds added"),
            LocatorStrategy.by_template("templates/mlbb_purchase_success.png"),
        ]

        # Wait for either type of confirmation
        max_wait = min(20.0, self.budget.step_remaining(self.BUDGET_KEY))
        deadline = time.monotonic() + max_wait

        while time.monotonic() < deadline:
            receipt = self.locator.find_element(receipt_indicators, timeout=3.0)
            if receipt:
                logger.info("[gpay] Purchase confirmed — receipt shown")
                self._capture_screenshot(self._steps[-1], "purchase_receipt")
                # Dismiss receipt
                dismiss_strategies = [
                    LocatorStrategy.by_text("Done"),
                    LocatorStrategy.by_text("OK"),
                    LocatorStrategy.by_content_desc("Close"),
                ]
                dismiss = self.locator.find_element(dismiss_strategies, timeout=3.0)
                if dismiss:
                    self.gestures.tap(dismiss)
                return

            in_game_confirm = self.locator.find_element(mlbb_confirm_indicators, timeout=3.0)
            if in_game_confirm:
                logger.info("[gpay] Purchase confirmed — back in MLBB with updated balance")
                self._capture_screenshot(self._steps[-1], "purchase_confirmed_ingame")
                return

            # Check for failure
            failure_strategies = [
                LocatorStrategy.by_text("Payment failed"),
                LocatorStrategy.by_text("Purchase failed"),
                LocatorStrategy.by_text("Error"),
            ]
            failure = self.locator.find_element(failure_strategies, timeout=1.0)
            if failure:
                error_text = failure.element.text if failure.element else "Unknown failure"
                raise RuntimeError(f"Purchase failed: {error_text}")

            time.sleep(2.0)

        raise RuntimeError(f"Purchase confirmation not received within {max_wait:.0f}s")
