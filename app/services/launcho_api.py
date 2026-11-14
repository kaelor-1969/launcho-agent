"""Legacy read-only facade. Sample registration options are no longer selectable."""
from app.services.catalog import documented_catalog

def get_pricing():
    return {
        "currency": "toman",
        "setupFees": {"shop": 15000000, "website": 5000000},
        "plans": [{"months": 3, "title": "اشتراک ۳ ماهه", "price": 2400000}]
    }

def get_signup_options(kind="shop"):
    return documented_catalog(kind)

def create_signup_draft(business_name, category, plan_months, template_id):
    raise RuntimeError('Legacy draft creation is disabled; use the contract adapter or explicit mock API.')
