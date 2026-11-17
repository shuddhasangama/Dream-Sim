"""One-off PostgreSQL cleanup; default dry run. No provider calls or external-file deletion."""
import argparse
from collections import deque
import json
import re

PROTECTED={'+919986006265':'su_68d63e3733e1',
           '+919986006275':'su_12458b8c2c3c',
           '+919986006296':'su_72b266b15ac7'}
USER_COLUMNS={'user_id','owner_id','requester_id','user_a','user_b','partner_a_id',
              'partner_b_id','candidate_id','initiated_by','raised_by','actor_id',
              'from_user_id','revoked_by','asked_by'}
SOFT={'account_id':['Account'],'session_id':['AuthSession'],
      'couple_id':['Couple'],'pair_id':['LockIn'],'lockin_id':['LockIn'],
      'dateplan_id':['DatePlan'],'case_id':['BgvCase'],'case_check_id':['BgvCaseCheck'],
      'request_id':['BgvRequest'],'purchase_id':['BillingPurchase'],
      'digilocker_session_id':['DigiLockerSession'],'parent_request_id':['BgvRequest'],
      'scope_id':['User','Couple','LockIn','DatePlan']}

def q(value):return '"'+value.replace('"','""')+'"'
def phone(value):
    digits=re.sub(r'[^0-9]','',str(value or ''))
    return '+91'+digits if len(digits)==10 else '+'+digits

def purge(conn,*,apply=False,expected=240,protected=None):
    protected=PROTECTED if protected is None else protected
    conn.rollback()
    with conn.transaction():
        conn.execute("SET LOCAL lock_timeout='5s'")
        conn.execute("SET LOCAL statement_timeout='120s'")
        # Restrict to this app's public tables. No disabled foreign keys, CASCADE or triggers.
        tables=[r['relname'] for r in conn.execute("SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='r' ORDER BY c.relname")]
        if not {'User','Account'}<=set(tables):raise ValueError('App tables not found')
        conn.execute('LOCK TABLE '+','.join('public.'+q(t) for t in tables)+' IN SHARE ROW EXCLUSIVE MODE')
        columns={t:{} for t in tables};pks={t:[] for t in tables}
        for r in conn.execute("SELECT table_name,column_name,is_nullable FROM information_schema.columns WHERE table_schema='public'"):
            if r['table_name'] in columns:columns[r['table_name']][r['column_name']]=r['is_nullable']=='YES'
        for r in conn.execute("SELECT tc.table_name,k.column_name FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage k ON k.constraint_name=tc.constraint_name AND k.constraint_schema=tc.constraint_schema WHERE tc.table_schema='public' AND tc.constraint_type='PRIMARY KEY' ORDER BY k.ordinal_position"):
            if r['table_name'] in pks:pks[r['table_name']].append(r['column_name'])
        fks=[]
        for r in conn.execute("""SELECT c.conrelid::regclass::text child,c.confrelid::regclass::text parent,
          ARRAY(SELECT a.attname FROM unnest(c.conkey) WITH ORDINALITY k(num,ord) JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=k.num ORDER BY k.ord) child_cols,
          ARRAY(SELECT a.attname FROM unnest(c.confkey) WITH ORDINALITY k(num,ord) JOIN pg_attribute a ON a.attrelid=c.confrelid AND a.attnum=k.num ORDER BY k.ord) parent_cols
          FROM pg_constraint c WHERE c.contype='f' AND c.connamespace='public'::regnamespace"""):
            child=r['child'].removeprefix('public.').strip('"');parent=r['parent'].removeprefix('public.').strip('"')
            if child not in tables or parent not in tables:raise ValueError('Cross-schema foreign key needs review')
            fks.append((child,parent,list(r['child_cols']),list(r['parent_cols'])))
        data={};nodes={}
        for t in tables:
            data[t]=[dict(r) for r in conn.execute('SELECT * FROM public.'+q(t))]
            if sum(map(len,data.values()))>250000:raise ValueError('Dataset exceeds cleanup size limit')
            for i,r in enumerate(data[t]):nodes[(t,i)]=r
        actual={}
        for number,uid in protected.items():
            found=[r for r in data['Account'] if phone(r.get('phone'))==number]
            if len(found)!=1 or found[0]['user_id']!=uid:raise ValueError('Protected account mapping changed: '+number)
            actual[number]=uid
        keep_ids=set(actual.values());all_ids={r['id'] for r in data['User']}
        if len(keep_ids)!=len(protected) or not keep_ids<=all_ids:raise ValueError('Protected profiles missing or duplicated')
        target_ids=all_ids-keep_ids
        if len(target_ids)!=expected:raise ValueError('User count changed; expected '+str(expected)+', found '+str(len(target_ids)))
        # Edges point parent -> dependent, including app relationships without FK constraints.
        edges={node:set() for node in nodes};real_edges=[]
        for child,parent,cc,pc in fks:
            lookup={tuple(r[c] for c in pc):(parent,i) for i,r in enumerate(data[parent])}
            for i,r in enumerate(data[child]):
                value=tuple(r[c] for c in cc)
                if any(v is None for v in value):continue
                if value in lookup:
                    a,b=lookup[value],(child,i);edges[a].add(b);real_edges.append((a,b,cc))
        relations={c:['User'] for c in USER_COLUMNS};relations.update(SOFT)
        for child in tables:
            rel=dict(relations)
            if child=='WaitlistAudit':rel['target_id']=['WaitlistEntry']
            if child=='BgvReview':rel['source_id']=['BgvAttempt','DigiLockerSession']
            for c,parents in rel.items():
                if c not in columns[child]:continue
                for parent in parents:
                    if parent not in data or 'id' not in columns[parent]:continue
                    lookup={r['id']:(parent,i) for i,r in enumerate(data[parent])}
                    for i,r in enumerate(data[child]):
                        if r.get(c) in lookup:edges[lookup[r[c]]].add((child,i))
        # Historical reset archive may hold a whole previous profile, not a current Account FK.
        for i,r in enumerate(data.get('SignupResetArchive',[])):
            try:
                snapshot=json.loads(r.get('snapshot_json') or '{}')
                text=json.dumps(snapshot)
                owners=[uid for uid in all_ids if '"'+uid+'"' in text]
            except (TypeError,ValueError):raise ValueError('Reset archive needs manual review')
            for uid in owners:
                for j,user in enumerate(data['User']):
                    if user['id']==uid:edges[('User',j)].add(('SignupResetArchive',i))
        def closure(ids):
            selected={('User',i) for i,r in enumerate(data['User']) if r['id'] in ids};todo=list(selected)
            while todo:
                for nxt in edges[todo.pop()]-selected:selected.add(nxt);todo.append(nxt)
            return selected
        remove=closure(target_ids);keep=closure(keep_ids)
        if not protected:
            # Unlinked OTP attempts and historic reset copies must not survive a full reset.
            extra={node for node in nodes if node[0] in ('AuthChallenge','AuthThrottle','SignupResetArchive')}
            todo=list(extra);remove.update(extra)
            while todo:
                for nxt in edges[todo.pop()]-remove:remove.add(nxt);todo.append(nxt)
        shared_matches={node for node in remove & keep if node[0]=='Match'
            and {nodes[node].get('user_id'),nodes[node].get('candidate_id')} & target_ids
            and {nodes[node].get('user_id'),nodes[node].get('candidate_id')} & keep_ids}
        conflicts=(remove & keep)-shared_matches
        if conflicts:
            affected=sorted({t for t,i in conflicts})
            raise ValueError('Shared protected records would be affected: '+', '.join(affected))
        for t,i in remove:
            if not pks[t]:raise ValueError('Selected table has no primary key: '+t)
            r=nodes[t,i]
            if t in ('BillingPurchase','BillingEntitlement') and r.get('mode')!='sandbox':raise ValueError('Live billing records need reconciliation first')
            if t=='RestaurantBooking':
                payload=json.loads(r.get('payload_json') or '{}')
                if payload.get('mode')!='simulation':raise ValueError('Restaurant booking needs provider-side review first')
        # Fail closed for user-defined delete/update triggers.
        trigger_tables={r['table_name'] for r in conn.execute("SELECT c.relname table_name FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid WHERE NOT t.tgisinternal AND t.tgenabled<>'D'")}
        if trigger_tables & {t for t,i in remove}:raise ValueError('User-defined triggers need review before deletion')
        counts={t:sum(node[0]==t for node in remove) for t in tables};counts={t:n for t,n in counts.items() if n}
        print(json.dumps({'users_to_delete':len(target_ids),'users_preserved':len(keep_ids),'match_links_to_deleted_users_removed':len(shared_matches),'rows_to_delete':counts},indent=2))
        if not apply:return counts
        # Clear nullable FK links only on rows themselves selected for deletion (handles cycles).
        cleared=set()
        def where(t,r):return ' AND '.join(q(c)+'=%s' for c in pks[t]),tuple(r[c] for c in pks[t])
        for a,b,cc in real_edges:
            if a not in remove or b not in remove:continue
            t,i=b;nullable=[c for c in cc if columns[t][c] and c not in pks[t]]
            if nullable:
                c=nullable[0];condition,values=where(t,nodes[b])
                conn.execute('UPDATE public.'+q(t)+' SET '+q(c)+'=NULL WHERE '+condition,values)
                cleared.add((b,c))
        # Remaining mandatory dependencies are deleted child-first.
        pending={n:0 for n in remove};parents={n:set() for n in remove}
        for a,b,cc in real_edges:
            if a in remove and b in remove and not any((b,c) in cleared for c in cc):parents[b].add(a)
        for b,ps in parents.items():
            for a in ps:pending[a]+=1
        ready=deque(n for n,count in pending.items() if count==0);order=[]
        while ready:
            n=ready.popleft();order.append(n)
            for a in parents[n]:
                pending[a]-=1
                if pending[a]==0:ready.append(a)
        if len(order)!=len(remove):raise ValueError('Mandatory dependency cycle; nothing committed')
        for t,i in order:
            condition,values=where(t,nodes[t,i])
            result=conn.execute('DELETE FROM public.'+q(t)+' WHERE '+condition,values)
            if result.rowcount!=1:raise ValueError('Unexpected delete count in '+t)
        conn.execute('SET CONSTRAINTS ALL IMMEDIATE')
        # All retained rows, not merely the three account rows, must be unchanged.
        canonical=lambda rows:sorted(json.dumps(r,sort_keys=True,default=str) for r in rows)
        for t in tables:
            wanted=[r for i,r in enumerate(data[t]) if (t,i) not in remove]
            remaining=[dict(r) for r in conn.execute('SELECT * FROM public.'+q(t))]
            if canonical(wanted)!=canonical(remaining):raise ValueError('Retained records changed in '+t)
        if {r['id'] for r in conn.execute('SELECT id FROM public."User"')}!=keep_ids:raise ValueError('Final user check failed')
    print(f'PURGE COMMITTED: {len(target_ids)} users deleted; {len(keep_ids)} users preserved. Other retained records unchanged.')

if __name__=='__main__':
    import db
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--all-users',action='store_true')
    parser.add_argument('--expected-users',type=int,required=True)
    args=parser.parse_args()
    conn=db.get_connection()
    try:
        if not db._is_postgres_connection(conn):raise ValueError('This cleanup requires PostgreSQL')
        purge(conn,apply=args.apply,expected=args.expected_users,protected={} if args.all_users else None)
        if not args.apply:print('DRY RUN ONLY: no rows changed.')
    except Exception as exc:
        conn.rollback()
        # Database exceptions can embed personal row values; do not print them.
        print('STOP: transaction rolled back. '+(str(exc) if isinstance(exc,ValueError) else type(exc).__name__))
        raise SystemExit(1)
    finally:conn.close()
