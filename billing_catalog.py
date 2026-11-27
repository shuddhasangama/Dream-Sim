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
    """DHASHU_BILLING_MODE (default 'disabled' = no gateway; the walkthrough's simulated
    fees apply). 'sandbox' = Razorpay test keys, testers only, Rs 1. 'live_pilot' = live
    keys, testers only, Rs 1. 'live' = owner decision 2026-11-25: real charges at the
    catalogue price for every member (live keys only; see docs/PAYMENTS_GO_LIVE.md)."""
    value = os.getenv('DHASHU_BILLING_MODE', 'disabled')
    if value not in ('disabled', 'sandbox', 'live_pilot', 'live'):
        raise ApiError('billing_configuration', 'Invalid billing mode.', 503)
    return value


LIVE_MONEY_MODES = ('live', 'live_pilot')
BYPASS_ON = ('1', 'true', 'yes', 'on')
BYPASS_OFF = ('', '0', 'false', 'no', 'off')
BYPASS_NOTICE = ('PAYMENT BYPASS ON (DHASHU_PAYMENT_BYPASS=1): every paid step is unlocked, '
                 'no checkout opens and nothing is charged. Development only; impossible in live billing modes.')


def payment_bypass_requested(environ=None):
    """DHASHU_PAYMENT_BYPASS as set (strict: ambiguous values count as off here and are
    refused by startup_check)."""
    env = os.environ if environ is None else environ
    return str(env.get('DHASHU_PAYMENT_BYPASS', '')).strip().lower() in BYPASS_ON


def payment_bypass(environ=None):
    """Owner decision 2026-11-27: development bypass. True only when DHASHU_PAYMENT_BYPASS
    is on AND the billing mode moves no real money (never 'live' or 'live_pilot'; an
    invalid mode also counts as off). Every fee gate, the verification payment and
    checkout read this one function."""
    env = os.environ if environ is None else environ
    if not payment_bypass_requested(env):
        return False
    return env.get('DHASHU_BILLING_MODE', 'disabled') in ('disabled', 'sandbox')


def real_billing(uid):
    """True when this member's payments go through Razorpay (never the simulation)."""
    if payment_bypass():
        return False
    return mode() == 'live' or pilot_user(uid)


def price(uid, product):
    if payment_bypass():
        raise ApiError('payment_bypass', 'Test mode: payments are off, so there is nothing to pay.', 409)
    if mode() == 'disabled':
        raise ApiError('billing_disabled', 'Payment checkout is not enabled.', 503)
    if mode() != 'live' and not pilot_user(uid):
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
    live = mode() == 'live'
    return {**PRODUCTS[product], 'product': product, 'country': market, 'currency': 'INR',
            'catalog_amount': amount, 'amount': amount if live else 100, 'mode': mode(),
            'version': os.getenv('DHASHU_BILLING_PRICE_VERSION', 'india-v1'),
            'tax_treatment': 'inclusive-total' if live else 'test-price-total', 'recurring': product == 'guru'}


def pilot_user(uid):
    return mode() != 'disabled' and uid in set(os.getenv('DHASHU_BILLING_TESTERS','').replace(' ','').split(','))


def route(channel):
    # Native digital purchases cannot quietly fall through to an external gateway.
    if channel in ('ios', 'android'):
        raise ApiError('store_billing_required', 'Native digital purchases require the configured store billing integration.', 409)
    if channel != 'web':
        raise ApiError('invalid_channel', 'Unsupported billing channel.')
    return 'razorpay'


def production(environ=None):
    env = os.environ if environ is None else environ
    return (env.get('RAILWAY_ENVIRONMENT_NAME') or env.get('RAILWAY_ENVIRONMENT') or env.get('DHASHU_ENVIRONMENT') or '').lower() == 'production'


def startup_check(environ=None):
    """Refuse to start a production web process with unsafe billing settings.

    In production with billing on: live mode needs the live key id (rzp_live_...), the
    key secret and a webhook secret; test keys and 'sandbox' are refused. Names only in
    the message, never values. Raises RuntimeError; returns None when fine."""
    env = os.environ if environ is None else environ
    value = env.get('DHASHU_BILLING_MODE', 'disabled')
    # Payment bypass: refused in every environment when real money can move.
    raw_bypass = str(env.get('DHASHU_PAYMENT_BYPASS', '')).strip().lower()
    if raw_bypass not in BYPASS_ON + BYPASS_OFF:
        raise RuntimeError('DHASHU_PAYMENT_BYPASS must be 1 or 0.')
    if raw_bypass in BYPASS_ON and value in LIVE_MONEY_MODES:
        raise RuntimeError('Billing configuration refused: DHASHU_PAYMENT_BYPASS cannot be on while '
                           'DHASHU_BILLING_MODE is ' + value + '. Remove DHASHU_PAYMENT_BYPASS.')
    if not production(env) or value == 'disabled':
        return None
    problems = []
    key = env.get('RAZORPAY_KEY_ID', '')
    if value == 'sandbox' or key.startswith('rzp_test_'):
        problems.append('Razorpay TEST keys / sandbox mode are not allowed in production')
    if value in ('live', 'live_pilot'):
        if not key.startswith('rzp_live_'):
            problems.append('RAZORPAY_KEY_ID must be a live key (rzp_live_...)')
        if not env.get('RAZORPAY_KEY_SECRET'):
            problems.append('RAZORPAY_KEY_SECRET is missing')
        if len(env.get('RAZORPAY_WEBHOOK_SECRET', '')) < 16:
            problems.append('RAZORPAY_WEBHOOK_SECRET is missing or shorter than 16 characters')
    if problems:
        raise RuntimeError('Billing configuration refused: ' + '; '.join(problems) + '. See docs/PAYMENTS_GO_LIVE.md.')
    return None


def startup_notice(environ=None):
    """The line the web process logs at startup while the bypass is on (else None)."""
    return BYPASS_NOTICE if payment_bypass(environ) else None
