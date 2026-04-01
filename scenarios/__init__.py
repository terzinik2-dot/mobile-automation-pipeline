"""
Scenarios Package

Each scenario represents a discrete automation objective:
- GoogleLoginScenario: Sign in to a Google account
- PlayStoreInstallScenario: Install MLBB from Play Store
- MLBBRegistrationScenario: Complete in-game registration
- GooglePayPurchaseScenario: Execute a Google Pay purchase
"""

from scenarios.base_scenario import BaseScenario
from scenarios.google_login import GoogleLoginScenario
from scenarios.play_store_install import PlayStoreInstallScenario
from scenarios.mlbb_registration import MLBBRegistrationScenario
from scenarios.google_pay_purchase import GooglePayPurchaseScenario

__all__ = [
    "BaseScenario",
    "GoogleLoginScenario",
    "PlayStoreInstallScenario",
    "MLBBRegistrationScenario",
    "GooglePayPurchaseScenario",
]
