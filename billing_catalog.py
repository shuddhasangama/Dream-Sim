"""Server-owned, versioned prices. Amounts are integer currency minor units."""
import json
import os
from api_contract import ApiError

PRODUCTS = {
    'verification': {'amount': 199900, 'label': 'Verification', 'scope': 'user'},
    'date_mechanics': {'amount': 99900, 'label': 'Date mechanics', 'scope': 'date'},
    'relationship_entry': {'amount': 99900, 'label': 'Relationship entry', 'scope': 'pair'},
    'guru': {'amount': 19900, 'label': 'Guru', 'scope': 'user', 'recurring': True},
    'engagement_marriage': {'amount': 199900, 'label': 'Engagement + Marriage',
                            'scope': 'couple', 'future_dependency': 'active_guru'},
}


def mode():
    value = os.getenv('DHASHU_BILLING_MODE', 'disabled')
    if value not in ('disabled', 'sandbox', 'live_pilot'):
        raise ApiError('billing_configuration', 'Invalid billing mode.', 503)
    return value


def price(uid, product):
    if mode() == 'disabled':
        raise ApiError('billing_disabled', 'Payment checkout is not enabled.', 503)
    if not pilot_user(uid):
        raise ApiError('billing_pilot_only', 'Checkout is currently limited to payment testers.', 403)
    if product not in PRODUCTS:
        raise ApiError('unknown_product', 'Unknown product.')
    # Deployment-owned market; never accept country, currency or amount from a client.
    market = os.getenv('DHASHU_BILLING_MARKET', 'IN')
    if market != 'IN':
        raise ApiError('market_unavailable', 'This market has no active billing adapter.', 409)
    try:
        overrides = json.loads(os.getenv('DHASHU_BILLING_PRICES_JSON', '{}'))
        if not isinstance(overrides,dict):
            raise ValueError()
    except (ValueError,TypeError):
        raise ApiError('billing_configuration','Invalid price catalogue JSON.',503) from None
    amount = overrides.get(product, PRODUCTS[product]['amount'])
    if type(amount) is not int or amount < 100:
        raise ApiError('billing_configuration', 'Invalid configured price.', 503)
    return {**PRODUCTS[product], 'product': product, 'country': market, 'currency': 'INR',
            'catalog_amount': amount, 'amount': 100, 'mode': mode(),
            'version': os.getenv('DHASHU_BILLING_PRICE_VERSION', 'india-v1'),
            'tax_treatment': 'test-price-total', 'recurring': product == 'guru'}


def pilot_user(uid):
    return mode() != 'disabled' and uid in set(os.getenv('DHASHU_BILLING_TESTERS','').replace(' ','').split(','))


def route(channel):
    # Native digital purchases cannot quietly fall through to an external gateway.
    if channel in ('ios', 'android'):
        raise ApiError('store_billing_required', 'Native digital purchases require the configured store billing integration.', 409)
    if channel != 'web':
        raise ApiError('invalid_channel', 'Unsupported billing channel.')
    return 'razorpay'
