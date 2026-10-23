"""Small provider adapter. No secrets or provider payloads in error responses."""
import base64
import hashlib
import hmac
import json
import os
import urllib.request
from urllib.error import HTTPError, URLError
from api_contract import ApiError
import billing_catalog


class Razorpay:
    def __init__(self):
        self.key = os.getenv('RAZORPAY_KEY_ID', '')
        self.secret = os.getenv('RAZORPAY_KEY_SECRET', '')
        prefix = 'rzp_test_' if billing_catalog.mode() == 'sandbox' else 'rzp_live_'
        if not self.key.startswith(prefix) or not self.secret:
            raise ApiError('gateway_configuration', 'Matching Razorpay credentials are required.', 503)
        if billing_catalog.mode() == 'live_pilot' and os.getenv('DHASHU_BILLING_LIVE_ACK') != 'charge-real-money':
            raise ApiError('live_disabled', 'Live pilot is not activated.', 503)

    def call(self, method, path, body=None):
        request = urllib.request.Request('https://api.razorpay.com/v1/' + path,
            data=None if body is None else json.dumps(body).encode(), method=method,
            headers={'Authorization': 'Basic '+base64.b64encode((self.key+':'+self.secret).encode()).decode(),
                     'Content-Type': 'application/json', 'User-Agent': 'DhaShuBilling/1.0'})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.load(response)
        except (HTTPError, URLError, TimeoutError, ValueError):
            # A failed response to a write is ambiguous: do not automatically repeat it.
            raise ApiError('provider_unavailable', 'Payment provider response unavailable. Check status before retrying.', 503) from None

    def create_order(self, purchase):
        return self.call('POST', 'orders', {'amount': purchase['amount'], 'currency': purchase['currency'],
            'receipt': purchase['id'], 'notes': {'purchase_id': purchase['id']}})

    def create_subscription(self, purchase):
        plan_id = os.getenv('RAZORPAY_GURU_TEST_PLAN_ID', '')
        if not plan_id.startswith('plan_') or not plan_id.replace('_', '').isalnum():
            raise ApiError('plan_required', 'Configure a monthly INR 1 Guru test plan.', 503)
        plan = self.call('GET', 'plans/'+plan_id)
        item = plan.get('item', {})
        if (plan.get('period'), plan.get('interval'), item.get('amount'), item.get('currency')) != ('monthly', 1, purchase['amount'], purchase['currency']):
            raise ApiError('plan_mismatch', 'Guru provider plan must match the quoted monthly test price.', 409)
        return self.call('POST', 'subscriptions', {'plan_id': plan_id, 'total_count': 12,
            'quantity': 1, 'customer_notify': 1, 'notes': {'purchase_id': purchase['id']}})


def verify_webhook(raw, signature):
    secret = os.getenv('RAZORPAY_WEBHOOK_SECRET', '')
    if not secret or not signature or not hmac.compare_digest(
            hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest(), signature):
        raise ApiError('invalid_signature', 'Invalid payment notification.', 401)
