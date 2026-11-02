"""Private operator commands. No public admin endpoints or automatic invitations."""
import argparse
import json
import uuid
import textwrap
import unicodedata
import db
import auth_sessions
import waitlist_service as service


def table(title, headers, rows):
    """Plain terminal tables, including wrapped long answers and safe labels."""
    def clean(value):
        return ''.join(c if not unicodedata.category(c).startswith('C') else ' ' for c in str(value))
    rows=[[clean(v) for v in row] for row in rows]
    if not rows:
        rows=[['No data recorded']+['-']*(len(headers)-1)]
    widths=[min(42,max(len(headers[i]),*(len(row[i]) for row in rows))) for i in range(len(headers))]
    rule='+'+'+'.join('-'*(w+2) for w in widths)+'+'
    output=['',title,rule,'| '+' | '.join(h.ljust(w) for h,w in zip(headers,widths))+' |',rule]
    for row in rows:
        wrapped=[textwrap.wrap(cell,width=w) or [''] for cell,w in zip(row,widths)]
        for line in range(max(map(len,wrapped))):
            output.append('| '+' | '.join((parts[line] if line<len(parts) else '').ljust(w) for parts,w in zip(wrapped,widths))+' |')
    output.append(rule)
    return '\n'.join(output)


def format_statistics(report):
    totals=report['totals']
    labels={'registrations':'All registrations','synthetic_test_registrations':'Synthetic test registrations',
            'contact_verified':'Verified contacts','linked_accounts':'Linked app accounts',
            'with_name':'Name supplied','with_email':'Email supplied','consent_recorded':'Consent recorded',
            'with_story_answers':'Registrations with story answers','without_story_answers':'Registrations without story answers',
            'story_answer_count':'Total story answers'}
    rows=[('Non-test registrations',report['non_test_registrations'])]+[(label,totals[key]) for key,label in labels.items()]
    sections=['DHASHU WAITLIST REGISTRATIONS',table('REGISTRATION SUMMARY',['Metric','Count'],rows)]
    categories={'genders':'Gender (self-declared)','age_bands':'Age band','statuses':'Registration status',
                'neighbourhoods':'Neighbourhood','sources':'Source','other_locations':'Other location',
                'consent_versions':'Consent version','survey_versions':'Story version'}
    for key,label in categories.items():
        sections.append(table(label.upper(),[label,'Count'],sorted(totals[key].items())))
    sections.append(table('REGISTRATIONS BY DAY (UTC)',['Date','Count'],sorted(report['daily_registrations_utc'].items())))
    sections.append(table('CITIES',['City','Launch status','All','Non-test','Test','Verified'],[
        (item['city'],item['launch_status'],item['registrations'],item['non_test_registrations'],item['synthetic_test_registrations'],item['contact_verified'])
        for _,item in sorted(report['markets'].items())]))
    for _,item in sorted(report['markets'].items()):
        city_rows=[]
        for key,label in categories.items():
            city_rows.extend((label,value,count) for value,count in sorted(item[key].items()))
        sections.append(table(item['city'].upper()+' BREAKDOWN',['Category','Answer','Count'],city_rows))
    sections.append(table('INTRODUCTORY STORY ANSWERS',['Story version : Question','Answer','Count'],[
        (question,answer,count) for question,answers in sorted(report['survey_answers'].items()) for answer,count in sorted(answers.items())]))
    sections.extend(['','Counts include test entries unless marked Non-test. Neighbourhood selections can overlap.',
                     'These are waitlist registrations, not verified people. Names and emails are not printed.',
                     'No story answers means none were shared with registration.'])
    return '\n'.join(sections)

def set_status(conn,entry,status,actor):
    transitions={'waiting':{'invited','withdrawn'},'invited':{'accepted','invitation_expired','withdrawn'},
                 'invitation_expired':{'waiting','withdrawn'},'accepted':{'withdrawn'},'withdrawn':set()}
    with auth_sessions.transaction(conn):
        row=db.fetch_one(conn,'WaitlistEntry',id=entry)
        if not row or status not in transitions.get(row['status'],set()) or not actor.strip():
            raise ValueError('Invalid status transition or operator')
        auth_sessions.sql(conn,'UPDATE "WaitlistEntry" SET status=? WHERE id=?',(status,entry))
        auth_sessions.sql(conn,'INSERT INTO "WaitlistAudit" (id,target_id,action,actor,created_at) VALUES (?,?,?,?,?)',
            (str(uuid.uuid4()),entry,'status:'+status,actor,service.stamp()))

def set_launch(conn,market,state,actor):
    if market not in {r['id'] for r in service.markets()} or state not in ('collecting','preparing','pilot','open','paused') or not actor.strip():
        raise ValueError('Valid market, state and operator name required')
    with auth_sessions.transaction(conn):
        auth_sessions.sql(conn,'INSERT INTO "WaitlistMarket" (id,state,updated_at) VALUES (?,?,?) '
            'ON CONFLICT (id) DO UPDATE SET state=excluded.state,updated_at=excluded.updated_at',(market,state,service.stamp()))
        auth_sessions.sql(conn,'INSERT INTO "WaitlistAudit" (id,target_id,action,actor,created_at) VALUES (?,?,?,?,?)',
            (str(uuid.uuid4()),market,'launch:'+state,actor,service.stamp()))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    stats=sub.add_parser('stats');stats.add_argument('--json',action='store_true',help='Print the complete JSON report instead of tables')
    launch=sub.add_parser('launch');launch.add_argument('market');launch.add_argument('state');launch.add_argument('--actor',required=True)
    status=sub.add_parser('status');status.add_argument('entry');status.add_argument('state');status.add_argument('--actor',required=True)
    args=parser.parse_args();conn=db.get_connection()
    try:
        if args.command=='stats':
            report=service.statistics(conn)
            print(json.dumps(report,indent=2) if args.json else format_statistics(report))
        elif args.command=='launch':set_launch(conn,args.market,args.state,args.actor);print('Launch status saved. No invitations sent; no users activated.')
        else:set_status(conn,args.entry,args.state,args.actor);print('Status recorded. No email sent and no account activated.')
    finally:conn.close()
