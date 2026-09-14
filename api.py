"""Versioned JSON boundary; journey rules remain in the existing application.

Dependencies are supplied at registration so this module never imports app.py
or creates a second Flask application (including under Gunicorn).
"""
import math

from flask import Blueprint, g, jsonify, request
from api_contract import ApiError, json_object


def register_api(app, *, current_user, reach_locked, reach_state, reach_actions,
                 journey_state=None, week_reads=None, week_prepare=None, match_action=None, planning=None, date_cycle=None, evolution=None, after_date=None, relationship=None, enrollment=None):
    api = Blueprint("api_v1", __name__, url_prefix="/api/v1")
    if enrollment is not None:
        import enrollment_api
        enrollment_api.register(api, **enrollment)
    if relationship is not None:
        import relationship_api
        relationship_api.register(api, **relationship)
    if after_date is not None:
        import after_date_api
        after_date_api.register(api, **after_date)
    if evolution is not None:
        import evolution_api
        evolution_api.register(api, **evolution)
    if planning is not None:
        import planning_api
        planning_api.register(api, **planning)
    if date_cycle is not None:
        import date_cycle_api
        date_cycle_api.register(api, **date_cycle)

    def failure(code, message, status):
        return jsonify(error=message, code=code), status

    @api.errorhandler(ApiError)
    def contract_error(exc):
        return failure(exc.code, exc.message, exc.status)

    @api.before_request
    def authenticate():
        if request.endpoint == "api_v1.health":
            return None
        g.api_user = current_user()
        if g.api_user is None:
            return failure("authentication_required", "Sign in to continue.", 401)
        if request.path.startswith("/api/v1/reach") and reach_locked(g.api_user):
            return failure("reach_locked", "REACH is locked once you're past Dating", 403)

    @api.get("/health")
    def health():
        # Liveness only: no database initialization or simulation mutations.
        return jsonify(status="ok", api_version="v1")

    @api.get("/me")
    def me():
        return jsonify({key: g.api_user[key] for key in
                        ("user_id", "journey_state", "bgv_status")})

    @api.get("/profile")
    def profile():
        # Own-profile allowlist: never serialize Account, partner or pool rows.
        return jsonify({key: g.api_user[key] for key in
                        ("user_id", "city", "gender", "age_band", "stats",
                         "visions", "preferences", "journey_state", "bgv_status")})

    @api.get("/reach")
    def reach():
        return jsonify(reach_state(g.api_user["user_id"]))

    if journey_state is not None:
        @api.get('/dashboard')
        @api.get('/journey/status')
        def journey_status():
            return jsonify(journey_state(g.api_user))

        @api.get('/guidance')
        def guidance():
            state = journey_state(g.api_user)
            if 'verified' not in state['milestones']:
                return failure('verification_required', 'Background verification must clear first.', 403)
            return jsonify(state['next_action'])

    if week_reads is not None:
        @api.get('/week')
        def week():
            return jsonify(week_reads['week'](g.api_user))

        @api.get('/matches/<match_id>')
        def match_detail(match_id):
            return jsonify(week_reads['match'](g.api_user, match_id))

        @api.get('/lock-ins/current')
        def current_lock_in():
            return jsonify({'lock_in': journey_state(g.api_user)['current_lock_in']})

        @api.post('/week/prepare')
        def prepare_week():
            json_object()
            week_prepare(g.api_user)
            return jsonify(week_reads['week'](g.api_user))

        @api.post('/matches/<match_id>/actions')
        def decide_match(match_id):
            body = json_object(required={'action'}, optional={'pass_reason'})
            return jsonify(match_action(g.api_user, match_id, body))

    def action_view(action):
        def view():
            fields = {
                "ignore": {"filter", "ignore"},
                "show-all": {"ignore"},
                "widen": {"lever"},
                "set-range": {"lever", "min", "max"},
            }[action]
            payload = json_object(required=fields)
            for key in fields & {"filter", "lever"}:
                if not isinstance(payload[key], str):
                    return failure("validation_error", key + " must be a string.", 400)
            if action in ("widen", "set-range") and payload["lever"] not in g.api_user["preferences"]["adjustable"]:
                return failure("validation_error", "That filter is not available for your profile.", 400)
            if "ignore" in fields and type(payload["ignore"]) is not bool:
                return failure("validation_error", "ignore must be a boolean.", 400)
            if action == "set-range":
                for key in ("min", "max"):
                    value = payload[key]
                    try:
                        valid = type(value) in (int, float) and math.isfinite(value)
                    except OverflowError:
                        valid = False
                    if not valid:
                        return failure("validation_error", "min/max must be finite numbers.", 400)
                if payload["min"] > payload["max"]:
                    return failure("validation_error", "min must not exceed max.", 400)
            # Same handler, persistence and recomputed state as the web action.
            return reach_actions[action]()
        return view

    for action in reach_actions:
        api.add_url_rule("/reach/" + action, endpoint="reach_" + action.replace("-", "_"),
                         view_func=action_view(action), methods=["POST"])

    @app.after_request
    def api_response(response):
        # App-level hook includes routing 404/405 and the existing incident handler.
        if request.path != "/api/v1" and not request.path.startswith("/api/v1/"):
            return response
        if response.status_code == 405:
            methods = getattr(request.routing_exception, "valid_methods", None)
            if methods:
                response.headers["Allow"] = ", ".join(sorted(methods))
        payload = response.get_json(silent=True) or {}
        if response.status_code >= 400:
            codes = {400: "validation_error", 401: "authentication_required",
                     403: "forbidden", 404: "not_found", 405: "method_not_allowed",
                     415: "unsupported_media_type", 429: "rate_limited",
                     503: "auth_unavailable", 409: "state_conflict"}
            body = {"data": None, "error": {
                "code": payload.get("code", codes.get(response.status_code, "internal_error")),
                "message": payload.get("error", "Request failed."),
                "detail": payload.get("detail"), "reference": payload.get("reference"),
            }}
        else:
            body = {"data": payload, "error": None}
        response.set_data(app.json.dumps(body))
        response.content_type = "application/json"
        response.headers["Cache-Control"] = "no-store"
        return response

    app.register_blueprint(api)
