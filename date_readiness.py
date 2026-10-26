"""Shared date status copy; a saved proposal is not a confirmed date."""
def describe(plan, my_signed=False, awaiting_next=False):
    if not plan:
        return {'state':'planning','label':'Plan your date','message':'Choose preferences and a shared time.'}
    status=plan.get('status')
    if awaiting_next or status == 'completed':
        return {'state':'completed','label':'Date completed','message':'Reflect on your date and agree on what happens next.'}
    if status in ('cancelled','no_show_reported'):
        return {'state':status,'label':'Date cancelled' if status=='cancelled' else 'No-show reported','message':'Review the outcome before arranging another date.'}
    if status == 'confirmed':
        return {'state':'confirmed','label':'Date confirmed','message':'Both agreements are complete. Prepare for your date.'}
    return {'state':'awaiting_partner' if my_signed else 'proposed',
            'label':'Waiting for your partner' if my_signed else 'Date proposed',
            'message':'Your agreement is complete. Waiting for your partner.' if my_signed else 'Complete your agreement. Both partners must finish before confirmation.'}
