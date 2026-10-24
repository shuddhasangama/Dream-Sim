"""Authenticated browser test screen, sharing the same booking service as mobile."""
import secrets
from decimal import Decimal, InvalidOperation
from flask import request, session, render_template, redirect, url_for, abort
import restaurant_service as service
from api_contract import ApiError


def register(app, get_db, current_user, login_required):
    @app.route('/restaurant/<path:pid>', methods=['GET','POST'])
    @login_required
    def restaurant_page(pid):
        if not service.enabled():
            abort(404)
        uid = current_user()['user_id']
        session.setdefault('restaurant_csrf', secrets.token_urlsafe(32))
        try:
            if request.method == 'POST':
                if not secrets.compare_digest(request.form.get('csrf',''), session['restaurant_csrf']):
                    abort(403)
                revision = request.form.get('revision','')
                body = {'revision':int(revision) if revision.isdigit() else None, 'action':request.form.get('action')}
                if request.form.get('quote_id'):
                    body['quote_id'] = request.form['quote_id']
                if request.form.get('cap'):
                    data = service.view(get_db(),uid,pid)
                    try:
                        amount = Decimal(request.form['cap']) * (10 ** data['currency_exponent'])
                        if not amount.is_finite() or amount != amount.to_integral_value() or not 0 < amount <= 1000000000:
                            abort(400)
                        body['max_per_person_minor'] = int(amount)
                    except InvalidOperation:
                        abort(400)
                service.act(get_db(),uid,pid,body)
                return redirect(url_for('restaurant_page',pid=pid))
            data = service.view(get_db(),uid,pid)
        except ApiError as exc:
            abort(exc.status, description=exc.message)
        return render_template('restaurant.html', r=data, csrf=session['restaurant_csrf'])
