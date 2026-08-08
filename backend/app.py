import calendar
import hashlib
import os
import secrets
from datetime import date, datetime, timedelta
from functools import wraps

from flask import Flask, g, jsonify, request, session
from flask_cors import CORS
from werkzeug.security import check_password_hash, generate_password_hash

import mailer
from db import get_db_connection as _open_db_connection, init_db, WEEKDAYS
from i18n import DEFAULT_LANG, resolve_lang, t
from scheduler import generate_schedule, rest_gap_hours, shift_datetimes, shift_duration_minutes

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'schichtplan-local-dev')

if os.environ.get('FLASK_ENV') == 'production':
    app.config['SESSION_COOKIE_SAMESITE'] = 'None'
    app.config['SESSION_COOKIE_SECURE'] = True

# supports_credentials is required for the session cookie to survive the
# cross-origin hop from the Vite dev server to this API. X-Lang is not a
# "simple" header, so without allow_headers a cross-origin request carrying
# it would fail CORS preflight before ever reaching a route.
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
    allow_headers=['Content-Type', 'X-Lang'],
)

init_db()


@app.before_request
def resolve_request_lang():
    """The language of this one request, read fresh every time (never stored)
    from the header frontend/src/api.js sends on every call. Every message
    this API returns goes through t(g.lang, ...) rather than a hardcoded
    string - see i18n.py.
    """
    g.lang = resolve_lang(request.headers.get('X-Lang', DEFAULT_LANG))


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


def current_user_id():
    return session.get('user_id')


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
    expires_at = datetime.utcnow() + timedelta(days=INVITATION_VALID_DAYS)
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
    if as_datetime(invitation['expires_at']) < datetime.utcnow():
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
    if first_account:
        session['user_id'] = user_id

    return jsonify({
        'id': user_id,
        'username': username,
        'role': role,
        'employee_id': employee_id,
        'invitation_email': recipient_email,
        'invitation_sent': invitation_sent,
    }), 201


@app.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    connection = get_db()
    cursor = connection.cursor()
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
        return jsonify({'message': t(g.lang, 'login_failed')}), 401

    session.clear()
    session['user_id'] = user['id']
    return jsonify({
        'id': user['id'],
        'username': user['username'],
        'role': user['role'],
        'employee_id': user['employee_id'],
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
    invitation = load_invitation(cursor, token)
    if not invitation:
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
    if not value:
        return []
    try:
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

    return {
        'id': employee_id,
        'name': row['name'],
        'email': row['email'],
        'active': bool(row['active']),
        'max_shifts_per_month': row['max_shifts_per_month'],
        'weekly_hours': row['weekly_hours'],
        'min_rest_hours': row['min_rest_hours'],
        'unavailable_weekdays': unavailable_weekdays,
        'unavailable_dates': unavailable_dates,
        'allowed_shift_types': allowed_shift_types,
    }


def parse_optional_hours(value, field_key):
    """A non-negative number, or None if the field was omitted/blank.

    `field_key` names the field for the error message via an i18n key (e.g.
    'weekly_hours_label') rather than a literal string, so the message comes
    out in the request's language regardless of which field failed.
    """
    if value is None or value == '':
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError(t(g.lang, 'field_must_be_number', field=t(g.lang, field_key)))
    if value < 0:
        raise ValueError(t(g.lang, 'field_must_not_be_negative', field=t(g.lang, field_key)))
    return value


def replace_employee_constraints(connection, employee_id, data):
    cursor = connection.cursor()

    cursor.execute('DELETE FROM employee_unavailable_weekdays WHERE employee_id = ?', (employee_id,))
    for weekday in parse_int_list(data.get('unavailable_weekdays')):
        if not 0 <= weekday <= 6:
            raise ValueError(t(g.lang, 'weekday_out_of_range'))
        cursor.execute('INSERT INTO employee_unavailable_weekdays (employee_id, weekday) VALUES (?, ?)', (employee_id, weekday))

    cursor.execute('DELETE FROM employee_unavailable_dates WHERE employee_id = ?', (employee_id,))
    for entry in data.get('unavailable_dates') or []:
        iso_date = entry['date'] if isinstance(entry, dict) else entry
        reason = entry.get('reason') if isinstance(entry, dict) else None
        try:
            date.fromisoformat(iso_date)
        except (TypeError, ValueError):
            raise ValueError(t(g.lang, 'invalid_date_value', date=iso_date))
        cursor.execute('INSERT INTO employee_unavailable_dates (employee_id, date, reason) VALUES (?, ?, ?)', (employee_id, iso_date, reason))

    cursor.execute('DELETE FROM employee_allowed_shift_types WHERE employee_id = ?', (employee_id,))
    for shift_type_id in parse_int_list(data.get('allowed_shift_types')):
        cursor.execute('INSERT INTO employee_allowed_shift_types (employee_id, shift_type_id) VALUES (?, ?)', (employee_id, shift_type_id))


def serialize_shift_type(cursor, row):
    shift_type_id = row['id']
    cursor.execute('SELECT weekday, required_count FROM shift_requirements WHERE shift_type_id = ?', (shift_type_id,))
    by_weekday = {r['weekday']: r['required_count'] for r in cursor.fetchall()}
    requirements = [by_weekday.get(wd, 0) for wd in range(7)]

    return {
        'id': shift_type_id,
        'name': row['name'],
        'start_time': row['start_time'],
        'end_time': row['end_time'],
        'color': row['color'],
        'requirements': requirements,
    }


def replace_shift_requirements(connection, shift_type_id, requirements):
    if requirements is None:
        requirements = [0] * 7
    if len(requirements) != 7:
        raise ValueError(t(g.lang, 'requirements_length'))

    cursor = connection.cursor()
    cursor.execute('DELETE FROM shift_requirements WHERE shift_type_id = ?', (shift_type_id,))
    for weekday, count in enumerate(requirements):
        try:
            count = int(count)
        except (TypeError, ValueError):
            # Same normalisation as parse_int_list: a null or other non-number
            # in the list must be a 400, not an unhandled 500.
            raise ValueError(t(g.lang, 'requirements_must_be_int'))
        if count < 0:
            raise ValueError(t(g.lang, 'requirements_must_not_be_negative'))
        cursor.execute('INSERT INTO shift_requirements (shift_type_id, weekday, required_count) VALUES (?, ?, ?)', (shift_type_id, weekday, count))


# ---------- employees ----------

@app.route('/employees', methods=['GET'])
@hr_required
def list_employees():
    # HR-only: an employee account is shown its own shifts, which already carry
    # the shift name and hours, so it never needs the roster - and the roster is
    # colleagues' personal data.
    connection = get_db()
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM employees ORDER BY name')
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
        cursor.execute(
            'INSERT INTO employees (name, email, active, max_shifts_per_month, weekly_hours, min_rest_hours) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (name, data.get('email'), 1 if data.get('active', True) else 0, data.get('max_shifts_per_month'),
             weekly_hours, min_rest_hours if min_rest_hours is not None else 11),
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
        cursor.execute(
            'UPDATE employees SET name = ?, email = ?, active = ?, max_shifts_per_month = ?, '
            'weekly_hours = ?, min_rest_hours = ? WHERE id = ?',
            (name, data.get('email'), 1 if data.get('active', True) else 0, data.get('max_shifts_per_month'),
             weekly_hours, min_rest_hours if min_rest_hours is not None else 11, employee_id),
        )
        replace_employee_constraints(connection, employee_id, data)
        connection.commit()
        cursor.execute('SELECT * FROM employees WHERE id = ?', (employee_id,))
        employee = serialize_employee(cursor, cursor.fetchone())
    except ValueError as e:
        return jsonify({'message': str(e)}), 400
    return jsonify(employee)


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

    cursor.execute('DELETE FROM employees WHERE id = ?', (employee_id,))
    connection.commit()
    return jsonify({'message': t(g.lang, 'employee_deleted')}), 200


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
    allowed for the month the server's clock says it is right now.
    """
    today = date.today()
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    return today.replace(day=1).isoformat(), today.replace(day=days_in_month).isoformat()


@app.route('/employees/<int:employee_id>/absences', methods=['GET'])
def list_absences(employee_id):
    error = require_self_or_hr(employee_id)
    if error:
        return error

    try:
        year = int(request.args['year']) if 'year' in request.args else date.today().year
        month = int(request.args['month']) if 'month' in request.args else date.today().month
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
        date.fromisoformat(iso_date)
    except (TypeError, ValueError):
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
        date.fromisoformat(iso_date)
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
        replace_shift_requirements(connection, shift_type_id, data.get('requirements'))
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
        replace_shift_requirements(connection, shift_type_id, data.get('requirements'))
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

def load_employees_for_scheduling(cursor):
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
        employees.append({
            'id': employee_id,
            'max_shifts_per_month': row['max_shifts_per_month'],
            'weekly_hours': row['weekly_hours'],
            'min_rest_hours': row['min_rest_hours'],
            'unavailable_weekdays': unavailable_weekdays,
            'unavailable_dates': unavailable_dates,
            'allowed_shift_types': allowed if allowed else None,
        })
    return employees


def load_shift_types_for_scheduling(cursor):
    cursor.execute('SELECT * FROM shift_types')
    shift_types = []
    for row in cursor.fetchall():
        cursor.execute('SELECT weekday, required_count FROM shift_requirements WHERE shift_type_id = ?', (row['id'],))
        requirements = {r['weekday']: r['required_count'] for r in cursor.fetchall()}
        shift_types.append({
            'id': row['id'],
            'requirements': requirements,
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
               sa.absence_type, sa.absent_employee_id,
               st.name AS shift_type_name, st.color AS shift_type_color, st.start_time, st.end_time,
               e.name AS employee_name, ae.name AS absent_employee_name
        FROM shift_assignments sa
        JOIN shift_types st ON st.id = sa.shift_type_id
        LEFT JOIN employees e ON e.id = sa.employee_id
        LEFT JOIN employees ae ON ae.id = sa.absent_employee_id
        WHERE sa.schedule_id = ?
        ORDER BY sa.date, st.start_time, sa.slot_index
    ''', (schedule['id'],))

    assignments = []
    for row in cursor.fetchall():
        a = dict(row)
        a['manually_edited'] = bool(a['manually_edited'])
        # The shift type's hours are the default; a per-date override wins.
        override = overrides.get((a['date'], a['shift_type_id']))
        a['default_start_time'] = a['start_time']
        a['default_end_time'] = a['end_time']
        a['time_overridden'] = override is not None
        if override:
            a['start_time'] = override['start_time']
            a['end_time'] = override['end_time']
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
        'unfilled_count': schedule['unfilled_count'],
        'generated_at': schedule['generated_at'],
        'assignments': assignments,
        'absences': absences,
        'distribution': build_distribution(assignments, active_employees),
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

    employees = load_employees_for_scheduling(cursor)

    try:
        result = generate_schedule(year, month, employees, shift_types, weekend_weight=weekend_weight)
    except ValueError:
        return jsonify({'message': t(g.lang, 'invalid_year_or_month')}), 400

    cursor.execute('SELECT id FROM schedules WHERE year = ? AND month = ?', (year, month))
    existing = cursor.fetchone()
    if existing:
        schedule_id = existing['id']
        cursor.execute('DELETE FROM shift_assignments WHERE schedule_id = ?', (schedule_id,))
        cursor.execute(
            "UPDATE schedules SET status = 'generated', unfilled_count = ?, generated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (result['unfilled_count'], schedule_id),
        )
    else:
        cursor.execute(
            "INSERT INTO schedules (year, month, status, unfilled_count, generated_at) VALUES (?, ?, 'generated', ?, CURRENT_TIMESTAMP)",
            (year, month, result['unfilled_count']),
        )
        schedule_id = cursor.lastrowid

    for a in result['assignments']:
        cursor.execute(
            'INSERT INTO shift_assignments (schedule_id, date, shift_type_id, slot_index, employee_id) VALUES (?, ?, ?, ?, ?)',
            (schedule_id, a['date'], a['shift_type_id'], a['slot_index'], a['employee_id']),
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
    schedule['scope'] = 'own'
    schedule['unfilled_count'] = 0
    schedule['linked_employee_id'] = linked_employee_id

    return jsonify(schedule)


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
        date.fromisoformat(iso_date)
    except (TypeError, ValueError):
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
    """
    data = request.get_json(silent=True) or {}
    iso_date = data.get('date')
    shift_type_id = data.get('shift_type_id')

    try:
        parsed = date.fromisoformat(iso_date)
    except (TypeError, ValueError):
        return jsonify({'message': t(g.lang, 'invalid_date')}), 400
    if (parsed.year, parsed.month) != (year, month):
        return jsonify({'message': t(g.lang, 'date_not_in_month')}), 400

    connection = get_db()
    cursor = connection.cursor()

    schedule_id = find_schedule_id(cursor, year, month)
    if not schedule_id:
        return jsonify({'message': t(g.lang, 'no_schedule_found')}), 404

    cursor.execute('SELECT id FROM shift_types WHERE id = ?', (shift_type_id,))
    if not cursor.fetchone():
        return jsonify({'message': t(g.lang, 'shift_type_not_found')}), 404

    cursor.execute(
        'SELECT COALESCE(MAX(slot_index), -1) AS highest FROM shift_assignments '
        'WHERE schedule_id = ? AND date = ? AND shift_type_id = ?',
        (schedule_id, iso_date, shift_type_id),
    )
    next_index = cursor.fetchone()['highest'] + 1

    cursor.execute(
        'INSERT INTO shift_assignments (schedule_id, date, shift_type_id, slot_index, employee_id, manually_edited) '
        'VALUES (?, ?, ?, ?, NULL, 1)',
        (schedule_id, iso_date, shift_type_id, next_index),
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
    """A shift's actual hours on one date: a per-date override if one exists, else the shift type's usual hours."""
    cursor.execute(
        'SELECT start_time, end_time FROM shift_time_overrides WHERE schedule_id = ? AND date = ? AND shift_type_id = ?',
        (schedule_id, iso_date, shift_type_id),
    )
    override = cursor.fetchone()
    if override:
        return override['start_time'], override['end_time']
    return default_start, default_end


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


def constraint_warnings(cursor, employee_id, assignment_date, shift_type_id, schedule_id, exclude_assignment_id=None):
    """Non-blocking warnings for assigning `employee_id` to one shift.

    Unlike the scheduler's hard constraints (which only ever see one month at a
    time), this runs against already-saved data, so the weekly-hours and
    rest-period checks below deliberately query shift_assignments *without*
    scoping by schedule_id - the employee's neighbouring shift may belong to a
    different month's schedule row, and it should still be found.
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

    cursor.execute('SELECT 1 FROM employee_allowed_shift_types WHERE employee_id = ?', (employee_id,))
    if cursor.fetchone():
        cursor.execute('SELECT 1 FROM employee_allowed_shift_types WHERE employee_id = ? AND shift_type_id = ?', (employee_id, shift_type_id))
        if not cursor.fetchone():
            warnings.append(t(g.lang, 'warn_restricted_shift_types', name=employee['name']))

    query = 'SELECT 1 FROM shift_assignments WHERE date = ? AND employee_id = ?'
    params = [assignment_date, employee_id]
    if exclude_assignment_id is not None:
        query += ' AND id != ?'
        params.append(exclude_assignment_id)
    cursor.execute(query, params)
    if cursor.fetchone():
        warnings.append(t(g.lang, 'warn_already_assigned_that_day', name=employee['name']))

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
            SELECT sa.id, sa.date, sa.schedule_id, sa.shift_type_id, st.start_time, st.end_time
            FROM shift_assignments sa
            JOIN shift_types st ON st.id = sa.shift_type_id
            WHERE sa.employee_id = ? AND sa.date BETWEEN ? AND ?
        ''', (employee_id, week_start, week_end))
        total_minutes = 0
        for row in cursor.fetchall():
            if exclude_assignment_id is not None and row['id'] == exclude_assignment_id:
                continue
            start, end = effective_shift_hours(
                cursor, row['schedule_id'], row['date'], row['shift_type_id'], row['start_time'], row['end_time'])
            total_minutes += shift_duration_minutes(start, end)

        cursor.execute('SELECT start_time, end_time FROM shift_types WHERE id = ?', (shift_type_id,))
        proposed_type = cursor.fetchone()
        if proposed_type:
            new_start, new_end = effective_shift_hours(
                cursor, schedule_id, assignment_date, shift_type_id, proposed_type['start_time'], proposed_type['end_time'])
            total_minutes += shift_duration_minutes(new_start, new_end)

        if total_minutes > employee['weekly_hours'] * 60:
            warnings.append(t(g.lang, 'warn_weekly_hours_exceeded', name=employee['name'],
                             hours=total_minutes / 60, target=employee['weekly_hours']))

    cursor.execute('SELECT start_time, end_time FROM shift_types WHERE id = ?', (shift_type_id,))
    this_shift_type = cursor.fetchone()
    if this_shift_type:
        cur_start, cur_end = effective_shift_hours(
            cursor, schedule_id, assignment_date, shift_type_id, this_shift_type['start_time'], this_shift_type['end_time'])
        this_shift = shift_datetimes(assignment_date, cur_start, cur_end)
        min_rest = employee['min_rest_hours']
        d = date.fromisoformat(assignment_date)

        # (neighbouring date, is that neighbour the earlier of the two shifts?)
        neighbors = [((d - timedelta(days=1)).isoformat(), True), ((d + timedelta(days=1)).isoformat(), False)]
        for neighbor_date, neighbor_is_earlier in neighbors:
            query = 'SELECT id, schedule_id, shift_type_id FROM shift_assignments WHERE employee_id = ? AND date = ?'
            params = [employee_id, neighbor_date]
            if exclude_assignment_id is not None:
                query += ' AND id != ?'
                params.append(exclude_assignment_id)
            cursor.execute(query, params)
            neighbor = cursor.fetchone()
            if not neighbor:
                continue
            cursor.execute('SELECT start_time, end_time FROM shift_types WHERE id = ?', (neighbor['shift_type_id'],))
            neighbor_type = cursor.fetchone()
            if not neighbor_type:
                continue
            n_start, n_end = effective_shift_hours(
                cursor, neighbor['schedule_id'], neighbor_date, neighbor['shift_type_id'],
                neighbor_type['start_time'], neighbor_type['end_time'])
            neighbor_shift = shift_datetimes(neighbor_date, n_start, n_end)

            gap = (rest_gap_hours(neighbor_shift, this_shift) if neighbor_is_earlier
                   else rest_gap_hours(this_shift, neighbor_shift))
            if gap < min_rest:
                warnings.append(t(g.lang, 'warn_rest_period_too_short', name=employee['name'],
                                 gap=gap, required=min_rest))

    return warnings


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

    warnings = constraint_warnings(
        cursor, employee_id, assignment['date'], assignment['shift_type_id'], assignment['schedule_id'],
        exclude_assignment_id=assignment_id,
    )

    cursor.execute('UPDATE shift_assignments SET employee_id = ?, manually_edited = 1 WHERE id = ?', (employee_id, assignment_id))
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

    warnings = []
    warnings += constraint_warnings(cursor, b['employee_id'], a['date'], a['shift_type_id'], a['schedule_id'], exclude_assignment_id=a['id'])
    warnings += constraint_warnings(cursor, a['employee_id'], b['date'], b['shift_type_id'], b['schedule_id'], exclude_assignment_id=b['id'])

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


@app.route('/')
def index():
    return jsonify({'message': t(g.lang, 'api_root'), 'status': 'ok'})


if __name__ == '__main__':
    # Only used for local development; hosts run this through gunicorn instead.
    app.run(debug=True, port=int(os.environ.get('PORT', 5001)))
