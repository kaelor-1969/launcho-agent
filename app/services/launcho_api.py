import uuid

def get_pricing():
    return {
        "currency": "toman",
        "setupFees": {"shop": 15000000, "website": 5000000},
        "plans": [{"months": 3, "title": "اشتراک ۳ ماهه", "price": 2400000}]
    }

def get_signup_options(kind="shop"):
    return {
        "kind": kind,
        "businessCategories": [{"id": "fashion", "label": "پوشاک و مد"}],
        "templates": [{"id": "example-row", "title": "قالب نمونه", "available": True}]
    }

def create_signup_draft(business_name, category, plan_months, template_id):
    draft_ref = "sd_" + str(uuid.uuid4())[:8]
    return {
        "ref": draft_ref,
        "confirmUrl": f"https://launcho.ir/start?signup={draft_ref}",
        "quote": {"total": 17400000, "isFinal": False}
    }
