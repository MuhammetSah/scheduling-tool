"""Backend message translations.

Two languages (`de`, `en`), chosen per request from the `X-Lang` header the
frontend sends on every call (see app.py's before_request hook) and never
persisted server-side - this is a stateless lookup, not a locale/timezone/
currency system, and it only ever covers strings this API itself returns.
"""

DEFAULT_LANG = 'de'
SUPPORTED_LANGS = ('de', 'en')

TRANSLATIONS = {
    # ---- auth / sessions ----
    'not_signed_in': {
        'de': 'Nicht angemeldet',
        'en': 'Not signed in',
    },
    'hr_only': {
        'de': 'Nur die Personalabteilung hat darauf Zugriff',
        'en': 'Only HR has access to this',
    },
    'forbidden': {
        'de': 'Dazu haben Sie keine Berechtigung',
        'en': 'You are not authorized to do this',
    },
    'username_required': {
        'de': 'Benutzername ist erforderlich',
        'en': 'Username is required',
    },
    'accounts_hr_only': {
        'de': 'Nur die Personalabteilung darf Konten anlegen',
        'en': 'Only HR may create accounts',
    },
    'accounts_signin_required': {
        'de': 'Neue Konten kann nur ein angemeldeter Benutzer anlegen',
        'en': 'You must be signed in to create new accounts',
    },
    'unknown_role': {
        'de': 'Unbekannte Rolle',
        'en': 'Unknown role',
    },
    'employee_account_needs_link': {
        'de': 'Ein Mitarbeiter-Konto muss mit einem Mitarbeiter verknüpft werden',
        'en': 'An employee account must be linked to an employee',
    },
    'employee_not_found': {
        'de': 'Mitarbeiter nicht gefunden',
        'en': 'Employee not found',
    },
    'valid_email_required': {
        'de': 'Bitte eine gültige E-Mail-Adresse angeben',
        'en': 'Please provide a valid email address',
    },
    'employee_missing_email': {
        'de': '{name} hat keine E-Mail-Adresse. Bitte zuerst beim Mitarbeiter hinterlegen.',
        'en': '{name} has no email address on file. Please add one on the employee record first.',
    },
    'email_required_for_invitation': {
        'de': 'E-Mail-Adresse ist erforderlich, um die Einladung zu senden',
        'en': 'An email address is required to send the invitation',
    },
    'password_required': {
        'de': 'Passwort ist erforderlich',
        'en': 'Password is required',
    },
    'password_too_short': {
        'de': 'Das Passwort muss mindestens {n} Zeichen lang sein',
        'en': 'The password must be at least {n} characters long',
    },
    'username_taken': {
        'de': 'Benutzername ist bereits vergeben',
        'en': 'That username is already taken',
    },
    'password_not_set_yet': {
        'de': 'Für dieses Konto wurde noch kein Passwort vergeben. '
              'Bitte den Link aus der Einladungs-E-Mail verwenden.',
        'en': 'No password has been set for this account yet. '
              'Please use the link from the invitation email.',
    },
    'login_failed': {
        'de': 'Benutzername oder Passwort ist falsch',
        'en': 'Incorrect username or password',
    },
    'too_many_login_attempts': {
        'de': 'Zu viele fehlgeschlagene Anmeldeversuche. Bitte in {minutes} Minuten erneut versuchen.',
        'en': 'Too many failed sign-in attempts. Please try again in {minutes} minutes.',
    },
    'logged_out': {
        'de': 'Abgemeldet',
        'en': 'Signed out',
    },
    'invitation_invalid': {
        'de': 'Dieser Link ist ungültig oder abgelaufen',
        'en': 'This link is invalid or has expired',
    },
    'password_set': {
        'de': 'Passwort gesetzt. Sie können sich jetzt anmelden.',
        'en': 'Password set. You can now sign in.',
    },

    # ---- employees ----
    'name_required': {
        'de': 'Name ist erforderlich',
        'en': 'Name is required',
    },
    'employee_deleted': {
        'de': 'Mitarbeiter gelöscht',
        'en': 'Employee deleted',
    },
    'delete_linked_account_first': {
        'de': 'Zuerst das verknüpfte Konto löschen: {accounts}',
        'en': 'Please delete the linked account first: {accounts}',
    },
    'weekly_hours_label': {
        'de': 'Die Zielstundenzahl pro Woche',
        'en': 'The weekly target hours',
    },
    'min_rest_hours_label': {
        'de': 'Die Mindestruhezeit',
        'en': 'The minimum rest period',
    },
    'max_daily_hours_label': {
        'de': 'Die tägliche Höchstarbeitszeit',
        'en': 'The maximum daily working hours',
    },
    'max_daily_hours_out_of_range': {
        'de': 'Die tägliche Höchstarbeitszeit muss über 0 liegen und darf {max} Stunden '
              'nicht überschreiten (§ 3 ArbZG)',
        'en': 'The maximum daily working hours must be above 0 and may not exceed {max} '
              'hours (§ 3 ArbZG)',
    },
    'request_body_must_be_object': {
        'de': 'Der Anfragerumpf muss ein JSON-Objekt sein',
        'en': 'The request body must be a JSON object',
    },
    'field_must_be_number': {
        'de': '{field} muss eine Zahl sein',
        'en': '{field} must be a number',
    },
    'field_must_not_be_negative': {
        'de': '{field} darf nicht negativ sein',
        'en': '{field} must not be negative',
    },
    'int_list_required': {
        'de': 'Die Liste darf nur ganze Zahlen enthalten',
        'en': 'The list may only contain whole numbers',
    },
    'weekday_out_of_range': {
        'de': 'Wochentag muss zwischen 0 (Montag) und 6 (Sonntag) liegen',
        'en': 'Weekday must be between 0 (Monday) and 6 (Sunday)',
    },
    'availability_window_duplicate': {
        'de': 'Das Fenster {weekday} {start}–{end} ist doppelt angegeben',
        'en': 'The window {weekday} {start}–{end} is given twice',
    },
    'swap_needs_own_shift': {
        'de': 'Ein Tauschantrag geht immer von einer eigenen Schicht aus.',
        'en': 'A swap request always starts from a shift of your own.',
    },
    'swap_needs_a_partner': {
        'de': 'Die zweite Schicht muss einer anderen Person gehören.',
        'en': 'The second shift must belong to somebody else.',
    },
    'swap_would_break_the_law': {
        'de': 'Dieser Tausch ist nicht möglich: er würde zwingendes '
              'Arbeitszeitrecht verletzen.',
        'en': 'This swap is not possible: it would breach compulsory '
              'working-time law.',
    },
    'unknown_swap_status': {
        'de': 'Unbekannter Stand. Erlaubt sind: {allowed}',
        'en': 'Unknown status. Allowed values are: {allowed}',
    },
    'swap_request_not_found': {
        'de': 'Tauschantrag nicht gefunden',
        'en': 'Swap request not found',
    },
    'swap_request_already_settled': {
        'de': 'Dieser Tauschantrag ist bereits entschieden ({status}).',
        'en': 'This swap request has already been settled ({status}).',
    },
    'swap_shifts_changed_hands': {
        'de': 'Eine der beiden Schichten ist inzwischen anders besetzt. '
              'Zugestimmt wurde einem anderen Tausch als dem, der jetzt '
              'zustande käme.',
        'en': 'One of the two shifts has changed hands since. What was agreed '
              'to is not the swap that would happen now.',
    },
    'swap_needs_partner_consent': {
        'de': 'Ohne die Zustimmung der Tauschpartnerin oder des Tauschpartners '
              'wäre es kein Tausch, sondern eine Umsetzung.',
        'en': 'Without the swap partner’s consent this would not be a swap but '
              'a reassignment.',
    },
    'break_start_needs_minutes': {
        'de': 'Eine Uhrzeit ohne Pausendauer beschreibt keine Pause.',
        'en': 'A time without a break duration does not describe a break.',
    },
    'break_start_needs_times': {
        'de': 'Die Lage der Pause braucht einen Block mit bekannten Zeiten.',
        'en': 'A break position needs a block with known hours.',
    },
    'break_start_outside_block': {
        'de': 'Die Pause muss innerhalb des Blocks {start}–{end} liegen.',
        'en': 'The break has to fall inside the block {start}–{end}.',
    },
    'warn_stretch_without_break': {
        'de': '{name} arbeitet {hours:.1f} Std. am Stück ohne Pause – '
              '§ 4 Satz 3 ArbZG erlaubt höchstens sechs',
        'en': '{name} works {hours:.1f} hrs in one go without a break – '
              '§ 4 Satz 3 ArbZG allows at most six',
    },
    'warn_sunday_work': {
        'de': 'Der {date} ist ein Sonntag – § 9 Abs. 1 ArbZG verbietet '
              'Sonntagsarbeit, sofern der Betrieb nicht unter § 10 fällt '
              '(unter Öffnungszeiten einstellbar)',
        'en': 'The {date} is a Sunday – § 9 Abs. 1 ArbZG forbids Sunday work '
              'unless the business falls under § 10 (set under opening hours)',
    },
    'qualification_exists': {
        'de': 'Den Nachweis „{name}" gibt es bereits.',
        'en': 'The certificate “{name}” already exists.',
    },
    'qualification_not_found': {
        'de': 'Nachweis nicht gefunden',
        'en': 'Certificate not found',
    },
    'qualification_deleted': {
        'de': 'Nachweis gelöscht',
        'en': 'Certificate deleted',
    },
    'qualification_listed_twice': {
        'de': 'Derselbe Nachweis ist doppelt angegeben.',
        'en': 'The same certificate is listed twice.',
    },
    'warn_missing_qualification': {
        'de': '{name} hat den Nachweis „{qualification}" nicht, den diese Schicht verlangt',
        'en': '{name} does not hold the certificate “{qualification}” this shift requires',
    },
    'warn_expired_qualification': {
        'de': '{name}s Nachweis „{qualification}" ist am {date} abgelaufen',
        'en': '{name}’s certificate “{qualification}” expired on {date}',
    },
    'invalid_date_value': {
        'de': 'Ungültiges Datum: {date}',
        'en': 'Invalid date: {date}',
    },
    'break_minutes_invalid': {
        'de': 'Die Pause muss eine ganze Zahl von Minuten sein und darf nicht negativ sein',
        'en': 'The break must be a whole, non-negative number of minutes',
    },
    'availability_mode_invalid': {
        'de': 'Unbekannter Verfügbarkeitsmodus. Erlaubt sind "anytime" und "windows".',
        'en': 'Unknown availability mode. Allowed values are "anytime" and "windows".',
    },
    'availability_entry_invalid': {
        'de': 'Jeder Eintrag unter "availability" muss ein Objekt mit Wochentag und Uhrzeiten sein.',
        'en': 'Each entry under "availability" must be an object with a weekday and times.',
    },
    'availability_time_invalid': {
        'de': 'Ungültige Uhrzeit "{value}". Erwartet wird HH:MM.',
        'en': 'Invalid time "{value}". Expected HH:MM.',
    },
    'availability_window_empty': {
        'de': 'Start- und Endzeit eines Fensters dürfen nicht gleich sein.',
        'en': 'A window\'s start and end time must differ.',
    },
    'availability_valid_range_invalid': {
        'de': 'Das Gültigkeitsende darf nicht vor dem Gültigkeitsbeginn liegen.',
        'en': 'The validity end date must not be before its start date.',
    },

    # ---- self-service absences (sick / vacation) ----
    'year_month_must_be_numbers': {
        'de': 'Jahr und Monat müssen Zahlen sein',
        'en': 'Year and month must be numbers',
    },
    'month_out_of_range': {
        'de': 'Monat muss zwischen 1 und 12 liegen',
        'en': 'Month must be between 1 and 12',
    },
    'invalid_date': {
        'de': 'Ungültiges Datum',
        'en': 'Invalid date',
    },
    'absence_type_invalid': {
        'de': "Typ muss 'sick' oder 'vacation' sein",
        'en': "Type must be 'sick' or 'vacation'",
    },
    'absence_current_month_only': {
        'de': 'Krank- und Urlaubsmeldungen sind nur für den aktuellen Monat möglich',
        'en': 'Sick and vacation reports are only possible for the current month',
    },
    'absence_not_found': {
        'de': 'Keine Abwesenheit für dieses Datum gefunden',
        'en': 'No absence found for this date',
    },
    'absence_removed': {
        'de': 'Abwesenheit entfernt',
        'en': 'Absence removed',
    },

    # ---- accounts ----
    'account_not_found': {
        'de': 'Konto nicht gefunden',
        'en': 'Account not found',
    },
    'account_missing_email': {
        'de': 'Für dieses Konto ist keine E-Mail-Adresse hinterlegt',
        'en': 'No email address is on file for this account',
    },
    'invitation_email_sent': {
        'de': 'Einladung an {email} gesendet',
        'en': 'Invitation sent to {email}',
    },
    'invitation_logged': {
        'de': 'Einladung für {email} erstellt (kein SMTP konfiguriert - Link steht im Server-Log)',
        'en': 'Invitation created for {email} (no SMTP configured - the link is in the server log)',
    },
    'cannot_delete_own_account': {
        'de': 'Das eigene Konto kann nicht gelöscht werden',
        'en': 'You cannot delete your own account',
    },
    'cannot_delete_last_hr_account': {
        'de': 'Das letzte Personal-Konto kann nicht gelöscht werden',
        'en': 'The last HR account cannot be deleted',
    },
    'account_deleted': {
        'de': 'Konto {username} gelöscht',
        'en': 'Account {username} deleted',
    },

    # ---- shift types ----
    'shift_type_fields_required': {
        'de': 'Name, Beginn und Ende sind erforderlich',
        'en': 'Name, start and end are required',
    },
    'shift_type_not_found': {
        'de': 'Schichtart nicht gefunden',
        'en': 'Shift type not found',
    },
    'shift_type_in_use': {
        'de': 'Schichtart wird in einem bestehenden Plan verwendet und kann nicht gelöscht werden',
        'en': 'This shift type is used in an existing plan and cannot be deleted',
    },
    'shift_type_deleted': {
        'de': 'Schichtart gelöscht',
        'en': 'Shift type deleted',
    },

    # ---- schedule generation ----
    'year_month_required': {
        'de': 'Jahr und Monat sind als Zahl erforderlich',
        'en': 'Year and month are required as numbers',
    },
    'weekend_weight_must_be_int': {
        'de': 'weekend_weight muss eine ganze Zahl sein',
        'en': 'weekend_weight must be a whole number',
    },
    'weekend_weight_must_not_be_negative': {
        'de': 'weekend_weight darf nicht negativ sein',
        'en': 'weekend_weight must not be negative',
    },
    'need_a_shift_type_first': {
        'de': 'Bitte zuerst mindestens eine Schichtart anlegen',
        'en': 'Please create at least one shift type first',
    },
    'invalid_year_or_month': {
        'de': 'Ungültiges Jahr oder Monat',
        'en': 'Invalid year or month',
    },
    'no_schedule_generated_yet': {
        'de': 'Für diesen Monat wurde noch kein Plan generiert',
        'en': 'No plan has been generated for this month yet',
    },
    'no_schedule_found': {
        'de': 'Für diesen Monat wurde kein Plan gefunden',
        'en': 'No plan was found for this month',
    },
    'schedule_deleted': {
        'de': 'Plan gelöscht',
        'en': 'Plan deleted',
    },
    'regenerate_would_discard_edits': {
        'de': 'Der Plan enthält {n} von Hand bearbeitete Schichten, die beim '
              'Neuerzeugen verloren gehen. Zum Fortfahren bestätigen.',
        'en': 'The schedule contains {n} manually edited shifts that would be lost '
              'by regenerating. Confirm to continue.',
    },

    # ---- day-level editing (times, extra places) ----
    'time_format_hint': {
        'de': 'Zeiten müssen im Format HH:MM angegeben werden',
        'en': 'Times must be given in HH:MM format',
    },
    'times_reset_to_default': {
        'de': 'Zeiten auf die Standardzeiten zurückgesetzt',
        'en': 'Times reset to the shift type default',
    },
    'times_changed': {
        'de': 'Zeiten für diesen Tag geändert',
        'en': 'Times changed for this day',
    },
    'date_not_in_month': {
        'de': 'Das Datum liegt nicht in diesem Monat',
        'en': 'That date is not in this month',
    },
    'slot_added': {
        'de': 'Platz hinzugefügt',
        'en': 'Slot added',
    },
    'assignment_not_found': {
        'de': 'Zuweisung nicht gefunden',
        'en': 'Assignment not found',
    },
    'slot_removed': {
        'de': 'Platz entfernt',
        'en': 'Slot removed',
    },

    # ---- manual editing (reassign / swap) ----
    'employee_id_required': {
        'de': 'employee_id ist erforderlich (null, um die Schicht unbesetzt zu lassen)',
        'en': 'employee_id is required (null to leave the shift unfilled)',
    },
    'assignment_times_need_both': {
        'de': 'Start- und Endzeit müssen zusammen gesetzt oder zusammen leer sein.',
        'en': 'Start and end time must be set together or left empty together.',
    },
    'assignment_times_must_differ': {
        'de': 'Start- und Endzeit einer Zuweisung dürfen nicht gleich sein.',
        'en': "An assignment's start and end time must differ.",
    },
    'assignment_without_shift_type_needs_times': {
        'de': 'Ein Block ohne Schichtart braucht eigene Zeiten — er hat keine Vorlage, von der er sie erben könnte.',
        'en': 'A block without a shift type needs its own hours — it has no template to inherit them from.',
    },
    'assignment_updated': {
        'de': 'Zuweisung aktualisiert',
        'en': 'Assignment updated',
    },
    'two_assignment_ids_required': {
        'de': 'Zwei unterschiedliche Zuweisungs-IDs sind erforderlich',
        'en': 'Two different assignment IDs are required',
    },
    'swap_same_schedule_only': {
        'de': 'Schichten können nur innerhalb desselben Plans getauscht werden',
        'en': 'Shifts can only be swapped within the same plan',
    },
    'shifts_swapped': {
        'de': 'Schichten getauscht',
        'en': 'Shifts swapped',
    },

    # ---- constraint warnings (non-blocking, shown on manual edits) ----
    'warn_not_usual_weekday': {
        'de': '{name} arbeitet normalerweise nicht {weekday}',
        'en': '{name} does not usually work on {weekday}',
    },
    'warn_marked_unavailable': {
        'de': '{name} ist am {date} als nicht verfügbar eingetragen',
        'en': '{name} is marked unavailable on {date}',
    },
    'warn_restricted_shift_types': {
        'de': '{name} ist normalerweise auf andere Schichtarten beschränkt',
        'en': '{name} is normally restricted to other shift types',
    },
    'warn_already_assigned_that_day': {
        'de': '{name} ist an diesem Tag bereits einer anderen Schicht zugeteilt',
        'en': '{name} is already assigned to another shift that day',
    },
    'warn_overlapping_blocks': {
        'de': '{name} hat am {date} bereits einen Block von {start}–{end}, der sich damit überschneidet',
        'en': '{name} already has a block from {start}–{end} on {date} that overlaps this one',
    },
    'warn_seventh_consecutive_day': {
        'de': '{name} käme damit auf {days} Tage in Folge; nach § 11 Abs. 3 ArbZG ist spätestens nach sechs ein Ersatzruhetag fällig',
        'en': '{name} would then work {days} days in a row; § 11 Abs. 3 ArbZG calls for a rest day after six at the latest',
    },
    'warn_sunday_budget_exhausted': {
        'de': '{name} hätte damit nur noch {free} freie Sonntage in {year}; § 11 Abs. 1 ArbZG verlangt mindestens 15',
        'en': '{name} would be left with only {free} free Sundays in {year}; § 11 Abs. 1 ArbZG requires at least 15',
    },
    'schedule_not_published_yet': {
        'de': 'Der Plan für diesen Monat ist noch nicht veröffentlicht',
        'en': 'The schedule for this month has not been published yet',
    },
    'unknown_schedule_status': {
        'de': 'Unbekannter Zustand. Erlaubt sind: {allowed}',
        'en': 'Unknown status. Allowed values are: {allowed}',
    },
    'anonymised_employee_name': {
        'de': 'Gelöschter Mitarbeiter #{id}',
        'en': 'Deleted employee #{id}',
    },
    'employee_anonymised': {
        'de': 'Mitarbeiter gelöscht. Die vergangenen Schichten bleiben ohne Namen bestehen — § 16 Abs. 2 ArbZG verlangt, Arbeitszeitnachweise mindestens zwei Jahre aufzubewahren.',
        'en': 'Employee deleted. Past shifts remain without a name — § 16 Abs. 2 ArbZG requires working-time records to be kept for at least two years.',
    },
    'retention_purged': {
        'de': 'Aufräumen abgeschlossen',
        'en': 'Clean-up finished',
    },
    'free_block_label': {
        'de': 'Dienst',
        'en': 'Shift',
    },
    'limit_must_be_int': {
        'de': 'limit muss eine positive ganze Zahl sein',
        'en': 'limit must be a positive whole number',
    },
    'unknown_setting': {
        'de': 'Unbekannte Einstellung: {names}',
        'en': 'Unknown setting: {names}',
    },
    'unknown_holiday_region': {
        'de': 'Unbekanntes Bundesland',
        'en': 'Unknown federal state',
    },
    'warn_public_holiday': {
        'de': '{date} ist ein gesetzlicher Feiertag ({name}); nach § 9 ArbZG darf dort nur gearbeitet werden, wenn der Betrieb unter eine Ausnahme des § 10 fällt',
        'en': '{date} is a public holiday ({name}); under § 9 ArbZG work is only allowed there if the business falls under an exemption in § 10',
    },
    'warn_break_below_minimum': {
        'de': '{name} hätte bei {hours:.1f} Std. nur {minutes} Min. Pause; nach § 4 ArbZG sind mindestens {required} Min. vorgeschrieben',
        'en': '{name} would get only {minutes} min of break for {hours:.1f}h; § 4 ArbZG requires at least {required} min',
    },
    'warn_daily_hours_exceeded': {
        'de': '{name} käme am {date} auf {hours:.1f} Std.; die tägliche Höchstarbeitszeit liegt bei {cap:g} Std.',
        'en': '{name} would work {hours:.1f}h on {date}; the maximum daily working time is {cap:g}h',
    },
    'warn_monthly_cap_reached': {
        'de': '{name} hat das monatliche Limit von {limit} Schichten bereits erreicht',
        'en': '{name} has already reached the monthly limit of {limit} shifts',
    },
    'warn_weekly_hours_exceeded': {
        'de': '{name} käme damit auf {hours:.1f} Std. in dieser Woche - über dem Ziel von {target:g} Std./Woche',
        'en': '{name} would then be at {hours:.1f}h this week - over the {target:g}h/week target',
    },
    'warn_rest_period_too_short': {
        'de': '{name} hätte dann nur {gap:.1f} Std. Ruhezeit statt der geforderten {required:g} Std.',
        'en': '{name} would then have only {gap:.1f}h of rest instead of the required {required:g}h',
    },
    'warn_outside_availability': {
        'de': '{name} arbeitet {weekday} normalerweise nur {windows}.',
        'en': '{name} normally only works {weekday} {windows}.',
    },
    'warn_outside_availability_no_window': {
        'de': '{name} arbeitet {weekday} normalerweise gar nicht.',
        'en': '{name} normally does not work {weekday} at all.',
    },

    # ---- business hours / exceptions ----
    'business_hours_length': {
        'de': 'Es müssen genau 7 Einträge übergeben werden, einer je Wochentag (Montag bis Sonntag)',
        'en': 'Exactly 7 entries must be provided, one per weekday (Monday through Sunday)',
    },
    'business_hours_entry_invalid': {
        'de': 'Jeder Eintrag muss ein Objekt mit Wochentag, Öffnungs- und Schließzeit sein',
        'en': 'Each entry must be an object with a weekday, opening time and closing time',
    },
    'business_hours_weekday_duplicate': {
        'de': 'Jeder Wochentag darf nur einmal vorkommen',
        'en': 'Each weekday may only appear once',
    },
    'business_hours_exception_date_taken': {
        'de': 'Für dieses Datum besteht bereits eine Ausnahme',
        'en': 'An exception already exists for this date',
    },
    'business_hours_exception_not_found': {
        'de': 'Keine Ausnahme für dieses Datum gefunden',
        'en': 'No exception found for this date',
    },
    'business_hours_exception_deleted': {
        'de': 'Ausnahme gelöscht',
        'en': 'Exception deleted',
    },
    'business_hours_closed_with_band': {
        'de': 'Am {weekday} ist das Bedarfsband {start}–{end} gespeichert; '
              'der Tag kann nicht auf geschlossen gesetzt werden. Bitte zuerst das Band entfernen.',
        'en': 'The coverage band {start}–{end} is saved for {weekday}; '
              'that day cannot be set to closed. Please remove the band first.',
    },
    'business_hours_conflicts_band': {
        'de': 'Die neue Öffnungszeit ({open}–{close}) am {weekday} passt nicht zum '
              'gespeicherten Bedarfsband {start}–{end}. Bitte zuerst das Band anpassen.',
        'en': 'The new opening hours ({open}–{close}) on {weekday} do not fit the '
              'saved coverage band {start}–{end}. Please adjust the band first.',
    },

    # ---- coverage requirement bands ----
    'coverage_requirement_entry_invalid': {
        'de': 'Jeder Eintrag muss ein Objekt mit Wochentag, Start-, Endzeit und Bedarf sein',
        'en': 'Each entry must be an object with a weekday, start time, end time and required headcount',
    },
    'required_count_label': {
        'de': 'Der Bedarf',
        'en': 'The required headcount',
    },
    'coverage_requirement_overlap': {
        'de': 'Bänder überschneiden sich am {weekday}: {start1}–{end1} und {start2}–{end2}',
        'en': 'Bands overlap on {weekday}: {start1}–{end1} and {start2}–{end2}',
    },
    'coverage_requirement_closed_day': {
        'de': 'Am {weekday} ist geschlossen, dort ist kein Bedarfsband erlaubt ({start}–{end})',
        'en': 'The business is closed on {weekday}; no coverage band is allowed there ({start}–{end})',
    },
    'coverage_requirement_outside_hours': {
        'de': 'Band {start}–{end} am {weekday} liegt außerhalb der Öffnungszeit ({open}–{close})',
        'en': 'Band {start}–{end} on {weekday} lies outside the opening hours ({open}–{close})',
    },

    # ---- misc ----
    'api_root': {
        'de': 'Schichtplan-Tool API',
        'en': 'Schichtplan-Tool API',
    },

    # ---- error handling ----
    'server_error': {
        'de': 'Unerwarteter Serverfehler. Bitte erneut versuchen.',
        'en': 'Unexpected server error. Please try again.',
    },
    'not_found': {
        'de': 'Diese Adresse gibt es nicht',
        'en': 'This address does not exist',
    },
    'method_not_allowed': {
        'de': 'Diese Methode ist hier nicht erlaubt',
        'en': 'This method is not allowed here',
    },
}


def resolve_lang(value):
    """A supported language code for `value`, defaulting when it isn't one."""
    return value if value in SUPPORTED_LANGS else DEFAULT_LANG


def t(lang, key, **kwargs):
    """`key`'s text in `lang`, falling back to German then the key itself.

    Any keyword arguments fill the template's `{placeholder}` slots via
    str.format - including its own format specs (e.g. `{hours:.1f}`), since
    those live in the template and are applied at lookup time regardless of
    what type the caller passes in.
    """
    entry = TRANSLATIONS.get(key)
    if not entry:
        return key
    template = entry.get(lang) or entry.get(DEFAULT_LANG) or key
    return template.format(**kwargs) if kwargs else template
