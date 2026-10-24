"""Read-only connector readiness report. Never prints secrets or contacts."""
import json
import os
from restaurant_registry import config, readiness


def report():
    settings=config()
    return {'mode':os.environ.get('DHASHU_RESTAURANT_MODE','disabled'),
            'selection_policy':settings['selection_policy'],'providers':readiness(settings),
            'live_booking_enabled':False,
            'remaining':['Approved provider documentation and access',
                         'Reviewed platform mapping and real sandbox verification',
                         'Durable remote booking/payment orchestration and reconciliation',
                         'Live payment, cancellation and refund acceptance tests',
                         'Controlled real-user pilot before broad rollout']}


if __name__=='__main__':
    print(json.dumps(report(),indent=2))
