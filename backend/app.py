import calendar
import hashlib
import logging
import os
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from functools import wraps

from flask import Flask, Response, g, jsonify, request, session
from flask_cors import CORS
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

import mailer
import security
import timeutil
from block_planner import build_month_blocks
from coverage_model import band_within, coverage_gaps, first_overlapping_pair, trim_band_to_hours
from exports import schedule_to_csv, schedule_to_ical
from holidays import REGIONS, holidays_in_range
from db import get_db_connection as _open_db_connection, init_db, WEEKDAYS
from i18n import DEFAULT_LANG, resolve_lang, t
from scheduler import (
    MAX_AVERAGE_DAILY_HOURS, MAX_CONSECUTIVE_DAYS, MIN_FREE_SUNDAYS_PER_YEAR, _ranges_overlap,
    _time_range_minutes, average_window, exceeds_average, generate_schedule,
    legal_break_minutes, net_working_minutes, rest_gap_hours, shift_datetimes,
    shift_duration_minutes, window_contains_shift, window_is_valid_on, working_days_in,
)

# Muss vor jedem Modul-Code stehen, der protokollieren koennte - insbesondere
# init_db() weiter unten. Stand diese Konfiguration erst am Dateiende (wie
# vor diesem Fix), lief init_db() mit dem Root-Logger auf dem WARNING-Default:
# jede Migration, die beim Start angewandt wurde, verschwand spurlos, obwohl
# init_db() sie protokolliert (siehe db.py) - auf Renders Free-Plan ohne Shell
# ist migrations.py status dort nicht mal als Notloesung erreichbar.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
)

app = Flask(__name__)
app.secret_key = security.resolve_secret_key()

if security.is_production():
    app.config['SESSION_COOKIE_SAMESITE'] = 'None'
    app.config['SESSION_COOKIE_SECURE'] = True

    # Nur in Produktion vertrauenswuerdig: Render terminiert TLS vor dieser
    # App und schreibt X-Forwarded-For/X-Forwarded-Proto selbst - der eine
    # Hop (x_for=1, x_proto=1), dem wir hier vertrauen, kommt also nachweislich
    # vom Render-Proxy, nicht vom Client. Lokal (und ueberall ohne Proxy davor)
    # gibt es diese Garantie nicht: ein direkt erreichbarer Flask-Dev-Server
    # wuerde jedem Client erlauben, X-Forwarded-For selbst zu setzen und damit
    # die in login_attempts.ip protokollierte Adresse zu faelschen - deshalb
    # bedingt auf is_production(), nicht global. Eine Bereitstellung, die diese
    # App direkt ohne vorgeschalteten Proxy exponiert, darf dies nicht
    # unveraendert uebernehmen.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

# supports_credentials is required for the session cookie to survive the
# cross-origin hop from the Vite dev server to this API. X-Lang and
# Authorization are not "simple" headers, so without allow_headers a
# cross-origin request carrying either would fail CORS preflight before ever
# reaching a route.
CORS(
    app,
    supports_credentials=True,
    origins=[
        origin.strip()
        for origin in os.environ.get(
            'ALLOWED_ORIGINS', 'http://localhost:5173,http://localhost:5174'
        ).split(',')
        if origin.strip()
    ],
    allow_headers=['Content-Type', 'X-Lang', 'Authorization'],
)

security.register_security_headers(app)

init_db()


@app.before_request
def resolve_request_lang():
    """The language of this one request, read fresh every time (never stored)
    from the header frontend/src/api.js sends on every call. Every message
    this API returns goes through t(g.lang, ...) rather than a hardcoded
    string - see i18n.py.
    """
    g.lang = resolve_lang(request.headers.get('X-Lang', DEFAULT_LANG))
    # Kurze Kennung, die in der Fehlerantwort und im Log steht, damit eine
    # Nutzermeldung ("Fehler a1b2c3d4") im Protokoll wiederfindbar ist.
    g.request_id = uuid.uuid4().hex[:8]


# Requests that change nothing are not worth a row, and the two that carry a
# password in their body are already covered by login_attempts - two records of
# the same event would be one too many.
AUDIT_SKIP_METHODS = frozenset({'GET', 'HEAD', 'OPTIONS'})
AUDIT_SKIP_PATHS = frozenset({'/login'})
AUDIT_LIMIT_DEFAULT = 100
AUDIT_LIMIT_MAX = 500


@app.after_request
def record_audit_entry(response):
    """Log every changing request: who, when, what method and path, what status.

    Deliberately request-level and **without bodies**. A narrative log ("put
    Anna on the early shift") would read better, but its details would write
    sick notes a second time, and those are health data under Art. 9 GDPR -
    that is the operator's call to make, not the schema's. What this answers is
    the question actually asked: who touched this assignment, and when.

    Failed requests are recorded too. A rejected attempt to change the roster
    is at least as interesting as a successful one, and a log that only knows
    successes hides exactly the cases people open it for.

    This must never turn a request into an error. A log that breaks an
    otherwise fine change is worse than no log - it would fail first in the
    moments when something is already wrong. Hence the try/except: the failure
    goes to the application log and the response goes out untouched.
    """
    if request.method in AUDIT_SKIP_METHODS:
        return response
    if request.path in AUDIT_SKIP_PATHS or request.path.startswith('/invitations/'):
        return response

    try:
        user = getattr(g, 'user', None)
        connection = get_db()
        # Erst zurueckrollen, dann schreiben. Der Haken laeuft, nachdem die
        # Route zurueckgekehrt ist: eine erfolgreiche hat laengst committet und
        # laesst nichts offen, eine gescheiterte laesst genau die halbfertigen
        # Zeilen stehen, die teardown_appcontext ohnehin verwerfen wuerde. Ohne
        # dieses rollback() committet der Eintrag sie mit - genau das ist beim
        # Bauen passiert, und ein Bestandstest hat es gefangen: ein ungueltig
        # angelegter Mitarbeiter blieb ploetzlich stehen.
        #
        # Die naheliegende Alternative war eine eigene Verbindung je Anfrage.
        # Sie ist entkoppelter, verdoppelte aber die Laufzeit der Testsuite
        # (68 auf 134 Sekunden) - und in Produktion waere es eine zusaetzliche
        # Postgres-Verbindung pro schreibender Anfrage, auf einer Instanz mit
        # begrenztem Vorrat. Der Preis stand in keinem Verhaeltnis.
        connection.rollback()
        cursor = connection.cursor()
        cursor.execute(
            'INSERT INTO audit_log (at, user_id, username, method, path, status) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=' ', timespec='seconds'),
             user['id'] if user else None,
             user['username'] if user else None,
             request.method, request.path, response.status_code),
        )
        connection.commit()
    except Exception:
        # app.logger, wie der globale Fehlerhandler weiter unten - app.py hat
        # keinen eigenen Modul-Logger.
        app.logger.exception('Audit-Eintrag konnte nicht geschrieben werden')

    return response


def get_db():
    """This request's database connection, opened on first use and reused after.

    Every route used to open its own connection and had to remember to close it
    on every single return path - easy to get wrong, and a forgotten close() on
    an exception path that isn't a plain ValueError (e.g. a stray null in a JSON
    list blowing up int()) leaked a connection holding a write lock, which then
    made every *other* request fail too until garbage collection eventually
    caught up. Going through `g` and teardown_appcontext below means the
    connection is closed exactly once per request no matter how it ends -
    including on an unhandled exception.
    """
    if 'db_connection' not in g:
        g.db_connection = _open_db_connection()
    return g.db_connection


@app.teardown_appcontext
def close_db(exception=None):
    connection = g.pop('db_connection', None)
    if connection is not None:
        connection.close()


# ---------- authentication ----------

HR_ROLE = 'hr'
EMPLOYEE_ROLE = 'employee'

# The session cookie alone isn't enough: it's SameSite=None (see FLASK_ENV
# above), which is *sent* fine cross-site by most browsers, but Safari/WebKit
# (including Chrome on iOS - Apple requires every iOS browser to use WebKit)
# applies Intelligent Tracking Prevention to it anyway and drops it, since
# from the browser's perspective the frontend and this API are two unrelated
# sites. Confirmed live: the same login worked over and over from a desktop
# Chromium browser and failed every time from an iPhone.
#
# The fix is a second, cookie-independent channel: a signed, stateless bearer
# token (itsdangerous - already a Flask dependency, no new package) returned
# in the login/register body and sent back as `Authorization: Bearer <token>`.
# That header isn't a cookie, so ITP has no opinion about it. Stateless means
# there is nothing to look up per request, but also nothing to revoke - the
# tradeoff is a fixed expiry rather than a server-side logout; acceptable for
# this app's threat model. The cookie path is left in place unchanged (it
# still works for same-site/local-dev use), so current_user_id() below tries
# it first and only falls back to the header if there's no session.
AUTH_TOKEN_MAX_AGE_SECONDS = 30 * 24 * 3600  # 30 days
_auth_serializer = URLSafeTimedSerializer(app.secret_key, salt='auth-token')


def issue_auth_token(user_id):
    return _auth_serializer.dumps({'user_id': user_id})


def verify_auth_token(token):
    try:
        data = _auth_serializer.loads(token, max_age=AUTH_TOKEN_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    return data.get('user_id')


def current_user_id():
    user_id = session.get('user_id')
    if user_id:
        return user_id

    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return verify_auth_token(auth_header[len('Bearer '):])
    return None


def load_current_user():
    """The signed-in account, or None. Read fresh so a role change takes effect."""
    user_id = current_user_id()
    if not user_id:
        return None

    connection = get_db()
    cursor = connection.cursor()
    cursor.execute('SELECT id, username, role, employee_id FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    return dict(user) if user else None


def is_hr(user):
    return bool(user) and user['role'] == HR_ROLE


def login_required(view):
    """Any signed-in account may pass: HR, or an employee reading the plan."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = load_current_user()
        if not user:
            return jsonify({'message': t(g.lang, 'not_signed_in')}), 401
        g.user = user
        return view(*args, **kwargs)

    return wrapped


def hr_required(view):
    """Anything that changes data is HR-only.

    Employee accounts are strictly read-only: they may look at the published
    schedule and nothing else. Enforced here rather than only by hiding buttons,
    because hidden buttons stop nobody from calling the API directly.
    """
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = load_current_user()
        if not user:
            return jsonify({'message': t(g.lang, 'not_signed_in')}), 401
        if not is_hr(user):
            return jsonify({'message': t(g.lang, 'hr_only')}), 403
        g.user = user
        return view(*args, **kwargs)

    return wrapped


def require_self_or_hr(employee_id):
    """The one deliberate, narrow exception to "employee accounts are read-only".

    Reporting your own sick/vacation days is a write, but only ever to your
    own roster entry - so this checks "signed in AND (HR OR this employee's
    own linked account)" instead of using the hr_required decorator above.
    Returns a (response, status) pair to return early on failure, or None to
    proceed; not a decorator, since the rule depends on the employee_id in the
    URL, which a decorator can't see without extra machinery the rest of this
    codebase doesn't otherwise use.
    """
    user = load_current_user()
    if not user:
        return jsonify({'message': t(g.lang, 'not_signed_in')}), 401
    if is_hr(user):
        g.user = user
        return None
    if user['role'] == EMPLOYEE_ROLE and user['employee_id'] == employee_id:
        g.user = user
        return None
    return jsonify({'message': t(g.lang, 'forbidden')}), 403


def count_users(cursor):
    cursor.execute('SELECT COUNT(*) AS n FROM users')
    return cursor.fetchone()['n']


# ---------- password invitations ----------

INVITATION_VALID_DAYS = 7
MIN_PASSWORD_LENGTH = 8


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def issue_invitation(cursor, user_id):
    """Replaces any open invitation, so a resend invalidates the previous link."""
    token = secrets.token_urlsafe(32)
    # .replace(tzinfo=None) statt des seit 3.12 veralteten datetime.utcnow():
    # gleicher naiver UTC-Wert, byte-identisch zum bisherigen isoformat()-String.
    # Ein aware Zeitstempel wuerde die Spalte (Postgres: TIMESTAMP ohne
    # Zeitzone) inkonsistent mit bestehenden Zeilen machen und load_invitation()
    # beim Vergleich mit einem naiven datetime crashen lassen.
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=INVITATION_VALID_DAYS)
    cursor.execute('DELETE FROM password_invitations WHERE user_id = ?', (user_id,))
    cursor.execute(
        'INSERT INTO password_invitations (user_id, token_hash, expires_at) VALUES (?, ?, ?)',
        (user_id, hash_token(token), expires_at.isoformat(timespec='seconds')),
    )
    return token


def load_invitation(cursor, token):
    """The account a token belongs to, or None if unknown or expired."""
    cursor.execute('''
        SELECT i.id, i.user_id, i.expires_at, u.username
        FROM password_invitations i
        JOIN users u ON u.id = i.user_id
        WHERE i.token_hash = ?
    ''', (hash_token(token),))
    invitation = cursor.fetchone()
    if not invitation:
        return None
    if as_datetime(invitation['expires_at']) < datetime.now(timezone.utc).replace(tzinfo=None):
        return None
    return dict(invitation)


def as_datetime(value):
    """Postgres hands back a datetime for a TIMESTAMP column; SQLite a string."""
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)


def employee_email(cursor, employee_id):
    cursor.execute('SELECT name, email FROM employees WHERE id = ?', (employee_id,))
    row = cursor.fetchone()
    return dict(row) if row else None


def looks_like_email(value):
    if not isinstance(value, str):
        return False
    local, at, domain = value.strip().partition('@')
    return bool(local) and bool(at) and '.' in domain and not domain.startswith('.')


def invitation_recipient(cursor, account):
    """Where this account's invitation goes, and who to address it to.

    An employee account takes the address from its roster entry, so it never
    drifts from the record HR maintains; an HR account has no roster entry and
    carries its own.
    """
    if account['role'] == EMPLOYEE_ROLE:
        employee = employee_email(cursor, account['employee_id']) if account['employee_id'] else None
        if employee and employee['email']:
            return employee['email'], employee['name']
        return None, None
    if account['email']:
        return account['email'], account['username']
    return None, None


@app.route('/register', methods=['POST'])
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not username:
        return jsonify({'message': t(g.lang, 'username_required')}), 400

    connection = get_db()
    cursor = connection.cursor()

    first_account = count_users(cursor) == 0
    creator = load_current_user()

    # The first account sets the tool up and is always HR - someone has to be
    # able to administer it. After that only HR may create accounts, so nobody
    # can sign themselves up and read the roster.
    if not first_account and not is_hr(creator):
        key = 'accounts_hr_only' if creator else 'accounts_signin_required'
        return jsonify({'message': t(g.lang, key)}), 403

    role = HR_ROLE if first_account else (data.get('role') or HR_ROLE)
    if role not in (HR_ROLE, EMPLOYEE_ROLE):
        return jsonify({'message': t(g.lang, 'unknown_role')}), 400

    # Every account except the very first is created by somebody else, so it is
    # invited: the person picks a password nobody else ever sees. The bootstrap
    # account is the exception - there is no one to invite it, so it sets its
    # own password on the spot.
    invited = not first_account

    employee_id = data.get('employee_id') if role == EMPLOYEE_ROLE else None
    account_email = (data.get('email') or '').strip() or None
    recipient_email = None
    recipient_name = None

    if role == EMPLOYEE_ROLE:
        # An employee account shows that person's own shifts, so it is useless
        # until it knows whose shifts those are.
        if employee_id is None:
            return jsonify({'message': t(g.lang, 'employee_account_needs_link')}), 400
        employee = employee_email(cursor, employee_id)
        if not employee:
            return jsonify({'message': t(g.lang, 'employee_not_found')}), 404

        # HR can set or correct the address right here instead of having to
        # leave this form to edit the roster entry first. Empty stays a no-op -
        # this field exists to unblock an invitation, not as a general edit
        # surface, so it must never blank out an address already on file.
        typed_email = (data.get('email') or '').strip()
        if typed_email:
            if not looks_like_email(typed_email):
                return jsonify({'message': t(g.lang, 'valid_email_required')}), 400
            cursor.execute('UPDATE employees SET email = ? WHERE id = ?', (typed_email, employee_id))
            employee['email'] = typed_email

        # The invitation is the only way this account gets a password, so
        # without an address there is nowhere to send it.
        if not employee['email']:
            return jsonify({'message': t(g.lang, 'employee_missing_email', name=employee['name'])}), 400
        # Taken from the roster entry rather than stored again on the account.
        account_email = None
        recipient_email, recipient_name = employee['email'], employee['name']
    elif invited:
        if not account_email:
            return jsonify({'message': t(g.lang, 'email_required_for_invitation')}), 400
        if not looks_like_email(account_email):
            return jsonify({'message': t(g.lang, 'valid_email_required')}), 400
        recipient_email, recipient_name = account_email, username
    else:
        # The bootstrap account. An address is optional here, but storing one
        # means this account can later be re-invited if the password is lost.
        if account_email and not looks_like_email(account_email):
            return jsonify({'message': t(g.lang, 'valid_email_required')}), 400
        if not password:
            return jsonify({'message': t(g.lang, 'password_required')}), 400
        if len(password) < MIN_PASSWORD_LENGTH:
            return jsonify({'message': t(g.lang, 'password_too_short', n=MIN_PASSWORD_LENGTH)}), 400

    cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
    if cursor.fetchone():
        return jsonify({'message': t(g.lang, 'username_taken')}), 400

    # An empty hash marks an account that cannot be signed into yet. Invited
    # accounts start that way, so nobody - the creator included - ever knows the
    # password that ends up on them.
    password_hash = '' if invited else generate_password_hash(password)
    cursor.execute(
        'INSERT INTO users (username, hash, role, employee_id, email) VALUES (?, ?, ?, ?, ?)',
        (username, password_hash, role, employee_id, account_email),
    )
    user_id = cursor.lastrowid

    invitation_sent = None
    if invited:
        token = issue_invitation(cursor, user_id)
        connection.commit()
        invitation_sent = mailer.send_invitation(
            recipient_email, username, token, INVITATION_VALID_DAYS, lang=g.lang)
    else:
        connection.commit()

    # Signing in the very first user saves them an immediate second step; HR
    # adding a colleague must stay logged in as themselves.
    auth_token = None
    if first_account:
        session['user_id'] = user_id
        auth_token = issue_auth_token(user_id)

    return jsonify({
        'id': user_id,
        'username': username,
        'role': role,
        'employee_id': employee_id,
        'invitation_email': recipient_email,
        'invitation_sent': invitation_sent,
        'auth_token': auth_token,
    }), 201


@app.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    connection = get_db()
    cursor = connection.cursor()

    if username and security.is_locked_out(cursor, username):
        return jsonify({'message': t(g.lang, 'too_many_login_attempts',
                                     minutes=security.ATTEMPT_WINDOW_MINUTES)}), 429

    cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()

    # An invited account has no password yet. Saying so is safe - the invitation
    # went to that person's mailbox, not to whoever is guessing here - and it is
    # far more useful than "wrong password" to someone who never set one.
    if user and not user['hash']:
        return jsonify({'message': t(g.lang, 'password_not_set_yet')}), 403

    # Same message either way, so the response cannot be used to find out which
    # usernames exist.
    if not user or not check_password_hash(user['hash'], password):
        if username:
            security.record_attempt(cursor, username, request.remote_addr, succeeded=False)
            connection.commit()
        return jsonify({'message': t(g.lang, 'login_failed')}), 401

    security.record_attempt(cursor, username, request.remote_addr, succeeded=True)
    connection.commit()

    session.clear()
    session['user_id'] = user['id']
    return jsonify({
        'id': user['id'],
        'username': user['username'],
        'role': user['role'],
        'employee_id': user['employee_id'],
        'auth_token': issue_auth_token(user['id']),
    }), 200


@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': t(g.lang, 'logged_out')}), 200


@app.route('/invitations/<token>', methods=['GET'])
def check_invitation(token):
    """Public: does this link still work? Used to greet the invitee by name."""
    connection = get_db()
    cursor = connection.cursor()
    invitation = load_invitation(cursor, token)

    if not invitation:
        return jsonify({'message': t(g.lang, 'invitation_invalid')}), 404
    return jsonify({'username': invitation['username']}), 200


@app.route('/invitations/<token>', methods=['POST'])
def redeem_invitation(token):
    """Public: the invitee sets their own password, which nobody else has seen."""
    data = request.get_json(silent=True) or {}
    password = data.get('password') or ''

    if len(password) < MIN_PASSWORD_LENGTH:
        return jsonify({'message': t(g.lang, 'password_too_short', n=MIN_PASSWORD_LENGTH)}), 400

    connection = get_db()
    cursor = connection.cursor()

    # Ein Treffer hier uebernimmt ein Konto, also wird auch das Einloesen
    # gedrosselt. Gezaehlt wird pro Token, nicht pro Konto - welches Konto
    # gemeint ist, weiss man ohne gueltigen Token gar nicht.
    attempt_key = f'invitation:{hash_token(token)}'
    if security.is_locked_out(cursor, attempt_key):
        return jsonify({'message': t(g.lang, 'too_many_login_attempts',
                                     minutes=security.ATTEMPT_WINDOW_MINUTES)}), 429

    invitation = load_invitation(cursor, token)
    if not invitation:
        security.record_attempt(cursor, attempt_key, request.remote_addr, succeeded=False)
        connection.commit()
        return jsonify({'message': t(g.lang, 'invitation_invalid')}), 404

    cursor.execute('UPDATE users SET hash = ? WHERE id = ?',
                   (generate_password_hash(password), invitation['user_id']))
    # Single use: the link stops working the moment it has been redeemed.
    cursor.execute('DELETE FROM password_invitations WHERE id = ?', (invitation['id'],))
    connection.commit()

    return jsonify({'username': invitation['username'],
                    'message': t(g.lang, 'password_set')}), 200


@app.route('/me', methods=['GET'])
def me():
    user_id = current_user_id()
    connection = get_db()
    cursor = connection.cursor()

    # The frontend uses this on load both to restore a session and to find out
    # whether this is a fresh install that still needs its first account.
    setup_required = count_users(cursor) == 0

    if not user_id:
        return jsonify({'message': t(g.lang, 'not_signed_in'), 'setup_required': setup_required}), 401

    cursor.execute('SELECT id, username, role, employee_id FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()

    if not user:
        # The account was deleted while the cookie was still around.
        session.clear()
        return jsonify({'message': t(g.lang, 'not_signed_in'), 'setup_required': setup_required}), 401

    return jsonify({
        'id': user['id'],
        'username': user['username'],
        'role': user['role'],
        'employee_id': user['employee_id'],
        'setup_required': False,
    }), 200


# ---------- serialization helpers ----------

def parse_int_list(value):
    """Whole numbers, rejecting the booleans int() quietly accepts.

    int(True) is 1: a stray `true` in allowed_shift_types becomes whichever
    shift type happens to hold id 1, and in unavailable_weekdays it blocks
    Tuesday. Both land inside the valid range, so nothing downstream objects.
    """
    if not value:
        return []
    try:
        if any(isinstance(v, bool) for v in value):
            raise ValueError
        return [int(v) for v in value]
    except (TypeError, ValueError):
        # int(None), int({...}), int([...]) etc. all raise TypeError rather than
        # ValueError - normalised here so a stray non-number in the list is a
        # clean 400 like any other bad input, not an unhandled 500.
        raise ValueError(t(g.lang, 'int_list_required'))


def serialize_employee(cursor, row):
    employee_id = row['id']
    cursor.execute('SELECT weekday FROM employee_unavailable_weekdays WHERE employee_id = ? ORDER BY weekday', (employee_id,))
    unavailable_weekdays = [r['weekday'] for r in cursor.fetchall()]

    cursor.execute('SELECT date, reason FROM employee_unavailable_dates WHERE employee_id = ? ORDER BY date', (employee_id,))
    unavailable_dates = [{'date': r['date'], 'reason': r['reason']} for r in cursor.fetchall()]

    cursor.execute('SELECT shift_type_id FROM employee_allowed_shift_types WHERE employee_id = ? ORDER BY shift_type_id', (employee_id,))
    allowed_shift_types = [r['shift_type_id'] for r in cursor.fetchall()]

    cursor.execute(
        'SELECT weekday, start_time, end_time, valid_from, valid_until FROM employee_availability '
        'WHERE employee_id = ? ORDER BY weekday, start_time',
        (employee_id,),
    )
    availability = [
        {
            'weekday': r['weekday'],
            'start_time': r['start_time'],
            'end_time': r['end_time'],
            'valid_from': r['valid_from'],
            'valid_until': r['valid_until'],
        }
        for r in cursor.fetchall()
    ]

    return {
        'id': employee_id,
        'name': row['name'],
        'email': row['email'],
        'active': bool(row['active']),
        'max_shifts_per_month': row['max_shifts_per_month'],
        'weekly_hours': row['weekly_hours'],
        'min_rest_hours': row['min_rest_hours'],
        'max_daily_hours': row['max_daily_hours'],
        'unavailable_weekdays': unavailable_weekdays,
        'unavailable_dates': unavailable_dates,
        'allowed_shift_types': allowed_shift_types,
        'availability_mode': row['availability_mode'],
        'availability': availability,
    }


def parse_iso_date(value, error_key='invalid_date_value'):
    """Validate a date and return its canonical YYYY-MM-DD form.

    Validating without normalising is the trap here. Since Python 3.11
    date.fromisoformat() also accepts the basic format ('20260901'), which
    passes the check and is then stored verbatim - and this tool compares dates
    as plain strings throughout, where '2026-09-15' sorts before '20260901'.
    The row exists, looks right in the database, and loses every later
    comparison: a blocked day that blocks nothing, a sick note that frees no
    shift, a closing day the business stays open on.

    Raises ValueError with a translated message, so callers that already catch
    ValueError need no new branch.
    """
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError):
        raise ValueError(t(g.lang, error_key, date=value))


def parse_weekday(value):
    """A weekday 0-6, rejecting the two values int() quietly accepts.

    int(True) is 1, so a stray boolean becomes Tuesday; int(3.9) is 3, so a
    rounding error one field upstream becomes Thursday instead of an error.
    Both produce a valid-looking row for a weekday nobody named.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(t(g.lang, 'weekday_out_of_range'))
    try:
        weekday = int(value)
        if float(value) != weekday:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError(t(g.lang, 'weekday_out_of_range'))
    if not 0 <= weekday <= 6:
        raise ValueError(t(g.lang, 'weekday_out_of_range'))
    return weekday


# § 3 ArbZG: eight hours a working day, extendable to ten only if the
# six-month average stays at eight. Ten is the ceiling this tool knows - § 7
# (collective agreement) and § 14 (emergencies) are not modelled, and a number
# above ten would be a promise the planner cannot keep anyway: block_planner's
# MAX_BLOCK_MINUTES caps a block at 600 minutes regardless.
MAX_DAILY_HOURS_CEILING = 10


def parse_daily_hours(value):
    """The per-employee daily ceiling: a number above 0 and at most ten.

    Zero passed the old check and was not a working-time limit but a disguised
    deactivation - the employee could never be scheduled, and nothing said so.
    """
    hours = parse_optional_hours(value, 'max_daily_hours_label')
    if hours is None:
        return None
    if not 0 < hours <= MAX_DAILY_HOURS_CEILING:
        raise ValueError(t(g.lang, 'max_daily_hours_out_of_range',
                           max=MAX_DAILY_HOURS_CEILING))
    return hours


def parse_optional_hours(value, field_key):
    """A non-negative number, or None if the field was omitted/blank.

    `field_key` names the field for the error message via an i18n key (e.g.
    'weekly_hours_label') rather than a literal string, so the message comes
    out in the request's language regardless of which field failed.
    """
    # float(True) is 1.0, so an unchecked boolean becomes a one-hour daily
    # limit or a one-hour weekly target - inside every valid range, and
    # therefore silent. Checked here rather than in the callers so the rule
    # holds for every field that goes through this parser.
    if isinstance(value, bool):
        raise ValueError(t(g.lang, 'field_must_be_number', field=t(g.lang, field_key)))
    if value is None or value == '':
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError(t(g.lang, 'field_must_be_number', field=t(g.lang, field_key)))
    if value < 0:
        raise ValueError(t(g.lang, 'field_must_not_be_negative', field=t(g.lang, field_key)))
    return value


def parse_assignment_times(data):
    """The optional start/end pair from a request body, validated as a pair.

    Returns (start, end) with both set or both None. Raises ValueError with a
    translated message otherwise - the caller turns that into a 400, the same
    way replace_employee_constraints does.
    """
    start_time = data.get('start_time') or None
    end_time = data.get('end_time') or None

    if (start_time is None) != (end_time is None):
        raise ValueError(t(g.lang, 'assignment_times_need_both'))
    for value in (start_time, end_time):
        if value is not None and not valid_time(value):
            # Reuses availability_time_invalid rather than adding a second key
            # with identical text - it already covers "value isn't HH:MM" for
            # any time field, not just availability windows.
            raise ValueError(t(g.lang, 'availability_time_invalid', value=value))
    # Equal start/end isn't a zero-length shift - shift_duration_minutes()
    # treats end <= start as running past midnight, so this would silently
    # become a 1440-minute shift instead of the empty range it looks like.
    if start_time is not None and start_time == end_time:
        raise ValueError(t(g.lang, 'assignment_times_must_differ'))
    return start_time, end_time


def parse_break_minutes(value):
    """A whole number of minutes, or None for "not separately agreed".

    None is not "no break": it reads as the legal minimum for the block's span
    (see scheduler.net_working_minutes). A stored 0 is the different, explicit
    statement that this block runs without one - that is HR's call to make, and
    constraint_warnings() is where it gets questioned.
    """
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        # bool is an int in Python, and True would silently become one minute.
        raise ValueError(t(g.lang, 'break_minutes_invalid'))
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        raise ValueError(t(g.lang, 'break_minutes_invalid'))
    if minutes != float(value) or minutes < 0:
        raise ValueError(t(g.lang, 'break_minutes_invalid'))
    return minutes


def replace_employee_constraints(connection, employee_id, data):
    cursor = connection.cursor()

    cursor.execute('DELETE FROM employee_unavailable_weekdays WHERE employee_id = ?', (employee_id,))
    for weekday in data.get('unavailable_weekdays') or []:
        weekday = parse_weekday(weekday)
        cursor.execute('INSERT INTO employee_unavailable_weekdays (employee_id, weekday) VALUES (?, ?)', (employee_id, weekday))

    cursor.execute('DELETE FROM employee_unavailable_dates WHERE employee_id = ?', (employee_id,))
    for entry in data.get('unavailable_dates') or []:
        iso_date = entry['date'] if isinstance(entry, dict) else entry
        reason = entry.get('reason') if isinstance(entry, dict) else None
        iso_date = parse_iso_date(iso_date)
        cursor.execute('INSERT INTO employee_unavailable_dates (employee_id, date, reason) VALUES (?, ?, ?)', (employee_id, iso_date, reason))

    cursor.execute('DELETE FROM employee_allowed_shift_types WHERE employee_id = ?', (employee_id,))
    for shift_type_id in parse_int_list(data.get('allowed_shift_types')):
        cursor.execute('INSERT INTO employee_allowed_shift_types (employee_id, shift_type_id) VALUES (?, ?)', (employee_id, shift_type_id))

    replace_employee_availability(cursor, employee_id, data.get('availability'))


def replace_employee_availability(cursor, employee_id, entries):
    """Replace one employee's working-time windows, and nothing else.

    Split out of replace_employee_constraints() above so that
    PUT /employees/<id>/availability can reuse the validation without
    inheriting its neighbours: that function clears every constraint list
    before rewriting it, so calling it with only an `availability` key would
    silently drop the employee's free weekdays, blocked dates and allowed
    shift types - a route that changes more than its name says.
    """
    cursor.execute('DELETE FROM employee_availability WHERE employee_id = ?', (employee_id,))
    for entry in entries or []:
        if not isinstance(entry, dict):
            raise ValueError(t(g.lang, 'availability_entry_invalid'))
        weekday = parse_weekday(entry.get('weekday'))

        start_time = entry.get('start_time')
        end_time = entry.get('end_time')
        if not valid_time(start_time):
            raise ValueError(t(g.lang, 'availability_time_invalid', value=start_time))
        if not valid_time(end_time):
            raise ValueError(t(g.lang, 'availability_time_invalid', value=end_time))
        if start_time == end_time:
            raise ValueError(t(g.lang, 'availability_window_empty'))

        # Normalising is also what keeps the valid_until < valid_from
        # comparison below honest, since it compares the same two strings.
        valid_from, valid_until = (
            parse_iso_date(bound) if bound is not None else None
            for bound in (entry.get('valid_from'), entry.get('valid_until')))
        if valid_from and valid_until and valid_until < valid_from:
            raise ValueError(t(g.lang, 'availability_valid_range_invalid'))

        cursor.execute(
            'INSERT INTO employee_availability (employee_id, weekday, start_time, end_time, valid_from, valid_until) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (employee_id, weekday, start_time, end_time, valid_from, valid_until),
        )


def serialize_shift_type(cursor, row):
    """A shift type is a template and nothing more: name, hours, colour.

    The per-weekday head counts it used to carry moved to
    coverage_requirements in Etappe 3 and stopped being read by the planner in
    Etappe 4; the table behind them is gone since 0010. The cursor argument
    stays for the sake of every caller's signature - and because a shift type
    may well grow something worth a second query again.
    """
    return {
        'id': row['id'],
        'name': row['name'],
        'start_time': row['start_time'],
        'end_time': row['end_time'],
        'color': row['color'],
    }


# ---------- employees ----------

@app.route('/employees', methods=['GET'])
@hr_required
def list_employees():
    # HR-only: an employee account is shown its own shifts, which already carry
    # the shift name and hours, so it never needs the roster - and the roster is
    # colleagues' personal data.
    connection = get_db()
    cursor = connection.cursor()
    # Anonymised rows are tombstones, not staff: their assignments still hang
    # off them so the working-time record stays whole (§ 16 Abs. 2 ArbZG), but
    # offering them for editing or counting them as headcount would be wrong.
    cursor.execute('SELECT * FROM employees WHERE anonymized_at IS NULL ORDER BY name')
    employees = [serialize_employee(cursor, row) for row in cursor.fetchall()]
    return jsonify(employees)


@app.route('/employees', methods=['POST'])
@hr_required
def create_employee():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'message': t(g.lang, 'name_required')}), 400

    connection = get_db()
    try:
        cursor = connection.cursor()
        weekly_hours = parse_optional_hours(data.get('weekly_hours'), 'weekly_hours_label')
        min_rest_hours = parse_optional_hours(data.get('min_rest_hours'), 'min_rest_hours_label')
        max_daily_hours = parse_daily_hours(data.get('max_daily_hours'))
        availability_mode = data.get('availability_mode') or 'anytime'
        if availability_mode not in ('anytime', 'windows'):
            raise ValueError(t(g.lang, 'availability_mode_invalid'))
        cursor.execute(
            'INSERT INTO employees (name, email, active, max_shifts_per_month, weekly_hours, min_rest_hours, max_daily_hours, availability_mode) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (name, data.get('email'), 1 if data.get('active', True) else 0, data.get('max_shifts_per_month'),
             weekly_hours, min_rest_hours if min_rest_hours is not None else 11,
             max_daily_hours if max_daily_hours is not None else 10, availability_mode),
        )
        employee_id = cursor.lastrowid
        replace_employee_constraints(connection, employee_id, data)
        connection.commit()
        cursor.execute('SELECT * FROM employees WHERE id = ?', (employee_id,))
        employee = serialize_employee(cursor, cursor.fetchone())
    except ValueError as e:
        return jsonify({'message': str(e)}), 400
    return jsonify(employee), 201


@app.route('/employees/<int:employee_id>', methods=['GET'])
@hr_required
def get_employee(employee_id):
    connection = get_db()
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM employees WHERE id = ?', (employee_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'message': t(g.lang, 'employee_not_found')}), 404
    employee = serialize_employee(cursor, row)
    return jsonify(employee)


@app.route('/employees/<int:employee_id>', methods=['PUT'])
@hr_required
def update_employee(employee_id):
    data = request.get_json(silent=True) or {}
    connection = get_db()
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM employees WHERE id = ?', (employee_id,))
    if not cursor.fetchone():
        return jsonify({'message': t(g.lang, 'employee_not_found')}), 404

    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'message': t(g.lang, 'name_required')}), 400

    try:
        weekly_hours = parse_optional_hours(data.get('weekly_hours'), 'weekly_hours_label')
        min_rest_hours = parse_optional_hours(data.get('min_rest_hours'), 'min_rest_hours_label')
        max_daily_hours = parse_daily_hours(data.get('max_daily_hours'))
        availability_mode = data.get('availability_mode') or 'anytime'
        if availability_mode not in ('anytime', 'windows'):
            raise ValueError(t(g.lang, 'availability_mode_invalid'))
        cursor.execute(
            'UPDATE employees SET name = ?, email = ?, active = ?, max_shifts_per_month = ?, '
            'weekly_hours = ?, min_rest_hours = ?, max_daily_hours = ?, availability_mode = ? WHERE id = ?',
            (name, data.get('email'), 1 if data.get('active', True) else 0, data.get('max_shifts_per_month'),
             weekly_hours, min_rest_hours if min_rest_hours is not None else 11,
             max_daily_hours if max_daily_hours is not None else 10, availability_mode, employee_id),
        )
        replace_employee_constraints(connection, employee_id, data)
        connection.commit()
        cursor.execute('SELECT * FROM employees WHERE id = ?', (employee_id,))
        employee = serialize_employee(cursor, cursor.fetchone())
    except ValueError as e:
        return jsonify({'message': str(e)}), 400
    return jsonify(employee)


@app.route('/employees/<int:employee_id>/availability', methods=['GET'])
def get_employee_availability(employee_id):
    """An employee's own working-time windows, readable by them and by HR.

    Spec §6 asked for this route from the start; the windows ended up hanging
    off PUT /employees/<id> (@hr_required) instead, which meant the one person
    the windows are about could not see them. Etappe 4 turns the windows into
    what the planner cuts blocks against, so that gap stops being cosmetic.

    Writing stays HR-only (see the PUT below): an employee announcing their own
    availability is a different feature - a request someone approves - not this
    one.
    """
    error = require_self_or_hr(employee_id)
    if error:
        return error

    cursor = get_db().cursor()
    cursor.execute('SELECT * FROM employees WHERE id = ?', (employee_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'message': t(g.lang, 'employee_not_found')}), 404

    employee = serialize_employee(cursor, row)
    return jsonify({
        'availability_mode': employee['availability_mode'],
        'availability': employee['availability'],
    })


@app.route('/employees/<int:employee_id>/availability', methods=['PUT'])
@hr_required
def put_employee_availability(employee_id):
    """Replace one employee's windows without touching the rest of their record.

    Same replace-completely semantics as the constraint lists on
    PUT /employees/<id>, and the same writer: replace_employee_availability()
    is the only place that validates and stores windows, so this route hands
    the payload straight to it rather than growing a second copy of that
    validation.
    """
    connection = get_db()
    cursor = connection.cursor()
    cursor.execute('SELECT id FROM employees WHERE id = ?', (employee_id,))
    if not cursor.fetchone():
        return jsonify({'message': t(g.lang, 'employee_not_found')}), 404

    data = request.get_json(silent=True)
    # A JSON array parses fine and then has no .get, which used to surface as a
    # 500 - "the server is broken" for something the caller got wrong.
    if not isinstance(data, dict):
        return jsonify({'message': t(g.lang, 'request_body_must_be_object')}), 400
    availability_mode = data.get('availability_mode') or 'anytime'
    if availability_mode not in ('anytime', 'windows'):
        return jsonify({'message': t(g.lang, 'availability_mode_invalid')}), 400

    try:
        replace_employee_availability(cursor, employee_id, data.get('availability'))
    except ValueError as e:
        return jsonify({'message': str(e)}), 400

    cursor.execute('UPDATE employees SET availability_mode = ? WHERE id = ?',
                   (availability_mode, employee_id))
    connection.commit()

    cursor.execute('SELECT * FROM employees WHERE id = ?', (employee_id,))
    employee = serialize_employee(cursor, cursor.fetchone())
    return jsonify({
        'availability_mode': employee['availability_mode'],
        'availability': employee['availability'],
    })


@app.route('/employees/<int:employee_id>', methods=['DELETE'])
@hr_required
def delete_employee(employee_id):
    connection = get_db()
    cursor = connection.cursor()
    cursor.execute('SELECT id FROM employees WHERE id = ?', (employee_id,))
    if not cursor.fetchone():
        return jsonify({'message': t(g.lang, 'employee_not_found')}), 404

    # Deleting the roster entry out from under a login would leave an account
    # that still works but can never show anything, so the account goes first.
    cursor.execute('SELECT username FROM users WHERE employee_id = ?', (employee_id,))
    linked = [row['username'] for row in cursor.fetchall()]
    if linked:
        return jsonify({'message': t(g.lang, 'delete_linked_account_first', accounts=', '.join(linked))}), 400

    # Anonymised, not deleted. ON DELETE SET NULL would turn this person's past
    # shifts into unfilled ones - the past would read as understaffed, coverage
    # gaps would appear retroactively, and the working-time record § 16 Abs. 2
    # ArbZG requires would lose the very attribution that makes it one.
    #
    # Art. 17 Abs. 3 lit. b DSGVO exempts processing needed to comply with a
    # legal obligation, and § 16 Abs. 2 is one. What stays is the working-time
    # record without a person; what goes is the person.
    for statement in (
        'DELETE FROM employee_availability WHERE employee_id = ?',
        'DELETE FROM employee_unavailable_weekdays WHERE employee_id = ?',
        'DELETE FROM employee_unavailable_dates WHERE employee_id = ?',
        'DELETE FROM employee_allowed_shift_types WHERE employee_id = ?',
        'DELETE FROM employee_absences WHERE employee_id = ?',
    ):
        cursor.execute(statement, (employee_id,))

    # The absence reason lives in two places: employee_absences, cleared above,
    # and denormalised into the assignment it freed. Clearing only the table
    # would leave the health note - with the person attached - sitting in the
    # roster until the retention period catches it months later.
    #
    # The assignment itself stays. Deleting the cover shift would rewrite the
    # working-time record § 16 Abs. 2 ArbZG requires.
    cursor.execute(
        'UPDATE shift_assignments SET absence_type = NULL, absent_employee_id = NULL '
        'WHERE absent_employee_id = ?', (employee_id,))

    cursor.execute(
        'UPDATE employees SET name = ?, email = NULL, active = 0, '
        'anonymized_at = CURRENT_TIMESTAMP WHERE id = ?',
        (t(g.lang, 'anonymised_employee_name', id=employee_id), employee_id))
    connection.commit()
    return jsonify({'message': t(g.lang, 'employee_anonymised')}), 200


# ---------- GDPR: access, erasure, retention ----------
#
# Two decisions came from the operator: six months of retention, and erasure by
# anonymisation. Both shape what follows.

# § 16 Abs. 2 ArbZG requires records of working time beyond eight hours a day
# to be kept for at least two years, so the retention period deliberately does
# *not* touch assignments or schedules. Deleting a month with ten-hour days
# after six months would be breaking one rule in order to keep another.
RETENTION_DEFAULT_MONTHS = 6


def retention_months(cursor):
    """How long absences and log entries are kept, in months."""
    stored = read_settings(cursor).get('retention_months')
    try:
        months = int(stored)
    except (TypeError, ValueError):
        return RETENTION_DEFAULT_MONTHS
    return months if months > 0 else RETENTION_DEFAULT_MONTHS


def retention_cutoff(cursor):
    """The date before which the personal extras are removed.

    Months as 30 days each rather than calendar arithmetic: the difference is
    at most a couple of days on a six-month period, and a cutoff that lands on
    the same day of the month is not worth a dependency or a leap-year branch.
    """
    return (date.today() - timedelta(days=30 * retention_months(cursor))).isoformat()


def purge_expired_personal_data(cursor):
    """Remove what the retention period no longer covers.

    Three places, and the third is the one that gets missed: an absence is
    recorded in employee_absences *and* denormalised into the assignment it
    freed (absence_type, absent_employee_id). Clearing only the table would
    leave the health note sitting in the roster.

    Assignments themselves are never touched - see RETENTION_DEFAULT_MONTHS.
    """
    cutoff = retention_cutoff(cursor)
    removed = {}

    cursor.execute('DELETE FROM employee_absences WHERE date < ?', (cutoff,))
    removed['absences'] = cursor.rowcount

    cursor.execute(
        'UPDATE shift_assignments SET absence_type = NULL, absent_employee_id = NULL '
        'WHERE date < ? AND absence_type IS NOT NULL', (cutoff,))
    removed['assignment_absence_marks'] = cursor.rowcount

    cursor.execute('DELETE FROM audit_log WHERE at < ?', (cutoff,))
    removed['audit_entries'] = cursor.rowcount

    return removed


@app.route('/retention/purge', methods=['POST'])
@hr_required
def purge_retention():
    """Run the clean-up now, and say what it did.

    There is no scheduler: the hosting plan in use offers none, and pretending
    otherwise would be worse than saying so. The purge also runs at startup,
    which in practice means on every deploy. An instance left running for
    months without a restart will not clean up on its own until someone presses
    this - which is exactly why it reports counts rather than a bare "done".
    """
    connection = get_db()
    cursor = connection.cursor()
    removed = purge_expired_personal_data(cursor)
    connection.commit()
    return jsonify({
        'message': t(g.lang, 'retention_purged'),
        'retention_months': retention_months(cursor),
        'removed': removed,
    })


@app.route('/employees/<int:employee_id>/data-export', methods=['GET'])
def export_employee_data(employee_id):
    """Everything this tool knows about one person, as JSON (Art. 15 DSGVO).

    Self-or-HR, the same rule the absences and availability windows follow.

    JSON rather than PDF: Art. 15 Abs. 3 asks for "a commonly used electronic
    format", JSON is one, and the alternative would be a dependency bought for
    the sake of looking like paper.
    """
    error = require_self_or_hr(employee_id)
    if error:
        return error

    cursor = get_db().cursor()
    cursor.execute('SELECT * FROM employees WHERE id = ?', (employee_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'message': t(g.lang, 'employee_not_found')}), 404

    employee = serialize_employee(cursor, row)

    cursor.execute(
        'SELECT date, absence_type FROM employee_absences WHERE employee_id = ? ORDER BY date',
        (employee_id,))
    absences = [dict(r) for r in cursor.fetchall()]

    cursor.execute(
        'SELECT sa.date, sa.start_time, sa.end_time, sa.break_minutes, st.name AS shift_type_name '
        'FROM shift_assignments sa LEFT JOIN shift_types st ON st.id = sa.shift_type_id '
        'WHERE sa.employee_id = ? ORDER BY sa.date, sa.start_time', (employee_id,))
    assignments = [dict(r) for r in cursor.fetchall()]

    # Never the password hash. It is the one field whose disclosure would make
    # the export itself a security problem.
    cursor.execute(
        'SELECT id, username, role, email, created_at FROM users WHERE employee_id = ?',
        (employee_id,))
    accounts = [dict(r) for r in cursor.fetchall()]

    log_entries = []
    if accounts:
        cursor.execute(
            'SELECT at, method, path, status FROM audit_log WHERE user_id IN '
            '(SELECT id FROM users WHERE employee_id = ?) ORDER BY at DESC',
            (employee_id,))
        log_entries = [dict(r) for r in cursor.fetchall()]

    return jsonify({
        'employee': employee,
        'absences': absences,
        'assignments': assignments,
        'accounts': accounts,
        'audit_log': log_entries,
    })


# ---------- self-service absences (sick / vacation) ----------
#
# The one deliberate exception to "employee accounts are read-only" (see
# require_self_or_hr above): an employee may report their own sick/vacation
# days, but only for the current month. This immediately frees any shift they
# currently hold that day - it starts behaving like any other unfilled slot -
# while employee_absences also feeds load_employees_for_scheduling() so a
# later regeneration doesn't schedule them straight back onto it.

ABSENCE_TYPES = ('sick', 'vacation')


def current_month_bounds():
    """The server's own idea of "this month", as (first day, last day) ISO strings.

    Never derived from client input - self-service reporting is only ever
    allowed for the month the server's clock says it is right now. Die Zone
    kommt aus timeutil, nicht aus der Serverzeitzone: siehe dortiger
    Modulkommentar.
    """
    return timeutil.month_bounds(timeutil.today_local())


@app.route('/employees/<int:employee_id>/absences', methods=['GET'])
def list_absences(employee_id):
    error = require_self_or_hr(employee_id)
    if error:
        return error

    try:
        heute = timeutil.today_local()
        year = int(request.args['year']) if 'year' in request.args else heute.year
        month = int(request.args['month']) if 'month' in request.args else heute.month
    except (TypeError, ValueError):
        return jsonify({'message': t(g.lang, 'year_month_must_be_numbers')}), 400
    if not 1 <= month <= 12:
        return jsonify({'message': t(g.lang, 'month_out_of_range')}), 400

    connection = get_db()
    cursor = connection.cursor()
    days_in_month = calendar.monthrange(year, month)[1]
    cursor.execute(
        'SELECT date, absence_type FROM employee_absences WHERE employee_id = ? AND date BETWEEN ? AND ? ORDER BY date',
        (employee_id, date(year, month, 1).isoformat(), date(year, month, days_in_month).isoformat()),
    )
    return jsonify([{'date': row['date'], 'type': row['absence_type']} for row in cursor.fetchall()])


@app.route('/employees/<int:employee_id>/absences', methods=['POST'])
def report_absence(employee_id):
    error = require_self_or_hr(employee_id)
    if error:
        return error

    data = request.get_json(silent=True) or {}
    iso_date = data.get('date')
    absence_type = data.get('type')

    try:
        iso_date = parse_iso_date(iso_date)
    except ValueError:
        return jsonify({'message': t(g.lang, 'invalid_date')}), 400
    if absence_type not in ABSENCE_TYPES:
        return jsonify({'message': t(g.lang, 'absence_type_invalid')}), 400

    if not is_hr(g.user):
        month_start, month_end = current_month_bounds()
        if not (month_start <= iso_date <= month_end):
            return jsonify({'message': t(g.lang, 'absence_current_month_only')}), 400

    connection = get_db()
    cursor = connection.cursor()
    cursor.execute('SELECT id, name FROM employees WHERE id = ?', (employee_id,))
    employee = cursor.fetchone()
    if not employee:
        return jsonify({'message': t(g.lang, 'employee_not_found')}), 404

    cursor.execute('''
        INSERT INTO employee_absences (employee_id, date, absence_type) VALUES (?, ?, ?)
        ON CONFLICT(employee_id, date) DO UPDATE SET absence_type = excluded.absence_type
    ''', (employee_id, iso_date, absence_type))

    # Free any shift they currently hold that day - "the shift becomes free in
    # the general plan". absent_employee_id remembers who it was.
    cursor.execute(
        'SELECT id, schedule_id FROM shift_assignments WHERE date = ? AND employee_id = ?',
        (iso_date, employee_id),
    )
    freed = cursor.fetchall()
    for row in freed:
        cursor.execute(
            'UPDATE shift_assignments SET employee_id = NULL, absence_type = ?, absent_employee_id = ?, '
            'manually_edited = 1 WHERE id = ?',
            (absence_type, employee_id, row['id']),
        )
        refresh_unfilled_count(cursor, row['schedule_id'])

    # A slot this same report already freed earlier (e.g. the type changed
    # from vacation to sick) just needs its type updated, not re-freeing.
    cursor.execute(
        'UPDATE shift_assignments SET absence_type = ? WHERE date = ? AND absent_employee_id = ? AND employee_id IS NULL',
        (absence_type, iso_date, employee_id),
    )

    connection.commit()
    return jsonify({
        'date': iso_date,
        'type': absence_type,
        'freed_assignment_ids': [row['id'] for row in freed],
    }), 201


@app.route('/employees/<int:employee_id>/absences/<iso_date>', methods=['DELETE'])
def cancel_absence(employee_id, iso_date):
    error = require_self_or_hr(employee_id)
    if error:
        return error

    try:
        iso_date = parse_iso_date(iso_date)
    except ValueError:
        return jsonify({'message': t(g.lang, 'invalid_date')}), 400

    if not is_hr(g.user):
        month_start, month_end = current_month_bounds()
        if not (month_start <= iso_date <= month_end):
            return jsonify({'message': t(g.lang, 'absence_current_month_only')}), 400

    connection = get_db()
    cursor = connection.cursor()
    cursor.execute('SELECT id FROM employee_absences WHERE employee_id = ? AND date = ?', (employee_id, iso_date))
    if not cursor.fetchone():
        return jsonify({'message': t(g.lang, 'absence_not_found')}), 404

    cursor.execute('DELETE FROM employee_absences WHERE employee_id = ? AND date = ?', (employee_id, iso_date))

    cursor.execute(
        'SELECT id, schedule_id, employee_id FROM shift_assignments WHERE date = ? AND absent_employee_id = ?',
        (iso_date, employee_id),
    )
    for row in cursor.fetchall():
        if row['employee_id'] is None:
            # Nobody has covered it yet - give the shift back to them.
            cursor.execute(
                'UPDATE shift_assignments SET employee_id = ?, absence_type = NULL, absent_employee_id = NULL WHERE id = ?',
                (employee_id, row['id']),
            )
            refresh_unfilled_count(cursor, row['schedule_id'])
        else:
            # Someone already covers this shift - leave their assignment
            # alone, just stop pointing at an absence record that no longer exists.
            cursor.execute(
                'UPDATE shift_assignments SET absence_type = NULL, absent_employee_id = NULL WHERE id = ?',
                (row['id'],),
            )

    connection.commit()
    return jsonify({'message': t(g.lang, 'absence_removed')}), 200


@app.route('/audit-log', methods=['GET'])
@hr_required
def get_audit_log():
    """The most recent entries, newest first.

    Read-only on purpose: there is no route to clear it. Something that empties
    at the press of a button is not a log. Retention comes with the GDPR work,
    and then as a period rather than a button.
    """
    try:
        limit = min(int(request.args.get('limit', AUDIT_LIMIT_DEFAULT)), AUDIT_LIMIT_MAX)
    except (TypeError, ValueError):
        return jsonify({'message': t(g.lang, 'limit_must_be_int')}), 400
    if limit < 1:
        return jsonify({'message': t(g.lang, 'limit_must_be_int')}), 400

    cursor = get_db().cursor()
    cursor.execute(
        'SELECT at, user_id, username, method, path, status FROM audit_log '
        'ORDER BY at DESC, id DESC LIMIT ?', (limit,))
    return jsonify([dict(row) for row in cursor.fetchall()])


# ---------- accounts ----------

@app.route('/accounts', methods=['GET'])
@hr_required
def list_accounts():
    connection = get_db()
    cursor = connection.cursor()
    cursor.execute('''
        SELECT u.id, u.username, u.role, u.employee_id, u.created_at,
               e.name AS employee_name,
               -- An employee's address lives on the roster entry, HR's on the
               -- account itself; the UI just needs to know where mail would go.
               COALESCE(e.email, u.email) AS contact_email,
               (u.hash != '') AS password_set,
               (i.id IS NOT NULL) AS invitation_pending
        FROM users u
        LEFT JOIN employees e ON e.id = u.employee_id
        LEFT JOIN password_invitations i ON i.user_id = u.id
        ORDER BY u.role, u.username
    ''')
    accounts = []
    for row in cursor.fetchall():
        account = dict(row)
        account['password_set'] = bool(account['password_set'])
        account['invitation_pending'] = bool(account['invitation_pending'])
        accounts.append(account)
    return jsonify(accounts)


@app.route('/accounts/<int:account_id>/invitation', methods=['POST'])
@hr_required
def resend_invitation(account_id):
    """Send a fresh invitation, e.g. when the first one expired or went astray."""
    connection = get_db()
    cursor = connection.cursor()
    cursor.execute('SELECT id, username, role, employee_id, email, hash FROM users WHERE id = ?', (account_id,))
    account = cursor.fetchone()
    if not account:
        return jsonify({'message': t(g.lang, 'account_not_found')}), 404

    recipient_email, _ = invitation_recipient(cursor, account)
    if not recipient_email:
        return jsonify({'message': t(g.lang, 'account_missing_email')}), 400

    token = issue_invitation(cursor, account_id)
    # Re-inviting also revokes the current password, so a forgotten one can be
    # replaced without HR ever setting it.
    cursor.execute("UPDATE users SET hash = '' WHERE id = ?", (account_id,))
    connection.commit()

    sent = mailer.send_invitation(recipient_email, account['username'], token, INVITATION_VALID_DAYS, lang=g.lang)
    message_key = 'invitation_email_sent' if sent else 'invitation_logged'
    return jsonify({
        'message': t(g.lang, message_key, email=recipient_email),
        'invitation_sent': sent,
    }), 200


@app.route('/accounts/<int:account_id>', methods=['DELETE'])
@hr_required
def delete_account(account_id):
    if account_id == g.user['id']:
        # Deleting the account you are signed in with would lock you out mid-session.
        return jsonify({'message': t(g.lang, 'cannot_delete_own_account')}), 400

    connection = get_db()
    cursor = connection.cursor()
    cursor.execute('SELECT id, username, role FROM users WHERE id = ?', (account_id,))
    account = cursor.fetchone()
    if not account:
        return jsonify({'message': t(g.lang, 'account_not_found')}), 404

    if account['role'] == HR_ROLE:
        cursor.execute('SELECT COUNT(*) AS n FROM users WHERE role = ?', (HR_ROLE,))
        if cursor.fetchone()['n'] <= 1:
            # Without an HR account nobody could administer the tool again.
            return jsonify({'message': t(g.lang, 'cannot_delete_last_hr_account')}), 400

    cursor.execute('DELETE FROM users WHERE id = ?', (account_id,))
    connection.commit()
    return jsonify({'message': t(g.lang, 'account_deleted', username=account['username'])}), 200


# ---------- shift types ----------

@app.route('/shift-types', methods=['GET'])
@login_required
def list_shift_types():
    connection = get_db()
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM shift_types ORDER BY start_time')
    shift_types = [serialize_shift_type(cursor, row) for row in cursor.fetchall()]
    return jsonify(shift_types)


@app.route('/shift-types', methods=['POST'])
@hr_required
def create_shift_type():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    start_time = data.get('start_time')
    end_time = data.get('end_time')
    if not name or not start_time or not end_time:
        return jsonify({'message': t(g.lang, 'shift_type_fields_required')}), 400

    connection = get_db()
    try:
        cursor = connection.cursor()
        cursor.execute(
            'INSERT INTO shift_types (name, start_time, end_time, color) VALUES (?, ?, ?, ?)',
            (name, start_time, end_time, data.get('color') or '#0d9488'),
        )
        shift_type_id = cursor.lastrowid
        connection.commit()
        cursor.execute('SELECT * FROM shift_types WHERE id = ?', (shift_type_id,))
        shift_type = serialize_shift_type(cursor, cursor.fetchone())
    except ValueError as e:
        return jsonify({'message': str(e)}), 400
    return jsonify(shift_type), 201


@app.route('/shift-types/<int:shift_type_id>', methods=['PUT'])
@hr_required
def update_shift_type(shift_type_id):
    data = request.get_json(silent=True) or {}
    connection = get_db()
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM shift_types WHERE id = ?', (shift_type_id,))
    if not cursor.fetchone():
        return jsonify({'message': t(g.lang, 'shift_type_not_found')}), 404

    name = (data.get('name') or '').strip()
    start_time = data.get('start_time')
    end_time = data.get('end_time')
    if not name or not start_time or not end_time:
        return jsonify({'message': t(g.lang, 'shift_type_fields_required')}), 400

    try:
        cursor.execute(
            'UPDATE shift_types SET name = ?, start_time = ?, end_time = ?, color = ? WHERE id = ?',
            (name, start_time, end_time, data.get('color') or '#0d9488', shift_type_id),
        )
        connection.commit()
        cursor.execute('SELECT * FROM shift_types WHERE id = ?', (shift_type_id,))
        shift_type = serialize_shift_type(cursor, cursor.fetchone())
    except ValueError as e:
        return jsonify({'message': str(e)}), 400
    return jsonify(shift_type)


@app.route('/shift-types/<int:shift_type_id>', methods=['DELETE'])
@hr_required
def delete_shift_type(shift_type_id):
    connection = get_db()
    cursor = connection.cursor()
    cursor.execute('SELECT id FROM shift_types WHERE id = ?', (shift_type_id,))
    if not cursor.fetchone():
        return jsonify({'message': t(g.lang, 'shift_type_not_found')}), 404

    cursor.execute('SELECT COUNT(*) AS n FROM shift_assignments WHERE shift_type_id = ?', (shift_type_id,))
    if cursor.fetchone()['n'] > 0:
        return jsonify({'message': t(g.lang, 'shift_type_in_use')}), 400

    cursor.execute('DELETE FROM shift_types WHERE id = ?', (shift_type_id,))
    connection.commit()
    return jsonify({'message': t(g.lang, 'shift_type_deleted')}), 200


# ---------- schedules ----------

def scheduling_history(cursor, employee_id, year, month):
    """The two facts about an employee's past that the planner needs.

    Returns (days_worked_before_month, sundays_worked_in_year).

    Bounded by the *date range* of the month being planned, never by
    schedule_id: generate_schedule_route() deletes the month's assignments only
    after the search has run, so they are still in the database while this
    loads. Counting them would dock everyone for shifts the very same request
    is about to take away - someone with four Sundays in the current August
    plan would have their yearly budget cut by four, for a plan being replaced.
    A date inside the target month belongs to that month, whatever schedule row
    it happens to hang off.

    Both are counted over distinct *dates*, not assignments: a split shift with
    two blocks does not make a day into two days.
    """
    first_of_month = date(year, month, 1)
    last_of_month = date(year, month, calendar.monthrange(year, month)[1])

    cursor.execute(
        'SELECT DISTINCT date FROM shift_assignments '
        'WHERE employee_id = ? AND date BETWEEN ? AND ? AND (date < ? OR date > ?)',
        (employee_id, date(year, 1, 1).isoformat(), date(year, 12, 31).isoformat(),
         first_of_month.isoformat(), last_of_month.isoformat()),
    )
    dates_in_year = {row['date'] for row in cursor.fetchall()}

    sundays = sum(1 for iso in dates_in_year if date.fromisoformat(iso).weekday() == 6)

    # Counting back from the day before the month starts. Stopping at
    # MAX_CONSECUTIVE_DAYS is not an optimisation but the whole truth that
    # matters: a run already at the limit blocks the first of the month no
    # matter how much longer it really is.
    run = 0
    cursor_date = first_of_month - timedelta(days=1)
    while run < MAX_CONSECUTIVE_DAYS and cursor_date.isoformat() in dates_in_year:
        run += 1
        cursor_date -= timedelta(days=1)

    return run, sundays


def sundays_in_year(year):
    """52 or 53 - computed rather than assumed; the difference is one Sunday of
    everyone's yearly budget."""
    return sum(
        1 for offset in range((date(year + 1, 1, 1) - date(year, 1, 1)).days)
        if (date(year, 1, 1) + timedelta(days=offset)).weekday() == 6
    )


def worked_dates_for(cursor, employee_id, first_date, last_date, exclude_assignment_id):
    """Distinct calendar dates this employee holds a block on, within a range.

    Distinct dates rather than assignments: a split shift with two blocks does
    not make a day into two days.
    """
    query = ('SELECT DISTINCT date FROM shift_assignments '
             'WHERE employee_id = ? AND date BETWEEN ? AND ?')
    params = [employee_id, first_date, last_date]
    if exclude_assignment_id is not None:
        query += ' AND id != ?'
        params.append(exclude_assignment_id)
    cursor.execute(query, params)
    return {row['date'] for row in cursor.fetchall()}


def consecutive_days_around(cursor, employee_id, assignment_date, exclude_assignment_id):
    """Length of the run of worked days this assignment would sit in.

    Counted in both directions over saved data, so unlike the generator this
    sees past the end of the month as well - which is exactly why the manual
    path is the stricter of the two. Bounded to a fortnight either side: a run
    longer than that is already far past the point where the warning fires.
    """
    d = date.fromisoformat(assignment_date)
    worked = worked_dates_for(
        cursor, employee_id,
        (d - timedelta(days=14)).isoformat(), (d + timedelta(days=14)).isoformat(),
        exclude_assignment_id,
    )

    run = 1
    for direction in (-1, 1):
        cursor_date = d + timedelta(days=direction)
        while cursor_date.isoformat() in worked:
            run += 1
            cursor_date += timedelta(days=direction)
    return run


def sundays_worked_in_year(cursor, employee_id, year, except_date, exclude_assignment_id):
    """Distinct Sundays already worked this year, leaving out one date.

    `except_date` is the one being decided: a second block on a Sunday someone
    already works must not count twice (§ 11 Abs. 1 asks whether the day is
    free, not how many blocks are on it).
    """
    worked = worked_dates_for(
        cursor, employee_id,
        date(year, 1, 1).isoformat(), date(year, 12, 31).isoformat(),
        exclude_assignment_id,
    )
    return sum(1 for iso in worked
               if iso != except_date and date.fromisoformat(iso).weekday() == 6)


def load_employees_for_scheduling(cursor, year=None, month=None):
    cursor.execute('SELECT * FROM employees WHERE active = 1')
    employees = []
    for row in cursor.fetchall():
        employee_id = row['id']
        cursor.execute('SELECT weekday FROM employee_unavailable_weekdays WHERE employee_id = ?', (employee_id,))
        unavailable_weekdays = {r['weekday'] for r in cursor.fetchall()}
        cursor.execute('SELECT date FROM employee_unavailable_dates WHERE employee_id = ?', (employee_id,))
        unavailable_dates = {r['date'] for r in cursor.fetchall()}
        # Self-reported sick/vacation days count as unavailable too, so a
        # regeneration doesn't schedule someone straight back onto a day they
        # already freed.
        cursor.execute('SELECT date FROM employee_absences WHERE employee_id = ?', (employee_id,))
        unavailable_dates |= {r['date'] for r in cursor.fetchall()}
        cursor.execute('SELECT shift_type_id FROM employee_allowed_shift_types WHERE employee_id = ?', (employee_id,))
        allowed = {r['shift_type_id'] for r in cursor.fetchall()}
        cursor.execute(
            'SELECT weekday, start_time, end_time, valid_from, valid_until FROM employee_availability WHERE employee_id = ?',
            (employee_id,),
        )
        availability = [
            {
                'weekday': r['weekday'],
                'start_time': r['start_time'],
                'end_time': r['end_time'],
                'valid_from': r['valid_from'],
                'valid_until': r['valid_until'],
            }
            for r in cursor.fetchall()
        ]
        employees.append({
            'id': employee_id,
            'max_shifts_per_month': row['max_shifts_per_month'],
            'weekly_hours': row['weekly_hours'],
            'min_rest_hours': row['min_rest_hours'],
            'max_daily_hours': row['max_daily_hours'],
            'unavailable_weekdays': unavailable_weekdays,
            'unavailable_dates': unavailable_dates,
            'allowed_shift_types': allowed if allowed else None,
            'availability_mode': row['availability_mode'],
            'availability': availability,
        })
        if year is not None and month is not None:
            before, sundays = scheduling_history(cursor, employee_id, year, month)
            employees[-1].update({
                'days_worked_before_month': before,
                'sundays_worked_in_year': sundays,
                # The law fixes the number; the planner enforces what it is
                # given, the same way min_rest_hours works. Supplying it here
                # is what turns the rule on for real data while leaving callers
                # that deal in shift counts alone.
                'max_consecutive_days': MAX_CONSECUTIVE_DAYS,
            })
    return employees


def load_shift_types_for_scheduling(cursor):
    cursor.execute('SELECT * FROM shift_types')
    shift_types = []
    for row in cursor.fetchall():
        shift_types.append({
            'id': row['id'],
            'start_time': row['start_time'],
            'end_time': row['end_time'],
        })
    return shift_types


def fetch_schedule(year, month):
    connection = get_db()
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM schedules WHERE year = ? AND month = ?', (year, month))
    schedule = cursor.fetchone()
    if not schedule:
        return None

    cursor.execute(
        'SELECT date, shift_type_id, start_time, end_time FROM shift_time_overrides WHERE schedule_id = ?',
        (schedule['id'],),
    )
    overrides = {(r['date'], r['shift_type_id']): dict(r) for r in cursor.fetchall()}

    cursor.execute('''
        SELECT sa.id, sa.date, sa.shift_type_id, sa.slot_index, sa.employee_id, sa.manually_edited,
               sa.absence_type, sa.absent_employee_id, sa.start_time, sa.end_time,
               sa.break_minutes,
               st.name AS shift_type_name, st.color AS shift_type_color,
               st.start_time AS type_start_time, st.end_time AS type_end_time,
               e.name AS employee_name, ae.name AS absent_employee_name
        FROM shift_assignments sa
        LEFT JOIN shift_types st ON st.id = sa.shift_type_id
        LEFT JOIN employees e ON e.id = sa.employee_id
        LEFT JOIN employees ae ON ae.id = sa.absent_employee_id
        WHERE sa.schedule_id = ?
        ORDER BY sa.date, COALESCE(sa.start_time, st.start_time), sa.slot_index
    ''', (schedule['id'],))

    assignments = []
    for row in cursor.fetchall():
        a = dict(row)
        a['manually_edited'] = bool(a['manually_edited'])
        # Three layers, outermost first: this assignment's own hours, then a
        # per-date override for the shift type, then the type's usual hours.
        # The flags tell the browser which layer won, so it can mark a cell
        # that deviates without re-deriving the rule.
        override = overrides.get((a['date'], a['shift_type_id']))
        a['default_start_time'] = a['type_start_time']
        a['default_end_time'] = a['type_end_time']
        a['assignment_time_set'] = bool(a['start_time'] and a['end_time'])
        a['time_overridden'] = override is not None
        if not a['assignment_time_set']:
            if override:
                a['start_time'] = override['start_time']
                a['end_time'] = override['end_time']
            else:
                a['start_time'] = a['type_start_time']
                a['end_time'] = a['type_end_time']
        # The break this block actually runs on: whatever someone entered, or
        # the legal minimum for the hours the three layers above settled on.
        # Resolved after them on purpose - the minimum depends on the span they
        # produce. Same shape as assignment_time_set/time_overridden: the
        # browser is told which layer won instead of re-deriving the rule.
        a['effective_break_minutes'] = (
            a['break_minutes'] if a['break_minutes'] is not None
            else legal_break_minutes(shift_duration_minutes(a['start_time'], a['end_time']))
            if a['start_time'] and a['end_time']
            else None
        )
        del a['type_start_time'], a['type_end_time']
        assignments.append(a)

    cursor.execute('SELECT id, name FROM employees WHERE active = 1 ORDER BY name')
    active_employees = cursor.fetchall()

    # This month's reported absences, including ones with no matching shift at
    # all (e.g. vacation reported before the day had anyone assigned) - the
    # assignments above only cover ones that *did* free a shift.
    days_in_month = calendar.monthrange(year, month)[1]
    cursor.execute('''
        SELECT ea.employee_id, e.name AS employee_name, ea.date, ea.absence_type
        FROM employee_absences ea
        JOIN employees e ON e.id = ea.employee_id
        WHERE ea.date BETWEEN ? AND ?
        ORDER BY ea.date
    ''', (date(year, month, 1).isoformat(), date(year, month, days_in_month).isoformat()))
    absences = [dict(row) for row in cursor.fetchall()]

    return {
        'id': schedule['id'],
        'year': schedule['year'],
        'month': schedule['month'],
        'status': schedule['status'],
        'published_at': schedule['published_at'],
        'unfilled_count': schedule['unfilled_count'],
        'generated_at': schedule['generated_at'],
        'assignments': assignments,
        'absences': absences,
        'distribution': build_distribution(assignments, active_employees),
        'coverage_gaps': coverage_gaps_for_month(cursor, year, month, assignments),
        'average_hours': average_hours_exceeded(cursor, year, month),
        'holidays': [{'date': tag.isoformat(), 'name': name}
                     for tag, name in holidays_for_month(cursor, year, month).items()],
    }


def build_distribution(assignments, active_employees):
    """Shifts per employee for the month, recomputed from what is actually stored.

    Deriving this from the saved assignments rather than from the generator means
    it stays honest after HR reassigns or swaps shifts by hand.
    """
    totals = {row['id']: {'employee_id': row['id'], 'name': row['name'], 'total': 0, 'weekend': 0}
              for row in active_employees}

    for a in assignments:
        employee_id = a['employee_id']
        if employee_id is None:
            continue
        entry = totals.setdefault(
            employee_id,
            # An employee who was deactivated after the plan was generated still
            # holds shifts in it, so they belong in the distribution.
            {'employee_id': employee_id, 'name': a['employee_name'] or f'#{employee_id}', 'total': 0, 'weekend': 0},
        )
        entry['total'] += 1
        if date.fromisoformat(a['date']).weekday() >= 5:
            entry['weekend'] += 1

    rows = sorted(totals.values(), key=lambda r: (-r['total'], r['name']))
    counts = [r['total'] for r in rows]
    weekend_counts = [r['weekend'] for r in rows]

    return {
        'per_employee': rows,
        'spread': (max(counts) - min(counts)) if counts else 0,
        'weekend_spread': (max(weekend_counts) - min(weekend_counts)) if weekend_counts else 0,
    }


@app.route('/schedules/generate', methods=['POST'])
@hr_required
def generate_schedule_route():
    data = request.get_json(silent=True) or {}
    try:
        year = int(data['year'])
        month = int(data['month'])
    except (KeyError, TypeError, ValueError):
        return jsonify({'message': t(g.lang, 'year_month_required')}), 400
    if not 1 <= month <= 12:
        return jsonify({'message': t(g.lang, 'month_out_of_range')}), 400

    # Optional: how strongly to even out weekend duty specifically, on top of
    # the total-shifts balancing that always runs (see scheduler.py). Off by
    # default so existing behaviour doesn't change under callers that don't
    # send it.
    weekend_weight = data.get('weekend_weight') or 0
    try:
        weekend_weight = float(weekend_weight)
        if weekend_weight != int(weekend_weight):
            raise ValueError()
        weekend_weight = int(weekend_weight)
    except (TypeError, ValueError):
        return jsonify({'message': t(g.lang, 'weekend_weight_must_be_int')}), 400
    if weekend_weight < 0:
        return jsonify({'message': t(g.lang, 'weekend_weight_must_not_be_negative')}), 400

    connection = get_db()
    cursor = connection.cursor()

    shift_types = load_shift_types_for_scheduling(cursor)
    if not shift_types:
        return jsonify({'message': t(g.lang, 'need_a_shift_type_first')}), 400

    employees = load_employees_for_scheduling(cursor, year, month)

    cursor.execute('SELECT id FROM schedules WHERE year = ? AND month = ?', (year, month))
    existing = cursor.fetchone()
    if existing:
        # Neuerzeugen verwirft jede Zuweisung des Monats, auch die von Hand
        # gesetzten. Ohne Rueckfrage waere das ein Klick, der stunden- bis
        # tagelange Nacharbeit still loescht - und es gibt kein Zurueck. Die
        # Pruefung steht bewusst vor dem Scheduler-Lauf: der hat ein
        # 8-Sekunden-Budget, das eine ohnehin abgelehnte Anfrage nicht
        # verbrauchen soll.
        cursor.execute(
            'SELECT COUNT(*) AS n FROM shift_assignments '
            'WHERE schedule_id = ? AND manually_edited = 1',
            (existing['id'],),
        )
        manually_edited = cursor.fetchone()['n']
        if manually_edited and not data.get('confirm'):
            return jsonify({
                'message': t(g.lang, 'regenerate_would_discard_edits', n=manually_edited),
                'manually_edited_count': manually_edited,
            }), 409

    # Stage 1: the month's blocks come out of the demand bands now, not out of
    # shift_requirements. The shift types still matter - stage 1 covers demand
    # with them wherever it can, so a normal month still looks like "2 early,
    # 3 midday, 2 late" - but their per-weekday counts are no longer read.
    try:
        slots = build_month_blocks(
            year, month, shift_types, effective_bands_by_date(cursor, year, month), employees)
        result = generate_schedule(year, month, employees, shift_types,
                                   weekend_weight=weekend_weight, slots=slots)
    except ValueError:
        return jsonify({'message': t(g.lang, 'invalid_year_or_month')}), 400

    if existing:
        schedule_id = existing['id']
        cursor.execute('DELETE FROM shift_assignments WHERE schedule_id = ?', (schedule_id,))
        cursor.execute(
            # Back to draft, deliberately. The plan HR published is not this
            # plan any more - regenerating discards every manual correction, and
            # leaving it published would slip employees a different roster than
            # the one they looked at. The response says so, so nobody has to
            # wonder where the plan went.
            "UPDATE schedules SET status = 'draft', published_at = NULL, "
            "unfilled_count = ?, generated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (result['unfilled_count'], schedule_id),
        )
    else:
        cursor.execute(
            "INSERT INTO schedules (year, month, status, unfilled_count, generated_at) "
            "VALUES (?, ?, 'draft', ?, CURRENT_TIMESTAMP)",
            (year, month, result['unfilled_count']),
        )
        schedule_id = cursor.lastrowid

    for a in result['assignments']:
        # start_time/end_time have been on this table since Etappe 2 but only
        # the manual-correction path ever filled them. Stage 1 decides a
        # block's hours now - trimmed to demand and to availability windows -
        # so they have to be stored, or the plan would read back at the shift
        # type's nominal times and the trimming would be invisible.
        cursor.execute(
            'INSERT INTO shift_assignments '
            '(schedule_id, date, shift_type_id, slot_index, employee_id, start_time, end_time) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (schedule_id, a['date'], a['shift_type_id'], a['slot_index'], a['employee_id'],
             a['start_time'], a['end_time']),
        )

    connection.commit()
    return jsonify(fetch_schedule(year, month)), 201


@app.route('/schedules/<int:year>/<int:month>', methods=['GET'])
@login_required
def get_schedule(year, month):
    schedule = fetch_schedule(year, month)
    if not schedule:
        return jsonify({'message': t(g.lang, 'no_schedule_generated_yet')}), 404

    if is_hr(g.user):
        schedule['scope'] = 'all'
        return jsonify(schedule)

    # A draft does not exist for employees - but with its own message. "There
    # is nothing" and "it is not ready yet" are two different answers, and the
    # second is the one that stops people asking.
    if schedule['status'] != SCHEDULE_PUBLISHED:
        return jsonify({'message': t(g.lang, 'schedule_not_published_yet')}), 404

    # An employee sees their own shifts and nothing else: not colleagues'
    # shifts, not gaps in the plan, and not the workload comparison, which is
    # a management view. Filtering happens here rather than in the browser so
    # the rest is never sent in the first place.
    linked_employee_id = g.user['employee_id']
    schedule['assignments'] = [
        a for a in schedule['assignments']
        # Own shifts as usual, plus own shifts freed by a reported absence -
        # employee_id is NULL on those, so they'd otherwise vanish from view
        # instead of showing as "Krank"/"Urlaub".
        if a['employee_id'] == linked_employee_id or a['absent_employee_id'] == linked_employee_id
    ]
    schedule['absences'] = [a for a in schedule['absences'] if a['employee_id'] == linked_employee_id]
    schedule.pop('distribution', None)
    schedule.pop('coverage_gaps', None)
    schedule['scope'] = 'own'
    schedule['unfilled_count'] = 0
    schedule['linked_employee_id'] = linked_employee_id

    return jsonify(schedule)


@app.route('/schedules/<int:year>/<int:month>/status', methods=['PUT'])
@hr_required
def set_schedule_status(year, month):
    """Publish a schedule, or pull it back to a draft.

    Setting the state it already has is not an error: that is idempotent and
    spares the caller a case distinction. published_at then stays where it was
    rather than moving - "since when have people been able to see this?" should
    not change just because someone pressed the button twice.
    """
    data = request.get_json(silent=True) or {}
    status = data.get('status')
    if status not in SCHEDULE_STATES:
        return jsonify({'message': t(g.lang, 'unknown_schedule_status',
                                     allowed=', '.join(SCHEDULE_STATES))}), 400

    connection = get_db()
    cursor = connection.cursor()
    cursor.execute('SELECT id, status FROM schedules WHERE year = ? AND month = ?', (year, month))
    row = cursor.fetchone()
    if not row:
        return jsonify({'message': t(g.lang, 'no_schedule_found')}), 404

    if status == SCHEDULE_PUBLISHED and row['status'] != SCHEDULE_PUBLISHED:
        cursor.execute(
            'UPDATE schedules SET status = ?, published_at = CURRENT_TIMESTAMP WHERE id = ?',
            (status, row['id']))
    elif status == SCHEDULE_DRAFT:
        cursor.execute(
            'UPDATE schedules SET status = ?, published_at = NULL WHERE id = ?',
            (status, row['id']))
    connection.commit()

    return jsonify(fetch_schedule(year, month))


def _export_rows(year, month, employee_id=None):
    """The month's assignments in the shape both exporters expect.

    Goes through fetch_schedule() rather than its own query: the hours there
    are already resolved through the three layers, and a second query would be
    a second chance to resolve them differently.
    """
    schedule = fetch_schedule(year, month)
    if not schedule:
        return None, None

    rows = []
    for a in schedule['assignments']:
        if employee_id is not None and a['employee_id'] != employee_id:
            continue
        working = None
        if a['start_time'] and a['end_time']:
            working = round(net_working_minutes(
                shift_duration_minutes(a['start_time'], a['end_time']),
                a['break_minutes']) / 60, 2)
        rows.append({**a, 'working_hours': '' if working is None else working})
    return schedule, rows


@app.route('/employees/<int:employee_id>/schedule.ics', methods=['GET'])
def export_employee_ical(employee_id):
    """One employee's shifts for a month, as an iCal file.

    Self-or-HR, the same rule the absences and availability windows follow.

    **Published plans only, for HR too.** A draft does not exist for employees
    since the publishing stage, and an export that handed one out anyway would
    be the back door beside that wall. HR is included because the file's
    purpose is to leave the building - the point is not who fetches it.
    """
    error = require_self_or_hr(employee_id)
    if error:
        return error

    try:
        year, month = int(request.args['year']), int(request.args['month'])
    except (KeyError, TypeError, ValueError):
        return jsonify({'message': t(g.lang, 'year_month_required')}), 400

    schedule, rows = _export_rows(year, month, employee_id)
    if not schedule:
        return jsonify({'message': t(g.lang, 'no_schedule_generated_yet')}), 404
    if schedule['status'] != SCHEDULE_PUBLISHED:
        return jsonify({'message': t(g.lang, 'schedule_not_published_yet')}), 404

    text = schedule_to_ical(
        rows, t(g.lang, 'free_block_label'),
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))

    return Response(
        text, mimetype='text/calendar; charset=utf-8',
        headers={'Content-Disposition':
                 f'attachment; filename="schichtplan-{year}-{month:02d}.ics"'})


@app.route('/schedules/<int:year>/<int:month>/export.csv', methods=['GET'])
@hr_required
def export_schedule_csv(year, month):
    """The whole month as CSV, for payroll or a spreadsheet.

    Drafts are included here, unlike the iCal export, and the difference is the
    recipient: HR pulls this for itself, and exporting a draft to check it over
    is a sensible thing to do. The iCal file lands in someone's phone.
    """
    schedule, rows = _export_rows(year, month)
    if not schedule:
        return jsonify({'message': t(g.lang, 'no_schedule_generated_yet')}), 404

    text = schedule_to_csv(rows, WEEKDAYS[g.lang])

    return Response(
        text, mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition':
                 f'attachment; filename="schichtplan-{year}-{month:02d}.csv"'})


@app.route('/schedules/<int:year>/<int:month>', methods=['DELETE'])
@hr_required
def delete_schedule(year, month):
    connection = get_db()
    cursor = connection.cursor()
    cursor.execute('SELECT id FROM schedules WHERE year = ? AND month = ?', (year, month))
    row = cursor.fetchone()
    if not row:
        return jsonify({'message': t(g.lang, 'no_schedule_found')}), 404
    cursor.execute('DELETE FROM schedules WHERE id = ?', (row['id'],))
    connection.commit()
    return jsonify({'message': t(g.lang, 'schedule_deleted')}), 200


# ---------- day-level editing (times, extra places) ----------

def valid_time(value):
    if not isinstance(value, str) or len(value) != 5 or value[2] != ':':
        return False
    hours, _, minutes = value.partition(':')
    return (hours.isdigit() and minutes.isdigit()
            and 0 <= int(hours) <= 23 and 0 <= int(minutes) <= 59)


def find_schedule_id(cursor, year, month):
    cursor.execute('SELECT id FROM schedules WHERE year = ? AND month = ?', (year, month))
    row = cursor.fetchone()
    return row['id'] if row else None


@app.route('/schedules/<int:year>/<int:month>/shift-times', methods=['PUT'])
@hr_required
def set_shift_times(year, month):
    """Change the hours a shift runs on one date only.

    Sending null times clears the override, putting that date back on the shift
    type's usual hours.
    """
    data = request.get_json(silent=True) or {}
    iso_date = data.get('date')
    shift_type_id = data.get('shift_type_id')
    start_time = data.get('start_time')
    end_time = data.get('end_time')

    try:
        iso_date = parse_iso_date(iso_date)
    except ValueError:
        return jsonify({'message': t(g.lang, 'invalid_date')}), 400

    connection = get_db()
    cursor = connection.cursor()

    schedule_id = find_schedule_id(cursor, year, month)
    if not schedule_id:
        return jsonify({'message': t(g.lang, 'no_schedule_found')}), 404

    cursor.execute('SELECT id FROM shift_types WHERE id = ?', (shift_type_id,))
    if not cursor.fetchone():
        return jsonify({'message': t(g.lang, 'shift_type_not_found')}), 404

    if start_time is None and end_time is None:
        cursor.execute(
            'DELETE FROM shift_time_overrides WHERE schedule_id = ? AND date = ? AND shift_type_id = ?',
            (schedule_id, iso_date, shift_type_id),
        )
        connection.commit()
        return jsonify({'message': t(g.lang, 'times_reset_to_default')}), 200

    if not valid_time(start_time) or not valid_time(end_time):
        return jsonify({'message': t(g.lang, 'time_format_hint')}), 400

    cursor.execute('''
        INSERT INTO shift_time_overrides (schedule_id, date, shift_type_id, start_time, end_time)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(schedule_id, date, shift_type_id)
        DO UPDATE SET start_time = excluded.start_time, end_time = excluded.end_time
    ''', (schedule_id, iso_date, shift_type_id, start_time, end_time))

    connection.commit()
    return jsonify({'message': t(g.lang, 'times_changed')}), 200


@app.route('/schedules/<int:year>/<int:month>/slots', methods=['POST'])
@hr_required
def add_slot(year, month):
    """Add one more place to a shift on a single date, initially unassigned.

    The shift type's required headcount stays as it is - this is a one-off
    change to this date, not a change to what the shift normally needs.

    shift_type_id may be omitted/null for a block with no template of its own;
    start_time/end_time are then taken straight from the request body, subject
    to the same pair/format validation as update_assignment(), and a block
    without a shift type is rejected unless it brings its own times - it has
    no template to inherit them from.
    """
    data = request.get_json(silent=True) or {}
    iso_date = data.get('date')
    shift_type_id = data.get('shift_type_id')

    try:
        start_time, end_time = parse_assignment_times(data)
    except ValueError as err:
        return jsonify({'message': str(err)}), 400

    if shift_type_id is None and start_time is None:
        return jsonify({'message': t(g.lang, 'assignment_without_shift_type_needs_times')}), 400

    try:
        iso_date = parse_iso_date(iso_date)
    except ValueError:
        return jsonify({'message': t(g.lang, 'invalid_date')}), 400
    parsed = date.fromisoformat(iso_date)
    if (parsed.year, parsed.month) != (year, month):
        return jsonify({'message': t(g.lang, 'date_not_in_month')}), 400

    connection = get_db()
    cursor = connection.cursor()

    schedule_id = find_schedule_id(cursor, year, month)
    if not schedule_id:
        return jsonify({'message': t(g.lang, 'no_schedule_found')}), 404

    if shift_type_id is not None:
        cursor.execute('SELECT id FROM shift_types WHERE id = ?', (shift_type_id,))
        if not cursor.fetchone():
            return jsonify({'message': t(g.lang, 'shift_type_not_found')}), 404

    # "WHERE shift_type_id = NULL" matches nothing in SQL - not even the NULL
    # rows - so a block without a template would keep getting slot_index 0 and
    # collide with the unique index on its second insert.
    if shift_type_id is None:
        cursor.execute(
            'SELECT COALESCE(MAX(slot_index), -1) AS highest FROM shift_assignments '
            'WHERE schedule_id = ? AND date = ? AND shift_type_id IS NULL',
            (schedule_id, iso_date))
    else:
        cursor.execute(
            'SELECT COALESCE(MAX(slot_index), -1) AS highest FROM shift_assignments '
            'WHERE schedule_id = ? AND date = ? AND shift_type_id = ?',
            (schedule_id, iso_date, shift_type_id))
    next_index = cursor.fetchone()['highest'] + 1

    cursor.execute(
        'INSERT INTO shift_assignments (schedule_id, date, shift_type_id, slot_index, employee_id, manually_edited, start_time, end_time) '
        'VALUES (?, ?, ?, ?, NULL, 1, ?, ?)',
        (schedule_id, iso_date, shift_type_id, next_index, start_time, end_time),
    )
    assignment_id = cursor.lastrowid
    refresh_unfilled_count(cursor, schedule_id)

    connection.commit()
    return jsonify({'id': assignment_id, 'message': t(g.lang, 'slot_added')}), 201


@app.route('/assignments/<int:assignment_id>', methods=['DELETE'])
@hr_required
def delete_assignment(assignment_id):
    """Remove a place from a shift on one date."""
    connection = get_db()
    cursor = connection.cursor()
    cursor.execute('SELECT schedule_id FROM shift_assignments WHERE id = ?', (assignment_id,))
    assignment = cursor.fetchone()
    if not assignment:
        return jsonify({'message': t(g.lang, 'assignment_not_found')}), 404

    cursor.execute('DELETE FROM shift_assignments WHERE id = ?', (assignment_id,))
    refresh_unfilled_count(cursor, assignment['schedule_id'])

    connection.commit()
    return jsonify({'message': t(g.lang, 'slot_removed')}), 200


# ---------- manual editing (reassign / swap) ----------

def effective_shift_hours(cursor, schedule_id, iso_date, shift_type_id, default_start, default_end):
    """A shift type's actual hours on one date: a per-date override if one exists, else its usual hours.

    For an assignment, prefer assignment_hours() - it puts the assignment's own
    times in front of these two layers.
    """
    if shift_type_id is None:
        return default_start, default_end
    cursor.execute(
        'SELECT start_time, end_time FROM shift_time_overrides WHERE schedule_id = ? AND date = ? AND shift_type_id = ?',
        (schedule_id, iso_date, shift_type_id),
    )
    override = cursor.fetchone()
    if override:
        return override['start_time'], override['end_time']
    return default_start, default_end


def assignment_hours(cursor, row):
    """The hours one assignment actually runs, by precedence.

    1. the assignment's own start_time/end_time, when set - this person, this
       slot, these hours
    2. otherwise a per-date override for the shift type, which applies to
       everyone on that shift that day
    3. otherwise the shift type's usual hours

    Returns (None, None) for a block that has neither its own times nor a shift
    type to inherit from. The API rejects that combination (see the validation
    in update_assignment), but a caller reading old or hand-edited rows should
    get a value it can test rather than an exception.

    `row` needs the keys schedule_id, date, shift_type_id, start_time and
    end_time - a sqlite3.Row and a plain dict both work.
    """
    if row['start_time'] and row['end_time']:
        return row['start_time'], row['end_time']

    shift_type_id = row['shift_type_id']
    if shift_type_id is None:
        return None, None

    cursor.execute('SELECT start_time, end_time FROM shift_types WHERE id = ?', (shift_type_id,))
    shift_type = cursor.fetchone()
    if not shift_type:
        return None, None

    return effective_shift_hours(
        cursor, row['schedule_id'], row['date'], shift_type_id,
        shift_type['start_time'], shift_type['end_time'])


def week_bounds(iso_date):
    """The Monday-Sunday ISO week containing a date, as (start, end) ISO strings."""
    d = date.fromisoformat(iso_date)
    start = d - timedelta(days=d.weekday())
    return start.isoformat(), (start + timedelta(days=6)).isoformat()


def weekday_adverb(lang, weekday_index):
    """The weekday as it reads in "doesn't usually work {this}" - "mittwochs" /
    "Wednesdays". Both languages happen to form it the same way (weekday name
    + "s"), just differing in case, so one helper covers both.
    """
    name = WEEKDAYS[lang][weekday_index]
    return (name.lower() if lang == 'de' else name) + 's'


def constraint_warnings(cursor, employee_id, assignment_date, shift_type_id, schedule_id,
                        exclude_assignment_id=None, start_time=None, end_time=None,
                        break_minutes=None):
    """Non-blocking warnings for assigning `employee_id` to one shift.

    Unlike the scheduler's hard constraints (which only ever see one month at a
    time), this runs against already-saved data, so the weekly-hours and
    rest-period checks below deliberately query shift_assignments *without*
    scoping by schedule_id - the employee's neighbouring shift may belong to a
    different month's schedule row, and it should still be found.

    `start_time`/`end_time` are this assignment's own proposed hours, if any -
    passed straight through to assignment_hours() alongside shift_type_id.
    """
    if employee_id is None:
        return []
    warnings = []
    cursor.execute('SELECT * FROM employees WHERE id = ?', (employee_id,))
    employee = cursor.fetchone()
    if not employee:
        return [t(g.lang, 'employee_not_found')]

    weekday = date.fromisoformat(assignment_date).weekday()
    cursor.execute('SELECT 1 FROM employee_unavailable_weekdays WHERE employee_id = ? AND weekday = ?', (employee_id, weekday))
    if cursor.fetchone():
        warnings.append(t(g.lang, 'warn_not_usual_weekday', name=employee['name'], weekday=weekday_adverb(g.lang, weekday)))

    cursor.execute('SELECT 1 FROM employee_unavailable_dates WHERE employee_id = ? AND date = ?', (employee_id, assignment_date))
    if cursor.fetchone():
        warnings.append(t(g.lang, 'warn_marked_unavailable', name=employee['name'], date=assignment_date))

    # A block without a template isn't any shift type, so a restriction on
    # which types this person may work has nothing to say about it.
    if shift_type_id is not None:
        cursor.execute('SELECT 1 FROM employee_allowed_shift_types WHERE employee_id = ?', (employee_id,))
        if cursor.fetchone():
            cursor.execute('SELECT 1 FROM employee_allowed_shift_types WHERE employee_id = ? AND shift_type_id = ?',
                           (employee_id, shift_type_id))
            if not cursor.fetchone():
                warnings.append(t(g.lang, 'warn_restricted_shift_types', name=employee['name']))

    if employee['availability_mode'] == 'windows':
        # The actual hours this assignment runs, respecting the assignment's
        # own times and a per-date override - same source of truth the
        # rest-period check below uses, so a shortened shift is judged against
        # the times it now runs, not the shift type's nominal ones.
        start_time_effective, end_time_effective = assignment_hours(cursor, {
            'schedule_id': schedule_id, 'date': assignment_date, 'shift_type_id': shift_type_id,
            'start_time': start_time, 'end_time': end_time,
        })
        if start_time_effective and end_time_effective:
            cursor.execute(
                'SELECT weekday, start_time, end_time, valid_from, valid_until FROM employee_availability '
                'WHERE employee_id = ? AND weekday = ? ORDER BY start_time',
                (employee_id, weekday),
            )
            windows_today = [dict(row) for row in cursor.fetchall()]
            # An expired/not-yet-valid window is not an applicable one - same
            # rule the scheduler's structurally_eligible() enforces.
            applicable_windows = [w for w in windows_today if window_is_valid_on(w, assignment_date)]

            if not any(window_contains_shift(w, start_time_effective, end_time_effective) for w in applicable_windows):
                if applicable_windows:
                    windows_text = ', '.join(f"{w['start_time']}–{w['end_time']}" for w in applicable_windows)
                    warnings.append(t(g.lang, 'warn_outside_availability', name=employee['name'],
                                     weekday=weekday_adverb(g.lang, weekday), windows=windows_text))
                else:
                    warnings.append(t(g.lang, 'warn_outside_availability_no_window', name=employee['name'],
                                     weekday=weekday_adverb(g.lang, weekday)))

    # Everything else this person already holds that day. Until Etappe 4 the
    # mere existence of one was the warning ("already assigned that day"),
    # because nobody could work twice in a day. A split shift is now a normal
    # arrangement, so what remains worth warning about is an *overlap* - and,
    # separately, the daily working time the blocks add up to.
    query = ('SELECT id, schedule_id, date, shift_type_id, start_time, end_time, break_minutes '
             'FROM shift_assignments WHERE date = ? AND employee_id = ?')
    params = [assignment_date, employee_id]
    if exclude_assignment_id is not None:
        query += ' AND id != ?'
        params.append(exclude_assignment_id)
    cursor.execute(query, params)
    same_day = [dict(row) for row in cursor.fetchall()]

    proposed = {
        'schedule_id': schedule_id, 'date': assignment_date, 'shift_type_id': shift_type_id,
        'start_time': start_time, 'end_time': end_time,
    }
    proposed_start, proposed_end = assignment_hours(cursor, proposed)

    # (start, end, break) per block already held that day. The break rides
    # along because § 2 Abs. 1 ArbZG counts working time without it, so the
    # daily total below cannot be summed from the hours alone.
    same_day_blocks = []
    unknown_hours = False
    for row in same_day:
        row_start, row_end = assignment_hours(cursor, row)
        if row_start and row_end:
            same_day_blocks.append((row_start, row_end, row['break_minutes']))
        else:
            unknown_hours = True
    same_day_hours = [(start, end) for start, end, _ in same_day_blocks]

    if same_day and (unknown_hours or not (proposed_start and proposed_end)):
        # No minute axis on at least one side - overlap cannot be decided, so
        # fall back to the pre-Etappe-4 wording rather than stay silent.
        warnings.append(t(g.lang, 'warn_already_assigned_that_day', name=employee['name']))
    elif proposed_start and proposed_end:
        proposed_range = _time_range_minutes(proposed_start, proposed_end)
        for row_start, row_end in same_day_hours:
            if _ranges_overlap(proposed_range, _time_range_minutes(row_start, row_end)):
                warnings.append(t(g.lang, 'warn_overlapping_blocks', name=employee['name'],
                                  date=assignment_date, start=row_start, end=row_end))
                break

    # § 3 ArbZG caps the working time of one day, and § 2 Abs. 1 defines that
    # as the sum of the blocks *without their breaks*, rather than the span
    # from the first start to the last end - neither the interruption of a
    # split shift nor a rest period inside a block is working time.
    proposed_span = (shift_duration_minutes(proposed_start, proposed_end)
                     if proposed_start and proposed_end else None)
    if employee['max_daily_hours'] is not None and proposed_span is not None:
        total_minutes = net_working_minutes(proposed_span, break_minutes)
        for row_start, row_end, row_break in same_day_blocks:
            total_minutes += net_working_minutes(
                shift_duration_minutes(row_start, row_end), row_break)
        if total_minutes > employee['max_daily_hours'] * 60:
            warnings.append(t(g.lang, 'warn_daily_hours_exceeded', name=employee['name'],
                              date=assignment_date, hours=total_minutes / 60,
                              cap=employee['max_daily_hours']))

    # § 11 Abs. 3 ArbZG via the six-day rule (see MAX_CONSECUTIVE_DAYS in
    # scheduler.py). Unlike the generator, this path reads saved data and
    # therefore also sees *forward* across the month boundary: the run is
    # counted in both directions over whatever is stored. Stricter than the
    # generator, not laxer.
    run = consecutive_days_around(cursor, employee_id, assignment_date, exclude_assignment_id)
    if run > MAX_CONSECUTIVE_DAYS:
        warnings.append(t(g.lang, 'warn_seventh_consecutive_day',
                          name=employee['name'], days=run))

    # § 9 ArbZG forbids work on public holidays, and § 10 exempts whole
    # industries. Which side this business is on is a fact about the business,
    # not something the tool can derive - so this states the situation and
    # leaves the judgement where it belongs. Silent while no federal state has
    # been picked, because then no date is known to be a holiday.
    feiertag = holidays_in_range(
        date.fromisoformat(assignment_date), date.fromisoformat(assignment_date),
        holiday_region(cursor),
    )
    if feiertag:
        warnings.append(t(g.lang, 'warn_public_holiday', date=assignment_date,
                          name=next(iter(feiertag.values()))))

    # § 11 Abs. 1 ArbZG: at least 15 Sundays a year stay free of work.
    if date.fromisoformat(assignment_date).weekday() == 6:
        year = date.fromisoformat(assignment_date).year
        worked = sundays_worked_in_year(cursor, employee_id, year, assignment_date,
                                        exclude_assignment_id) + 1
        free = sundays_in_year(year) - worked
        if free < MIN_FREE_SUNDAYS_PER_YEAR:
            warnings.append(t(g.lang, 'warn_sunday_budget_exhausted',
                              name=employee['name'], free=max(0, free), year=year))

    # § 4 ArbZG. This is the only place the rule can be broken at all: left
    # alone, break_minutes is NULL and reads as the legal minimum, so every
    # plan is compliant by construction. Only someone entering a shorter break
    # by hand gets here - and it stays a warning, as everywhere else.
    if proposed_span is not None and break_minutes is not None:
        required = legal_break_minutes(proposed_span)
        if break_minutes < required:
            warnings.append(t(g.lang, 'warn_break_below_minimum', name=employee['name'],
                              hours=proposed_span / 60, minutes=break_minutes,
                              required=required))

    if employee['max_shifts_per_month'] is not None:
        cursor.execute(
            'SELECT COUNT(*) AS n FROM shift_assignments WHERE employee_id = ? AND schedule_id = ? AND id != ?',
            (employee_id, schedule_id, exclude_assignment_id or -1),
        )
        if cursor.fetchone()['n'] >= employee['max_shifts_per_month']:
            warnings.append(t(g.lang, 'warn_monthly_cap_reached', name=employee['name'], limit=employee['max_shifts_per_month']))

    if employee['weekly_hours'] is not None:
        week_start, week_end = week_bounds(assignment_date)
        cursor.execute('''
            SELECT sa.id, sa.date, sa.schedule_id, sa.shift_type_id, sa.start_time,
                   sa.end_time, sa.break_minutes
            FROM shift_assignments sa
            WHERE sa.employee_id = ? AND sa.date BETWEEN ? AND ?
        ''', (employee_id, week_start, week_end))
        total_minutes = 0
        for row in cursor.fetchall():
            if exclude_assignment_id is not None and row['id'] == exclude_assignment_id:
                continue
            start, end = assignment_hours(cursor, row)
            if start and end:
                total_minutes += net_working_minutes(
                    shift_duration_minutes(start, end), row['break_minutes'])

        new_start, new_end = assignment_hours(cursor, {
            'schedule_id': schedule_id, 'date': assignment_date, 'shift_type_id': shift_type_id,
            'start_time': start_time, 'end_time': end_time,
        })
        if new_start and new_end:
            total_minutes += net_working_minutes(
                shift_duration_minutes(new_start, new_end), break_minutes)

        if total_minutes > employee['weekly_hours'] * 60:
            warnings.append(t(g.lang, 'warn_weekly_hours_exceeded', name=employee['name'],
                             hours=total_minutes / 60, target=employee['weekly_hours']))

    if proposed_start and proposed_end:
        # § 5 Abs. 1 ArbZG measures the rest period from the end of the *daily
        # working time*, so both sides of the comparison are whole days, not
        # single blocks: this date's envelope already includes whatever else
        # the person holds that day, and the neighbouring date contributes its
        # own envelope rather than one arbitrarily picked row. Before Etappe 4
        # a fetchone() was enough, because a day never held more than one.
        this_day = day_envelope_from_hours(
            assignment_date, same_day_hours + [(proposed_start, proposed_end)])
        min_rest = employee['min_rest_hours']
        d = date.fromisoformat(assignment_date)

        # (neighbouring date, is that neighbour the earlier of the two days?)
        neighbors = [((d - timedelta(days=1)).isoformat(), True), ((d + timedelta(days=1)).isoformat(), False)]
        for neighbor_date, neighbor_is_earlier in neighbors:
            query = ('SELECT id, schedule_id, date, shift_type_id, start_time, end_time '
                     'FROM shift_assignments WHERE employee_id = ? AND date = ?')
            params = [employee_id, neighbor_date]
            if exclude_assignment_id is not None:
                query += ' AND id != ?'
                params.append(exclude_assignment_id)
            cursor.execute(query, params)
            neighbor_hours = []
            for neighbor in cursor.fetchall():
                n_start, n_end = assignment_hours(cursor, neighbor)
                if n_start and n_end:
                    neighbor_hours.append((n_start, n_end))
            if not neighbor_hours:
                continue
            neighbor_day = day_envelope_from_hours(neighbor_date, neighbor_hours)

            gap = (rest_gap_hours(neighbor_day, this_day) if neighbor_is_earlier
                   else rest_gap_hours(this_day, neighbor_day))
            if gap < min_rest:
                warnings.append(t(g.lang, 'warn_rest_period_too_short', name=employee['name'],
                                 gap=gap, required=min_rest))

    return warnings


def day_envelope_from_hours(iso_date, hours):
    """The working-time envelope of one day: (earliest start, latest end).

    The counterpart of day_envelope() inside scheduler._search(), for the
    manual-correction path, which reads saved rows instead of a search state.
    Two implementations of the same idea is one more than the project likes,
    but the scheduler's closes over its own search state and this one takes a
    list - the shared part is shift_datetimes(), and that is imported, not
    copied.
    """
    pairs = [shift_datetimes(iso_date, start, end) for start, end in hours]
    return min(start for start, _ in pairs), max(end for _, end in pairs)


def refresh_unfilled_count(cursor, schedule_id):
    cursor.execute('SELECT COUNT(*) AS n FROM shift_assignments WHERE schedule_id = ? AND employee_id IS NULL', (schedule_id,))
    unfilled_count = cursor.fetchone()['n']
    cursor.execute('UPDATE schedules SET unfilled_count = ? WHERE id = ?', (unfilled_count, schedule_id))


@app.route('/assignments/<int:assignment_id>', methods=['PUT'])
@hr_required
def update_assignment(assignment_id):
    data = request.get_json(silent=True) or {}
    # Required rather than defaulted: data.get() can't tell "employee_id omitted"
    # from "employee_id explicitly null", and the latter means "unassign this
    # slot" - silently unassigning on a malformed request that simply forgot the
    # field would be the wrong failure mode.
    if 'employee_id' not in data:
        return jsonify({'message': t(g.lang, 'employee_id_required')}), 400
    employee_id = data['employee_id']

    connection = get_db()
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM shift_assignments WHERE id = ?', (assignment_id,))
    assignment = cursor.fetchone()
    if not assignment:
        return jsonify({'message': t(g.lang, 'assignment_not_found')}), 404

    if employee_id is not None:
        cursor.execute('SELECT id FROM employees WHERE id = ?', (employee_id,))
        if not cursor.fetchone():
            return jsonify({'message': t(g.lang, 'employee_not_found')}), 404

    try:
        start_time, end_time = parse_assignment_times(data)
    except ValueError as err:
        return jsonify({'message': str(err)}), 400

    if assignment['shift_type_id'] is None and start_time is None:
        return jsonify({'message': t(g.lang, 'assignment_without_shift_type_needs_times')}), 400

    try:
        break_minutes = parse_break_minutes(data.get('break_minutes'))
    except ValueError as err:
        return jsonify({'message': str(err)}), 400

    warnings = constraint_warnings(
        cursor, employee_id, assignment['date'], assignment['shift_type_id'], assignment['schedule_id'],
        exclude_assignment_id=assignment_id, start_time=start_time, end_time=end_time,
        break_minutes=break_minutes,
    )

    # start_time/end_time and break_minutes are written on every PUT, same
    # "absent means empty" semantics as employee_id above: leaving them out of
    # the body clears them to NULL rather than keeping whatever was there
    # before. Consequence: a caller that only wants to swap the employee must
    # resend the current times and break, or they get wiped. The frontend does
    # this. For the break, NULL is not a loss of information the way it is for
    # the times - it simply means "the legal minimum again" - but it is still a
    # silent change to what was stored, so the same rule applies.
    cursor.execute(
        'UPDATE shift_assignments SET employee_id = ?, start_time = ?, end_time = ?, '
        'break_minutes = ?, manually_edited = 1 WHERE id = ?',
        (employee_id, start_time, end_time, break_minutes, assignment_id))
    refresh_unfilled_count(cursor, assignment['schedule_id'])

    connection.commit()
    return jsonify({'message': t(g.lang, 'assignment_updated'), 'warnings': warnings})


@app.route('/assignments/swap', methods=['POST'])
@hr_required
def swap_assignments():
    data = request.get_json(silent=True) or {}
    id_a = data.get('assignment_id_a')
    id_b = data.get('assignment_id_b')
    if not id_a or not id_b or id_a == id_b:
        return jsonify({'message': t(g.lang, 'two_assignment_ids_required')}), 400

    connection = get_db()
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM shift_assignments WHERE id IN (?, ?)', (id_a, id_b))
    rows = {row['id']: row for row in cursor.fetchall()}
    if id_a not in rows or id_b not in rows:
        return jsonify({'message': t(g.lang, 'assignment_not_found')}), 404

    a, b = rows[id_a], rows[id_b]
    if a['schedule_id'] != b['schedule_id']:
        return jsonify({'message': t(g.lang, 'swap_same_schedule_only')}), 400

    cursor.execute('UPDATE shift_assignments SET employee_id = ?, manually_edited = 1 WHERE id = ?', (b['employee_id'], a['id']))
    cursor.execute('UPDATE shift_assignments SET employee_id = ?, manually_edited = 1 WHERE id = ?', (a['employee_id'], b['id']))

    # The times stay with the slot, not the person - a and b still hold the
    # rows as fetched before the swap above, so a['start_time']/a['end_time']
    # are the place's own times, unaffected by which employee now sits there.
    warnings = []
    warnings += constraint_warnings(cursor, b['employee_id'], a['date'], a['shift_type_id'], a['schedule_id'],
                                    exclude_assignment_id=a['id'],
                                    start_time=a['start_time'], end_time=a['end_time'])
    warnings += constraint_warnings(cursor, a['employee_id'], b['date'], b['shift_type_id'], b['schedule_id'],
                                    exclude_assignment_id=b['id'],
                                    start_time=b['start_time'], end_time=b['end_time'])

    refresh_unfilled_count(cursor, a['schedule_id'])

    connection.commit()
    return jsonify({'message': t(g.lang, 'shifts_swapped'), 'warnings': warnings})


@app.route('/assignments/<int:assignment_id>/replacement-suggestions', methods=['GET'])
@hr_required
def replacement_suggestions(assignment_id):
    """Who could reasonably cover this slot - built for a shift an absence just
    freed, but works for any slot, e.g. one added via add_slot.

    Reuses constraint_warnings() rather than a second, parallel eligibility
    check: a candidate with zero warnings is exactly "eligible under every
    constraint that also governs manual reassignment", and it stays correct
    automatically as those constraints evolve.
    """
    connection = get_db()
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM shift_assignments WHERE id = ?', (assignment_id,))
    assignment = cursor.fetchone()
    if not assignment:
        return jsonify({'message': t(g.lang, 'assignment_not_found')}), 404

    cursor.execute('SELECT id, name FROM employees WHERE active = 1 ORDER BY name')
    candidates = []
    # employee_id is NULL on a freed slot, so the absent person is only
    # identifiable via absent_employee_id - excluding just employee_id would
    # (wrongly) suggest them as their own replacement.
    excluded = {assignment['employee_id'], assignment['absent_employee_id']}
    for row in cursor.fetchall():
        if row['id'] in excluded:
            continue
        warnings = constraint_warnings(
            cursor, row['id'], assignment['date'], assignment['shift_type_id'], assignment['schedule_id'],
            exclude_assignment_id=assignment_id,
            start_time=assignment['start_time'], end_time=assignment['end_time'],
        )
        if warnings:
            continue
        cursor.execute(
            'SELECT COUNT(*) AS n FROM shift_assignments WHERE schedule_id = ? AND employee_id = ?',
            (assignment['schedule_id'], row['id']),
        )
        candidates.append({'employee_id': row['id'], 'name': row['name'], 'current_load': cursor.fetchone()['n']})

    candidates.sort(key=lambda c: (c['current_load'], c['name']))
    return jsonify(candidates)


# ---------- opening hours (business hours) and exceptions ----------
#
# business_hours always has exactly seven rows (one per weekday, see
# 0006_coverage.py) - PUT below only ever overwrites those seven, it never
# deletes or inserts, so that invariant can't be broken from here.
# business_hours_exceptions holds one-off overrides for a single date (a
# holiday, a special opening) and is otherwise empty; UNIQUE(date) is
# enforced explicitly below with a 400 rather than silently upserting,
# unlike employee_absences' ON CONFLICT DO UPDATE - a second exception for
# the same date is a mistake to flag, not a correction to accept quietly.
#
# business_hours_for() below owns the precedence rule (an exception fully
# overrides the weekday) and is the only place that decides it. It takes the
# two dicts a caller has already loaded rather than a cursor, so that the one
# caller which needs it per date - the month loop in coverage_gaps_for_month(),
# through _closed_on() and for the trimming window - can use it without turning
# into the per-date query the Task 4 and Task 5 reviews rejected. Earlier
# versions of this comment claimed the helper was already the shared read path
# while nothing outside the tests actually called it; that is what this shape
# fixes.
#
# The two write paths cross-validate each other: /coverage-requirements refuses
# a band outside its weekday's opening hours, and /business-hours refuses hours
# that would invalidate a band already saved (see
# reject_hours_conflicting_with_bands() below). Without the second direction,
# narrowing a weekday's hours left behind bands that GET handed out and PUT
# refused to take back, which locked the coverage editor for every weekday at
# once, because that route validates the whole list in one pass.

def serialize_business_hours(row):
    return {
        'weekday': row['weekday'],
        'open_time': row['open_time'],
        'close_time': row['close_time'],
        'closed': bool(row['closed']),
    }


def reject_hours_conflicting_with_bands(cursor, by_weekday):
    """Refuses opening hours that would invalidate a coverage band already saved.

    The mirror image of the check replace_coverage_requirements() runs against
    the stored opening hours, and deliberately through the same two rules in
    the same order: the closed flag first, then band_within(). Re-deciding
    containment here with a second, similar comparison is exactly what this
    project avoids elsewhere, so there is none.

    The message names the weekday and the concrete band. Without both, HR reads
    "these hours don't work" and goes looking in the opening-hours editor, while
    the row that actually blocks the save sits in the coverage editor under some
    other weekday.

    One query for every weekday's bands, not one per weekday -
    coverage_requirements_by_weekday() is the same loader the gap calculation
    uses.
    """
    bands_by_weekday = coverage_requirements_by_weekday(cursor)
    if not bands_by_weekday:
        return

    # Sorted by weekday so that a request touching several conflicting days
    # always reports the earliest one, rather than whichever order the caller
    # happened to send its seven entries in.
    for weekday, (open_time, close_time, closed) in sorted(by_weekday.items()):
        for band in bands_by_weekday.get(weekday, []):
            if closed:
                raise ValueError(t(
                    g.lang, 'business_hours_closed_with_band',
                    weekday=WEEKDAYS[g.lang][weekday],
                    start=band['start_time'], end=band['end_time'],
                ))
            if not band_within(band, open_time, close_time):
                raise ValueError(t(
                    g.lang, 'business_hours_conflicts_band',
                    weekday=WEEKDAYS[g.lang][weekday],
                    start=band['start_time'], end=band['end_time'],
                    open=open_time, close=close_time,
                ))


def replace_business_hours(connection, entries):
    """Overwrites all seven weekday rows from a list of exactly seven entries.

    Validates the whole list first and only writes once every entry has
    passed - a bad entry must not overwrite some of the seven rows and leave
    the rest as they were. Requiring exactly seven entries, each with a
    distinct weekday in 0..6, is what guarantees every weekday gets updated
    and none twice: seven distinct values in that range can only be
    {0, 1, ..., 6}.

    The last validation step is the cross-check against already saved coverage
    bands (see reject_hours_conflicting_with_bands()), and it runs before the
    first UPDATE for the same reason as everything above it: a rejected save
    must leave all seven rows exactly as they were.
    """
    if not isinstance(entries, list) or len(entries) != 7:
        raise ValueError(t(g.lang, 'business_hours_length'))

    by_weekday = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(t(g.lang, 'business_hours_entry_invalid'))
        weekday = parse_weekday(entry.get('weekday'))
        if weekday in by_weekday:
            raise ValueError(t(g.lang, 'business_hours_weekday_duplicate'))

        open_time = entry.get('open_time')
        close_time = entry.get('close_time')
        if not valid_time(open_time):
            raise ValueError(t(g.lang, 'availability_time_invalid', value=open_time))
        if not valid_time(close_time):
            raise ValueError(t(g.lang, 'availability_time_invalid', value=close_time))

        by_weekday[weekday] = (open_time, close_time, 1 if entry.get('closed') else 0)

    cursor = connection.cursor()
    reject_hours_conflicting_with_bands(cursor, by_weekday)

    for weekday, (open_time, close_time, closed) in by_weekday.items():
        cursor.execute(
            'UPDATE business_hours SET open_time = ?, close_time = ?, closed = ? WHERE weekday = ?',
            (open_time, close_time, closed, weekday),
        )


@app.route('/business-hours', methods=['GET'])
@hr_required
def list_business_hours():
    connection = get_db()
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM business_hours ORDER BY weekday')
    return jsonify([serialize_business_hours(row) for row in cursor.fetchall()])


@app.route('/business-hours', methods=['PUT'])
@hr_required
def update_business_hours():
    entries = request.get_json(silent=True)
    connection = get_db()
    try:
        replace_business_hours(connection, entries)
    except ValueError as e:
        return jsonify({'message': str(e)}), 400
    connection.commit()

    cursor = connection.cursor()
    cursor.execute('SELECT * FROM business_hours ORDER BY weekday')
    return jsonify([serialize_business_hours(row) for row in cursor.fetchall()])


def serialize_business_hours_exception(row):
    return {
        'date': row['date'],
        'open_time': row['open_time'],
        'close_time': row['close_time'],
        'closed': bool(row['closed']),
        'label': row['label'],
    }


def parse_business_hours_exception(data):
    """Validates one exception's fields, returning (date, open_time, close_time, closed, label).

    open_time/close_time are nullable in the schema - a closed exception
    (a holiday) needs no times. Only when the exception is NOT closed are
    both required, since an open exception with unknown hours would leave
    business_hours_for() with nothing usable to hand back to its callers -
    and those hours are what coverage_gaps_for_month() trims that date's
    coverage bands to, so a special opening really does change the demand
    reported for its date rather than only its open/closed state.
    """
    iso_date = parse_iso_date(data.get('date'))

    closed = 1 if data.get('closed') else 0
    open_time = data.get('open_time')
    close_time = data.get('close_time')

    if closed:
        for value in (open_time, close_time):
            if value is not None and not valid_time(value):
                raise ValueError(t(g.lang, 'availability_time_invalid', value=value))
    else:
        if not valid_time(open_time):
            raise ValueError(t(g.lang, 'availability_time_invalid', value=open_time))
        if not valid_time(close_time):
            raise ValueError(t(g.lang, 'availability_time_invalid', value=close_time))

    return iso_date, open_time, close_time, closed, data.get('label')


@app.route('/business-hours/exceptions', methods=['GET'])
@hr_required
def list_business_hours_exceptions():
    connection = get_db()
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM business_hours_exceptions ORDER BY date')
    return jsonify([serialize_business_hours_exception(row) for row in cursor.fetchall()])


@app.route('/business-hours/exceptions', methods=['POST'])
@hr_required
def create_business_hours_exception():
    data = request.get_json(silent=True) or {}
    connection = get_db()
    cursor = connection.cursor()

    try:
        iso_date, open_time, close_time, closed, label = parse_business_hours_exception(data)
    except ValueError as e:
        return jsonify({'message': str(e)}), 400

    cursor.execute('SELECT id FROM business_hours_exceptions WHERE date = ?', (iso_date,))
    if cursor.fetchone():
        return jsonify({'message': t(g.lang, 'business_hours_exception_date_taken')}), 400

    cursor.execute(
        'INSERT INTO business_hours_exceptions (date, open_time, close_time, closed, label) '
        'VALUES (?, ?, ?, ?, ?)',
        (iso_date, open_time, close_time, closed, label),
    )
    connection.commit()

    cursor.execute('SELECT * FROM business_hours_exceptions WHERE date = ?', (iso_date,))
    return jsonify(serialize_business_hours_exception(cursor.fetchone())), 201


@app.route('/business-hours/exceptions/<iso_date>', methods=['DELETE'])
@hr_required
def delete_business_hours_exception(iso_date):
    connection = get_db()
    cursor = connection.cursor()
    cursor.execute('SELECT id FROM business_hours_exceptions WHERE date = ?', (iso_date,))
    if not cursor.fetchone():
        return jsonify({'message': t(g.lang, 'business_hours_exception_not_found')}), 404

    cursor.execute('DELETE FROM business_hours_exceptions WHERE date = ?', (iso_date,))
    connection.commit()
    return jsonify({'message': t(g.lang, 'business_hours_exception_deleted')}), 200


def business_hours_for(iso_date, weekday, hours_by_weekday, exceptions_by_date):
    """(open_time, close_time, closed) for one date - an exception fully overrides the weekday rule.

    A pure helper over data the caller has already loaded:
    `hours_by_weekday` from load_business_hours_by_weekday(),
    `exceptions_by_date` from business_hours_exceptions_by_date(). It runs no
    query of its own, which is what lets coverage_gaps_for_month() call it once
    per date of the month without adding a single query - the N+1 constraint
    from the Task 4 and Task 5 reviews is met by where the data is loaded, not
    by avoiding this function.

    `weekday` is passed in rather than derived from `iso_date` because every
    caller is already looping over dates it built from a calendar and knows the
    weekday; re-parsing the string here would be work done twice.

    An exception that is open but carries no times of its own describes no
    usable window. The API refuses to store one (see
    parse_business_hours_exception()), but a row written past the API - by a
    migration or by hand - must not make the month loop fall over, so the
    weekday rule stands in for it. A closed exception needs no times and keeps
    its precedence either way.
    """
    exception = exceptions_by_date.get(iso_date)
    if exception is not None:
        closed = bool(exception['closed'])
        if closed or (exception['open_time'] and exception['close_time']):
            return exception['open_time'], exception['close_time'], closed

    hours = hours_by_weekday.get(weekday)
    if hours is None:
        return None, None, False
    return hours[0], hours[1], bool(hours[2])


# ---------- coverage requirement bands ----------
#
# coverage_requirements holds bands of required headcount across a weekday's
# opening hours ("Monday 08:00-12:00 needs 3 people"). PUT replaces the whole
# list across all seven weekdays at once - same full-replace semantics as
# /business-hours and the employee constraint lists above - so the overlap
# check below validates the *final* state in one pass instead of reasoning
# about a sequence of incremental edits.
#
# Two things this validation deliberately does NOT do:
#
# - It never consults business_hours_for(). That helper answers "which window
#   applies on this DATE", and a date is precisely what a band does not have:
#   bands hang off the weekday, so exceptions (business_hours_exceptions) play
#   no role here at all. load_business_hours_by_weekday() below reads all seven
#   weekdays in a single query and the loop below matches against that dict.
# - It never checks overlap across a weekday boundary. A Monday 22:00-06:00
#   band and a Tuesday 00:00-08:00 band describe different points in the week
#   under the start-anchored reading this project uses everywhere else (see
#   coverage_model._band_range): the night shift ends early the next day, the
#   Tuesday band sits on Tuesday morning. A real conflict would only appear
#   once the week is treated as a 10080-minute ring across its own weekly
#   repetition - documented known limitation, not built here.

def serialize_coverage_requirement(row):
    return {
        'weekday': row['weekday'],
        'start_time': row['start_time'],
        'end_time': row['end_time'],
        'required_count': row['required_count'],
    }


def parse_coverage_requirements(entries):
    """Validates every band's shape, weekday range, time format and count.

    Overlap and opening-hours checks are not done here - they need the whole
    list grouped by weekday, which replace_coverage_requirements() does after
    this parse pass succeeds.
    """
    if not isinstance(entries, list):
        raise ValueError(t(g.lang, 'coverage_requirement_entry_invalid'))

    parsed = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(t(g.lang, 'coverage_requirement_entry_invalid'))

        weekday = parse_weekday(entry.get('weekday'))

        start_time = entry.get('start_time')
        end_time = entry.get('end_time')
        if not valid_time(start_time):
            raise ValueError(t(g.lang, 'availability_time_invalid', value=start_time))
        if not valid_time(end_time):
            raise ValueError(t(g.lang, 'availability_time_invalid', value=end_time))

        try:
            required_count = int(entry.get('required_count'))
        except (TypeError, ValueError):
            raise ValueError(t(g.lang, 'field_must_be_number', field=t(g.lang, 'required_count_label')))
        if required_count < 0:
            raise ValueError(t(g.lang, 'field_must_not_be_negative', field=t(g.lang, 'required_count_label')))

        parsed.append({
            'weekday': weekday, 'start_time': start_time, 'end_time': end_time,
            'required_count': required_count,
        })

    return parsed


def load_business_hours_by_weekday(cursor):
    """All seven business_hours rows as {weekday: (open_time, close_time, closed)}.

    One query for all seven weekdays, not business_hours_for() called per
    band - see the comment above this section for why.
    """
    cursor.execute('SELECT weekday, open_time, close_time, closed FROM business_hours')
    return {
        row['weekday']: (row['open_time'], row['close_time'], bool(row['closed']))
        for row in cursor.fetchall()
    }


def replace_coverage_requirements(connection, entries):
    """Validates and fully replaces all coverage_requirements rows.

    Same "validate everything, write once" shape as replace_business_hours():
    a bad band anywhere in the list must not partially overwrite the table.
    The overlap check is grouped by weekday - bands_overlap()/
    first_overlapping_pair() only ever see one weekday's bands at a time, so a
    Monday band can never collide with a Tuesday band here (see the section
    comment on the known cross-weekday limitation).
    """
    parsed = parse_coverage_requirements(entries)

    cursor = connection.cursor()
    hours_by_weekday = load_business_hours_by_weekday(cursor)

    by_weekday = {}
    for band in parsed:
        by_weekday.setdefault(band['weekday'], []).append(band)

    for weekday, bands in by_weekday.items():
        pair = first_overlapping_pair(bands)
        if pair is not None:
            first, second = pair
            raise ValueError(t(
                g.lang, 'coverage_requirement_overlap',
                weekday=WEEKDAYS[g.lang][weekday],
                start1=first['start_time'], end1=first['end_time'],
                start2=second['start_time'], end2=second['end_time'],
            ))

        open_time, close_time, closed = hours_by_weekday[weekday]
        for band in bands:
            if closed:
                raise ValueError(t(
                    g.lang, 'coverage_requirement_closed_day',
                    weekday=WEEKDAYS[g.lang][weekday],
                    start=band['start_time'], end=band['end_time'],
                ))
            if not band_within(band, open_time, close_time):
                raise ValueError(t(
                    g.lang, 'coverage_requirement_outside_hours',
                    weekday=WEEKDAYS[g.lang][weekday],
                    start=band['start_time'], end=band['end_time'],
                    open=open_time, close=close_time,
                ))

    cursor.execute('DELETE FROM coverage_requirements')
    for band in parsed:
        cursor.execute(
            'INSERT INTO coverage_requirements (weekday, start_time, end_time, required_count) '
            'VALUES (?, ?, ?, ?)',
            (band['weekday'], band['start_time'], band['end_time'], band['required_count']),
        )


@app.route('/coverage-requirements', methods=['GET'])
@hr_required
def list_coverage_requirements():
    connection = get_db()
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM coverage_requirements ORDER BY weekday, start_time')
    return jsonify([serialize_coverage_requirement(row) for row in cursor.fetchall()])


@app.route('/coverage-requirements', methods=['PUT'])
@hr_required
def update_coverage_requirements():
    entries = request.get_json(silent=True)
    connection = get_db()
    try:
        replace_coverage_requirements(connection, entries)
    except ValueError as e:
        return jsonify({'message': str(e)}), 400
    connection.commit()

    cursor = connection.cursor()
    cursor.execute('SELECT * FROM coverage_requirements ORDER BY weekday, start_time')
    return jsonify([serialize_coverage_requirement(row) for row in cursor.fetchall()])


# ---------- coverage gaps ----------
#
# GET /schedules/<year>/<month> reports where a month's actual staffing falls
# short of what /coverage-requirements demands. fetch_schedule() runs over
# every day of the month, so reading coverage_requirements, business_hours or
# business_hours_exceptions per date would be exactly the N+1 the Task 4 and
# Task 5 reviews flagged. The three loader functions below each run exactly
# once per call to fetch_schedule(), regardless of how many days the month
# has; the precedence rule (exception beats weekday) is then replayed against
# their results in memory by business_hours_for(), which is a pure function
# over those dicts and issues no query at all.
#
# The actual gap arithmetic lives in coverage_model.coverage_gaps() - a pure
# function, no database - and runs once per date, fed the bands and covered
# intervals assembled here.

def coverage_requirements_by_weekday(cursor):
    """All coverage_requirements rows as {weekday: [bands...]}, one query for the whole month."""
    cursor.execute(
        'SELECT weekday, start_time, end_time, required_count FROM coverage_requirements '
        'ORDER BY weekday, start_time'
    )
    by_weekday = {}
    for row in cursor.fetchall():
        by_weekday.setdefault(row['weekday'], []).append({
            'start_time': row['start_time'], 'end_time': row['end_time'],
            'required_count': row['required_count'],
        })
    return by_weekday


def business_hours_exceptions_by_date(cursor, start_date, end_date):
    """All business_hours_exceptions rows in [start_date, end_date] as {date: row}, one query."""
    cursor.execute(
        'SELECT date, open_time, close_time, closed FROM business_hours_exceptions '
        'WHERE date BETWEEN ? AND ?',
        (start_date, end_date),
    )
    return {row['date']: row for row in cursor.fetchall()}


def _closed_on(iso_date, weekday, hours_by_weekday, exceptions_by_date):
    """Is the business shut on this date? Nothing but the closed flag of business_hours_for().

    The precedence rule is not repeated here - this is a name for the question
    the month loop asks, answered by the one function that owns the rule.

    Both sources of a closed day still matter, and neither can be inferred from
    the other. An exception closes a single date while its weekday stays open.
    A weekday marked closed in business_hours, on the other hand, can still
    carry bands: /business-hours now rejects closing a weekday that has any
    (reject_hours_conflicting_with_bands()), but a database written before that
    check existed, or by migration 0007 straight past the API, can hold exactly
    that combination - so the flag is read, never assumed False just because
    bands are there.
    """
    return business_hours_for(iso_date, weekday, hours_by_weekday, exceptions_by_date)[2]


def coverage_gaps_for_month(cursor, year, month, assignments):
    """Coverage gaps for every date of the month, from data loaded once - not per day.

    `assignments` is fetch_schedule()'s own list: its start_time/end_time are
    already resolved to the actual hours (own time > date override > shift
    type default - see the loop that builds it), so no second call to
    assignment_hours() is needed here. An assignment covers nothing unless it
    is held by someone: employee_id IS NULL both for a still-unfilled slot and
    for one an absence just freed, and both must contribute no coverage.

    Every band is trimmed to the effective opening window of its date before it
    is counted - effective meaning the one business_hours_for() resolves, so a
    special opening on a single date narrows or widens that date's demand and
    not just its open/closed state. Trimming is what keeps a band that predates
    the current opening hours from demanding staff for a closed business: bands
    derived by migration 0007 never passed the API's validation at all, and any
    database edited before /business-hours started cross-checking can hold the
    same thing. A band that is trimmed away entirely produces no gap.
    """
    bands_by_date = effective_bands_by_date(cursor, year, month)
    if not bands_by_date:
        return []

    days_in_month = calendar.monthrange(year, month)[1]

    intervals_by_date = {}
    for a in assignments:
        if a['employee_id'] is None or not a['start_time'] or not a['end_time']:
            continue
        intervals_by_date.setdefault(a['date'], []).append(
            {'start_time': a['start_time'], 'end_time': a['end_time']}
        )

    gaps = []
    for day in range(1, days_in_month + 1):
        iso_date = date(year, month, day).isoformat()
        bands = bands_by_date.get(iso_date)
        if not bands:
            continue

        for gap in coverage_gaps(bands, intervals_by_date.get(iso_date, [])):
            gaps.append({'date': iso_date, **gap})

    return gaps


# The only setting so far. Kept as an explicit allow-list rather than "store
# whatever arrives": a typo in a key would otherwise land in the table and
# quietly never be read again.
# The two states a schedule can be in. A draft is HR's business only; a
# published plan is what employees see. Kept here rather than as a CHECK on the
# table: the project has none anywhere, the API is the only writer, and
# changing a CHECK on SQLite later means rebuilding the table - which
# 0005_assignment_times already cost once.
SCHEDULE_DRAFT = 'draft'
SCHEDULE_PUBLISHED = 'published'
SCHEDULE_STATES = (SCHEDULE_DRAFT, SCHEDULE_PUBLISHED)

KNOWN_SETTINGS = {'holiday_region', 'retention_months'}


def read_settings(cursor):
    cursor.execute('SELECT name, value FROM settings')
    return {row['name']: row['value'] for row in cursor.fetchall()}


def holiday_region(cursor):
    """The federal state whose holidays apply, or None if none was picked.

    None is a valid state of affairs, not an error - the tool then knows no
    holidays and behaves as it did before this stage. There is deliberately no
    default: guessing a state would be worse than having none.
    """
    return read_settings(cursor).get('holiday_region')


def holidays_for_month(cursor, year, month):
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    return holidays_in_range(first, last, holiday_region(cursor))


@app.route('/settings', methods=['GET'])
@hr_required
def get_settings():
    return jsonify(read_settings(get_db().cursor()))


@app.route('/settings', methods=['PUT'])
@hr_required
def put_settings():
    """Sets the keys it is given and leaves the rest alone.

    Deliberately not the replace-completely semantics the constraint lists use:
    a setting is not a stock someone maintains as a whole, and a caller setting
    one key should not have to know the others. An unknown key is a 400 -
    strictness is right here, because a typo would otherwise run into nothing
    and look like it worked.
    """
    connection = get_db()
    cursor = connection.cursor()
    data = request.get_json(silent=True) or {}

    unknown = set(data) - KNOWN_SETTINGS
    if unknown:
        return jsonify({'message': t(g.lang, 'unknown_setting',
                                     names=', '.join(sorted(unknown)))}), 400

    if 'holiday_region' in data and data['holiday_region'] is not None:
        if data['holiday_region'] not in REGIONS:
            return jsonify({'message': t(g.lang, 'unknown_holiday_region')}), 400

    for name, value in data.items():
        if value is None:
            cursor.execute('DELETE FROM settings WHERE name = ?', (name,))
            continue
        cursor.execute('DELETE FROM settings WHERE name = ?', (name,))
        cursor.execute('INSERT INTO settings (name, value) VALUES (?, ?)', (name, str(value)))
    connection.commit()

    return jsonify(read_settings(cursor))


@app.route('/holiday-regions', methods=['GET'])
@login_required
def list_holiday_regions():
    """The states to choose from, so the browser does not carry its own copy."""
    return jsonify([{'code': code, 'name': name} for code, name in sorted(REGIONS.items())])


def average_hours_exceeded(cursor, year, month):
    """Employees whose working time breaks § 3's eight-hour average.

    Only the ones over the line, the way coverage_gaps_for_month() reports only
    gaps - listing everyone would put the whole roster under every month.

    Reported rather than enforced, and that is the whole point: whether ten
    hours today are lawful is settled by the months that follow, so insisting
    on it while generating would mean either miscounting or restricting for no
    reason. Etappe 4 introduced max_daily_hours with a default of 10 and said
    outright that the limit is not self-supporting without this proof. This is
    the proof.

    One query for the whole window and every employee, not one per person -
    the same care coverage_gaps_for_month() takes with its three.
    """
    first, last = average_window(year, month)
    # Holidays are not working days. Empty while no state is picked, which is
    # exactly the lenient behaviour working_days_in() documents.
    working_days = working_days_in(
        first, last, set(holidays_in_range(first, last, holiday_region(cursor))))

    cursor.execute(
        'SELECT sa.employee_id, sa.schedule_id, sa.date, sa.shift_type_id, '
        '       sa.start_time, sa.end_time, sa.break_minutes, e.name AS employee_name '
        'FROM shift_assignments sa '
        'JOIN employees e ON e.id = sa.employee_id '
        'WHERE sa.date BETWEEN ? AND ? '
        'ORDER BY e.name, sa.date',
        (first.isoformat(), last.isoformat()),
    )

    minutes_by_employee = {}
    names = {}
    for row in cursor.fetchall():
        start, end = assignment_hours(cursor, row)
        if not start or not end:
            continue
        names[row['employee_id']] = row['employee_name']
        minutes_by_employee[row['employee_id']] = (
            minutes_by_employee.get(row['employee_id'], 0)
            # Net of the break, as everywhere since Etappe 5a: § 2 Abs. 1 does
            # not count rest breaks as working time.
            + net_working_minutes(shift_duration_minutes(start, end), row['break_minutes'])
        )

    over = []
    for employee_id, minutes in sorted(minutes_by_employee.items(), key=lambda kv: names[kv[0]]):
        if not exceeds_average(minutes, working_days):
            continue
        over.append({
            'employee_id': employee_id,
            'employee_name': names[employee_id],
            'hours_worked': round(minutes / 60, 1),
            'hours_allowed': working_days * MAX_AVERAGE_DAILY_HOURS,
            # Handed over because "38 hours too many" says nothing without a
            # yardstick, while "8.4 hours on average instead of 8" says it at
            # a glance.
            'average_per_working_day': round(minutes / 60 / working_days, 1),
        })
    return over


def effective_bands_by_date(cursor, year, month):
    """Every date of the month mapped to the demand bands that actually apply.

    Loaded once for the whole month rather than per day, and shared by the two
    callers that need exactly this: coverage_gaps_for_month() above, which
    compares the bands against what is staffed, and the generator, which builds
    the month's blocks out of them. Keeping it in one place is what stops the
    trimming rules below from drifting apart between "what we planned for" and
    "what we report as missing" - Etappe 3 already had that happen once with
    business_hours_for().

    Effective means: a closed date contributes nothing, and every band is
    trimmed to the opening window business_hours_for() resolves, so a special
    opening on a single date narrows or widens that date's demand and not just
    its open/closed state. Trimming is what keeps a band that predates the
    current opening hours from demanding staff for a closed business - bands
    derived by migration 0007 never passed the API's validation at all, and any
    database edited before /business-hours started cross-checking can hold the
    same thing. A date whose bands are all trimmed away is left out entirely.
    """
    bands_by_weekday = coverage_requirements_by_weekday(cursor)
    if not bands_by_weekday:
        return {}

    hours_by_weekday = load_business_hours_by_weekday(cursor)
    days_in_month = calendar.monthrange(year, month)[1]
    exceptions_by_date = business_hours_exceptions_by_date(
        cursor, date(year, month, 1).isoformat(), date(year, month, days_in_month).isoformat(),
    )

    by_date = {}
    for day in range(1, days_in_month + 1):
        day_date = date(year, month, day)
        iso_date = day_date.isoformat()
        weekday = day_date.weekday()

        bands = bands_by_weekday.get(weekday)
        if not bands:
            continue
        if _closed_on(iso_date, weekday, hours_by_weekday, exceptions_by_date):
            continue

        # Both of these read the same preloaded dicts and query nothing; the
        # second call is what turns "open at all" into "open when, exactly".
        open_time, close_time, _ = business_hours_for(
            iso_date, weekday, hours_by_weekday, exceptions_by_date)
        if open_time and close_time:
            bands = [
                trimmed for trimmed in
                (trim_band_to_hours(band, open_time, close_time) for band in bands)
                if trimmed is not None
            ]
            if not bands:
                continue

        by_date[iso_date] = bands

    return by_date


# ---------- error handling ----------
# (logging.basicConfig() lives near the top of this file now, above init_db()
# - see the comment there.)


def _request_lang():
    """g.lang, oder die Standardsprache falls der before_request-Hook nie lief."""
    return getattr(g, 'lang', DEFAULT_LANG)


@app.errorhandler(HTTPException)
def handle_http_exception(error):
    """Flasks eigene Fehler (404, 405, 413 ...) als JSON statt als HTML.

    Ohne das bekommt frontend/src/api.js eine HTML-Seite mit Fehlerstatus,
    scheitert beim Parsen und meldet "unerwartete Antwort" - was nach einer
    falsch konfigurierten API-URL aussieht statt nach dem, was wirklich war.
    """
    keys = {404: 'not_found', 405: 'method_not_allowed'}
    key = keys.get(error.code)
    message = t(_request_lang(), key) if key else (error.description or error.name)
    return jsonify({'message': message}), error.code


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    """Alles, was sonst als Stacktrace beim Nutzer landen wuerde.

    Die Kennung geht an den Aufrufer, der Grund nur ins Protokoll - eine
    Ausnahmemeldung kann Tabellen-, Spalten- oder Dateinamen enthalten.
    """
    request_id = getattr(g, 'request_id', '-')
    app.logger.exception(
        'Unbehandelter Fehler [%s] %s %s', request_id, request.method, request.path)
    return jsonify({
        'message': t(_request_lang(), 'server_error'),
        'request_id': request_id,
    }), 500


@app.route('/')
def index():
    return jsonify({'message': t(g.lang, 'api_root'), 'status': 'ok'})


def _purge_at_startup():
    """Run the retention clean-up once, when the module is imported.

    There is no scheduler on the hosting plan in use, and pretending there was
    one would be worse than saying so. In practice the service restarts on
    every deploy, which makes this the usual trigger; an instance left running
    for months needs POST /retention/purge instead. Both are documented.

    Never allowed to stop the application from starting: a clean-up that keeps
    the service down is a far bigger problem than data kept a week too long.
    """
    try:
        connection = _open_db_connection()
        try:
            cursor = connection.cursor()
            removed = purge_expired_personal_data(cursor)
            connection.commit()
            if any(removed.values()):
                app.logger.info('Aufbewahrungsfrist: %s', removed)
        finally:
            connection.close()
    except Exception:
        app.logger.exception('Aufbewahrungslauf beim Start fehlgeschlagen')


_purge_at_startup()


if __name__ == '__main__':
    # Only used for local development; hosts run this through gunicorn instead.
    app.run(debug=True, port=int(os.environ.get('PORT', 5001)))
