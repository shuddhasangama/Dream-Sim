"""Small, deterministic Guru prompts from the current pair and own Debrief."""
import db


def context(conn, uid, pair, plan, clock, epoch=None):
    if not pair:
        return None
    other = pair['user_b'] if pair['user_a'] == uid else pair['user_a']
    def activities(who):
        row = db.fetch_one(conn, 'User', id=who)
        return db.load_json_field(row['skills_json'], {}).get('activities', {})
    mine, theirs = activities(uid), activities(other)
    groups = {'enjoy': [], 'develop': [], 'try': [], 'respect': []}
    for key in sorted(mine.keys() & theirs.keys()):
        a, b = mine[key], theirs[key]
        if 'no' in (a, b):
            groups['respect'].append(key)
        elif 'maybe' in (a, b):
            groups['try'].append(key)
        elif 'improve' in (a, b):
            groups['develop'].append(key)
        elif a == b == 'good':
            groups['enjoy'].append(key)
    prompts = []
    for key, label, tip in (
        ('enjoy', 'Enjoy together', 'Choose something you both enjoy'),
        ('develop', 'Learn together', 'Ask whether learning together sounds fun'),
        ('try', 'Open to trying', 'Check before suggesting a new activity'),
        ('respect', 'Respect a no', 'Leave these activities out unless preferences change'),
    ):
        if groups[key]:
            prompts.append({'title': label, 'body': tip + ': ' + ', '.join(groups[key][:4]) + '.'})
    completed = pair.get('dates_completed', 0)
    plans = db.fetch_all(conn, 'DatePlan', lockin_id=pair['id'])
    previous = sorted((p for p in plans if not plan or p['id'] != plan['id']), key=lambda p:p['datetime'], reverse=True)
    for old in previous:
        row = db.fetch_one(conn, 'DateFeedback', user_id=uid, dateplan_id=old['id'])
        if row:
            flags = db.load_json_field(row['payload_json'], {}).get('flags', {})
            if flags.get('green_flags'):
                prompts.append({'title':'Your last Debrief', 'body':'You appreciated: ' + ', '.join(flags['green_flags']) + '. What would you like to repeat?'})
            if flags.get('red_flags'):
                prompts.append({'title':'Your concerns', 'body':'Revisit your saved concerns before another date. You can pause or end the match.'})
            break
    phase = 'planning' if not plan else 'agreement' if plan['status'] != 'confirmed' else 'before_date'
    focus = 'Choose preferences and a shared time.' if not plan else 'Review your agreement and greeting preference.'
    debrief = 'Debrief opens after your confirmed date.'
    if plan and plan['status'] == 'confirmed' and epoch is not None:
        import date_cycle_service
        timing = date_cycle_service.timing(plan,clock,epoch)
        if timing['open'] and not timing['closed']:
            phase, focus = 'debrief', 'Share what went well and any concerns.'
            debrief = 'Debrief is open. Save your flags, then choose what happens next.'
        else:
            debrief = 'Debrief opens '+timing['opens_at'].replace('T',' at ')+'.' if not timing['closed'] else 'This date’s Debrief window has closed.'
    return {'phase':phase,'focus':focus,'debrief':debrief,'date_number': completed + 1, 'day':clock.day,
            'when': plan.get('datetime') if plan else None,
            'prompts':prompts,
            'prep':'Confirm budget, diet, cuisine, a public venue and your greeting preference.',
            'sharing':'Phone, WhatsApp, LinkedIn, Facebook, Instagram and Snapchat sharing are optional after meeting. Each request needs consent; declining is free.'}
