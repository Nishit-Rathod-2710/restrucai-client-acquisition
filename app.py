import os
import re
import threading
import traceback
import requests
from urllib.parse import quote
from flask import Flask, render_template, request, jsonify, Response, session, redirect, url_for
from flask_bcrypt import Bcrypt
from dotenv import load_dotenv
from functools import wraps

import db
from query_builder import parse_requirement
from apify_service import (
    run_scraper, start_scraper, fetch_dataset,
    build_run_input, run_attrs, normalize_item, ACTOR_ID,
)
from email_enricher import enrich_campaign

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'supersecret_dev')
bcrypt = Bcrypt(app)

db.init_db()

enrichment_jobs = {}

CALL_STATUSES = [
    'Need to Call',
    'Called NIL',
    'Not Answered',
    'Interested',
    'Follow-Up',
]
# Canonical list exposed to frontend



def csv_download_headers(filename):
    """
    Builds a Content-Disposition header that forces the browser to save the CSV
    under the exact filename. Sanitizes to a safe ASCII name (quoted) and also
    emits an RFC 5987 filename* so unicode/special chars survive too.
    """
    safe = re.sub(r'[^A-Za-z0-9._-]+', '_', filename).strip('_') or 'export'
    if not safe.lower().endswith('.csv'):
        safe += '.csv'
    return {
        'Content-Disposition': (
            f'attachment; filename="{safe}"; '
            f"filename*=UTF-8''{quote(safe)}"
        )
    }


def send_telegram_message(text):
    """
    Sends an HTML-formatted message to the configured Telegram chat.
    Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in the environment.
    Returns (ok: bool, error: str|None).
    """
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        return False, 'Telegram is not configured (set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID).'
    try:
        resp = requests.post(
            f'https://api.telegram.org/bot{token}/sendMessage',
            json={
                'chat_id': chat_id,
                'text': text,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True,
            },
            timeout=10,
        )
        data = resp.json()
        if resp.ok and data.get('ok'):
            return True, None
        return False, data.get('description', f'Telegram API error (HTTP {resp.status_code})')
    except Exception as e:
        return False, f'Failed to reach Telegram: {e}'


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'Unauthorized'}), 401
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'Unauthorized'}), 401
            return redirect(url_for('login_page'))
        if not session.get('is_admin'):
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'Forbidden'}), 403
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated


# --- Auth pages ---

@app.route('/login')
def login_page():
    if 'user_id' in session:
        return redirect(url_for('index'))
    return render_template('login.html')


@app.route('/api/auth/signup', methods=['POST'])
def signup():
    data = request.json
    username = (data.get('username') or '').strip()
    email    = (data.get('email')    or '').strip()
    password = (data.get('password') or '').strip()

    if not username or not email or not password:
        return jsonify({'error': 'Username, email and password are required'}), 400
    if '@' not in email or '.' not in email:
        return jsonify({'error': 'Enter a valid email address'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400

    existing = db.get_user_by_username(username)
    if existing:
        return jsonify({'error': 'Username already taken'}), 409

    pw_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    user = db.create_user(username, email, pw_hash)
    session['user_id'] = user['id']
    session['username'] = user['username']
    session['is_admin'] = False
    return jsonify({'success': True, 'username': user['username'], 'is_admin': False, 'redirect': '/'}), 201


@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()

    if not username or not password:
        return jsonify({'error': 'Username and password are required'}), 400

    user = db.get_user_by_username(username)
    if not user or not bcrypt.check_password_hash(user['password_hash'], password):
        return jsonify({'error': 'Invalid username or password'}), 401

    session['user_id'] = user['id']
    session['username'] = user['username']
    session['is_admin'] = bool(user.get('is_admin'))
    is_admin = bool(user.get('is_admin'))
    return jsonify({'success': True, 'username': user['username'], 'is_admin': is_admin,
                    'redirect': '/admin' if is_admin else '/'})


@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})


@app.route('/api/auth/me', methods=['GET'])
def me():
    if 'user_id' not in session:
        return jsonify({'logged_in': False})
    return jsonify({'logged_in': True, 'username': session.get('username'), 'is_admin': session.get('is_admin', False)})


@app.route('/api/config', methods=['GET'])
def config():
    return jsonify({
        'call_statuses': CALL_STATUSES,
        'supabase_url': os.getenv('SUPABASE_URL'),
        'supabase_key': os.getenv('SUPABASE_KEY'),
    })


# --- App ---

@app.route('/')
@login_required
def index():
    if session.get('is_admin'):
        return redirect(url_for('admin_panel'))
    return render_template('index.html', username=session.get('username'))


# --- Admin Panel ---

@app.route('/admin')
@admin_required
def admin_panel():
    return render_template('admin.html', admin_username=session.get('username'))


@app.route('/api/admin/stats', methods=['GET'])
@admin_required
def admin_stats():
    return jsonify(db.get_global_stats())


@app.route('/api/admin/users', methods=['GET'])
@admin_required
def admin_users():
    users = db.get_all_users()
    return jsonify({'users': users})


@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@admin_required
def admin_delete_user(user_id):
    target = db.get_user_by_id(user_id)
    if not target:
        return jsonify({'error': 'User not found'}), 404
    if target.get('is_admin'):
        return jsonify({'error': 'Cannot delete admin'}), 403
    db.delete_user(user_id)
    return jsonify({'success': True})


@app.route('/api/admin/apify/global', methods=['POST'])
@admin_required
def admin_apify_global():
    enabled = request.json.get('enabled')
    if enabled is None:
        return jsonify({'error': 'enabled field required'}), 400
    db.set_apify_enabled_global(bool(enabled))
    return jsonify({'success': True, 'enabled': bool(enabled)})


@app.route('/api/admin/apify/user/<int:user_id>', methods=['POST'])
@admin_required
def admin_apify_user(user_id):
    target = db.get_user_by_id(user_id)
    if not target:
        return jsonify({'error': 'User not found'}), 404
    if target.get('is_admin'):
        return jsonify({'error': 'Cannot modify admin'}), 403
    enabled = request.json.get('enabled')
    if enabled is None:
        return jsonify({'error': 'enabled field required'}), 400
    db.set_apify_enabled_user(user_id, bool(enabled))
    return jsonify({'success': True, 'enabled': bool(enabled)})


@app.route('/api/admin/campaigns', methods=['GET'])
@admin_required
def admin_campaigns():
    campaigns = db.get_all_campaigns_with_user()
    return jsonify({'campaigns': campaigns})


@app.route('/api/admin/users/<int:user_id>/campaigns', methods=['GET'])
@admin_required
def admin_user_campaigns(user_id):
    target = db.get_user_by_id(user_id)
    if not target:
        return jsonify({'error': 'User not found'}), 404
    campaigns = db.get_campaigns_by_user(user_id)
    return jsonify({'campaigns': campaigns, 'user': {'id': target['id'], 'username': target['username']}})


@app.route('/api/admin/campaigns/<int:campaign_id>/export', methods=['GET'])
@admin_required
def admin_export_campaign(campaign_id):
    campaign = db.get_campaign(campaign_id)
    if not campaign:
        return jsonify({'error': 'Not found'}), 404
    leads = db.get_leads(campaign_id)

    def generate():
        yield "Name,Address,Phone,Email,Website,Category,Rating,Reviews,Google URL,Status,Notes\n"
        for lead in leads:
            row = [
                str(lead.get('name', '')).replace(',', ' '),
                str(lead.get('address', '')).replace(',', ' '),
                str(lead.get('phone', '')).replace(',', ' '),
                str(lead.get('email', '')).replace(',', ' '),
                str(lead.get('website', '')).replace(',', ' '),
                str(lead.get('category', '')).replace(',', ' '),
                str(lead.get('rating', '')),
                str(lead.get('reviews', '')),
                str(lead.get('google_url', '')).replace(',', '%2C'),
                str(lead.get('call_status', 'Need to Call')).replace(',', ' '),
                str(lead.get('notes', '')).replace(',', ' ').replace('\r', ' ').replace('\n', ' | '),
            ]
            yield ','.join(row) + '\n'

    filename = f"admin_leads_{campaign_id}_{campaign.get('name','export')}.csv"
    return Response(generate(), mimetype='text/csv',
                    headers=csv_download_headers(filename))


@app.route('/api/admin/export/all-users', methods=['GET'])
@admin_required
def admin_export_users():
    users = db.get_all_users()

    def generate():
        yield "ID,Username,Email,Admin,Apify Enabled,Created At\n"
        for u in users:
            row = [
                str(u.get('id', '')),
                str(u.get('username', '')).replace(',', ' '),
                str(u.get('email', '')).replace(',', ' '),
                'Yes' if u.get('is_admin') else 'No',
                'Yes' if u.get('apify_enabled', True) else 'No',
                str(u.get('created_at', '')),
            ]
            yield ','.join(row) + '\n'

    return Response(generate(), mimetype='text/csv',
                    headers=csv_download_headers('admin_users_export.csv'))


# --- Campaigns ---

@app.route('/api/campaigns', methods=['GET'])
@login_required
def get_campaigns():
    campaigns = db.get_campaigns(user_id=session['user_id'])
    return jsonify({'campaigns': campaigns})


@app.route('/api/campaigns', methods=['POST'])
@login_required
def create_campaign():
    data = request.json
    requirement = data.get('requirement', '')

    if not requirement:
        return jsonify({'error': 'Requirement text is required'}), 400

    user = db.get_user_by_id(session['user_id'])
    if user and user.get('apify_enabled') is False:
        return jsonify({'error': 'Apify access is disabled for your account. Contact the admin.'}), 403

    parsed = parse_requirement(requirement)
    campaign_name = f"{parsed['search_query'].capitalize()} in {parsed['location'].capitalize()}" if parsed['location'] else parsed['search_query'].capitalize()

    campaign_id = db.create_campaign(
        name=campaign_name,
        query=parsed['search_query'],
        location=parsed['location'],
        max_results=parsed['max_results'],
        user_id=session['user_id']
    )

    # On Vercel: use async webhook so the function returns before Apify finishes.
    # Locally: use a background thread (blocking .call()) as before.
    app_url = os.getenv('APP_URL', '').rstrip('/')
    if app_url:
        # Production path — fire-and-forget via Apify webhook
        webhook_url = f"{app_url}/api/webhook/apify/{campaign_id}"
        try:
            run_id, dataset_id = start_scraper(
                parsed['search_query'], parsed['location'], parsed['max_results'], webhook_url
            )
            print(f"[Campaign {campaign_id}] Apify run started: {run_id}")
        except Exception:
            print(f"[Error] Campaign {campaign_id} failed to start:\n{traceback.format_exc()}")
            db.update_campaign_status(campaign_id, 'failed')
    else:
        # Local dev path — background thread with progressive dataset polling
        def scrape_job(cid, q, loc, mx):
            import time
            from apify_client import ApifyClient
            try:
                api_token = os.getenv('APIFY_API_TOKEN')
                if not api_token or api_token == 'your_apify_token_here':
                    raise Exception("APIFY_API_TOKEN is not set or invalid in .env file")

                client = ApifyClient(api_token)
                run_input = build_run_input(q, loc, mx)

                print(f"[Scraper Thread] Starting actor {ACTOR_ID} dynamically for campaign {cid}...")
                run = client.actor(ACTOR_ID).start(run_input=run_input)
                run_id, dataset_id, _ = run_attrs(run)
                print(f"[Scraper Thread] Run started: {run_id} | Dataset: {dataset_id}")

                processed_count = 0
                while True:
                    # Check the run status (handling dict vs Pydantic model)
                    _, _, status = run_attrs(client.run(run_id).get())

                    # Fetch new items starting from processed_count offset
                    items = list(client.dataset(dataset_id).iterate_items(offset=processed_count))

                    if items:
                        print(f"[Scraper Thread] Found {len(items)} new items from offset {processed_count}.")
                        for item in items:
                            db.insert_lead(cid, normalize_item(item))

                        processed_count += len(items)

                    # Break if run is finished
                    if status in ["SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"]:
                        if status == "SUCCEEDED":
                            db.update_campaign_status(cid, 'completed')
                            print(f"[Scraper Thread] Campaign {cid} completed successfully.")
                        else:
                            db.update_campaign_status(cid, 'failed')
                            print(f"[Scraper Thread] Campaign {cid} finished with status: {status}")
                        break

                    time.sleep(5)
            except Exception:
                print(f"[Error] Campaign {cid} failed:\n{traceback.format_exc()}")
                db.update_campaign_status(cid, 'failed')

        t = threading.Thread(target=scrape_job, args=(campaign_id, parsed['search_query'], parsed['location'], parsed['max_results']))
        t.daemon = True
        t.start()

    return jsonify({'success': True, 'campaign_id': campaign_id, 'parsed_query': parsed}), 201


@app.route('/api/campaigns/<int:campaign_id>', methods=['DELETE'])
@login_required
def delete_campaign(campaign_id):
    db.delete_campaign(campaign_id)
    return jsonify({'success': True})


@app.route('/api/campaigns/<int:campaign_id>/status', methods=['GET'])
@login_required
def get_campaign_status(campaign_id):
    campaign = db.get_campaign(campaign_id)
    if not campaign:
        return jsonify({'error': 'Not found'}), 404
    leads = db.get_leads(campaign_id)
    return jsonify({'status': campaign['status'], 'leads_count': len(leads)})


@app.route('/api/campaigns/<int:campaign_id>/leads', methods=['GET'])
@login_required
def get_campaign_leads(campaign_id):
    campaign = db.get_campaign(campaign_id)
    if not campaign:
        return jsonify({'error': 'Not found'}), 404
    leads = db.get_leads(campaign_id)
    return jsonify({'campaign': campaign, 'leads': leads})


# --- Leads ---

@app.route('/api/leads/<int:lead_id>', methods=['GET'])
@login_required
def get_lead(lead_id):
    lead = db.get_lead(lead_id)
    if not lead:
        return jsonify({'error': 'Not found'}), 404
    return jsonify({'lead': lead})


@app.route('/api/leads/<int:lead_id>/email', methods=['PATCH'])
@login_required
def update_lead_email(lead_id):
    lead = db.get_lead(lead_id)
    if not lead:
        return jsonify({'error': 'Not found'}), 404
    email = request.json.get('email', '').strip()
    db.update_lead_email(lead_id, email)
    return jsonify({'success': True, 'email': email})


@app.route('/api/leads/<int:lead_id>/status', methods=['PATCH'])
@login_required
def update_lead_status(lead_id):
    lead = db.get_lead(lead_id)
    if not lead:
        return jsonify({'error': 'Not found'}), 404
    call_status = request.json.get('call_status', '').strip()
    if call_status not in CALL_STATUSES:
        return jsonify({'error': 'Invalid status'}), 400
    db.update_lead_status(lead_id, call_status)
    return jsonify({'success': True, 'call_status': call_status})


@app.route('/api/leads/<int:lead_id>/notes', methods=['PATCH'])
@login_required
def update_lead_notes(lead_id):
    lead = db.get_lead(lead_id)
    if not lead:
        return jsonify({'error': 'Not found'}), 404
    notes = request.json.get('notes', '').strip()
    db.update_lead_notes(lead_id, notes)
    return jsonify({'success': True, 'notes': notes})


@app.route('/api/note-questions', methods=['GET'])
@login_required
def get_note_questions():
    try:
        questions = db.get_note_questions(session['user_id'])
    except Exception:
        # Table missing or DB error — fall back to defaults so the UI isn't empty.
        print(f"[note-questions] falling back to defaults:\n{traceback.format_exc()}")
        questions = [{'id': f'd{i}', 'text': t} for i, t in enumerate(db.DEFAULT_NOTE_QUESTIONS)]
    return jsonify({'questions': questions})


@app.route('/api/note-questions', methods=['PUT'])
@login_required
def update_note_questions():
    texts = (request.json or {}).get('questions', [])
    if not isinstance(texts, list):
        return jsonify({'error': 'questions must be a list of strings'}), 400
    texts = [str(t).strip() for t in texts if str(t).strip()]
    if not texts:
        return jsonify({'error': 'At least one question is required.'}), 400
    questions = db.replace_note_questions(session['user_id'], texts)
    return jsonify({'success': True, 'questions': questions})


@app.route('/api/leads/<int:lead_id>/inform-team', methods=['POST'])
@login_required
def inform_team(lead_id):
    lead = db.get_lead(lead_id)
    if not lead:
        return jsonify({'error': 'Not found'}), 404

    body = request.json or {}
    items = body.get('items', [])   # [{question, answer}, ...]
    free = (body.get('free') or '').strip()
    if not isinstance(items, list) or not items:
        return jsonify({'error': 'No questions to send.'}), 400
    if any(not (it.get('answer') or '').strip() for it in items):
        return jsonify({'error': 'All questions must be answered before informing the team.'}), 400

    def esc(s):
        # Escape the few characters Telegram's HTML parse_mode treats specially.
        return str(s or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    lines = [
        '🔔 <b>New Lead Briefing</b>',
        '',
        f"<b>{esc(lead.get('name') or 'Unknown business')}</b>",
    ]
    if lead.get('phone'):
        lines.append(f"📞 {esc(lead['phone'])}")
    if lead.get('website'):
        lines.append(f"🌐 {esc(lead['website'])}")
    lines.append(f"📍 Status: {esc(lead.get('call_status') or 'Need to Call')}")
    lines.append('')
    for i, it in enumerate(items, 1):
        lines.append(f"<b>{i}. {esc(it.get('question'))}</b>")
        lines.append(esc(it.get('answer')))
        lines.append('')
    if free:
        lines += ['<b>Additional notes</b>', esc(free), '']

    sent_by = session.get('username') or session.get('user_id')
    if sent_by:
        lines.append(f"<i>Sent by {esc(sent_by)}</i>")

    ok, err = send_telegram_message('\n'.join(lines).strip())
    if not ok:
        return jsonify({'error': err}), 502
    return jsonify({'success': True, 'message': 'Team notified on Telegram.'})


# --- Enrichment ---

@app.route('/api/campaigns/<int:campaign_id>/enrich', methods=['POST'])
@login_required
def start_enrichment(campaign_id):
    campaign = db.get_campaign(campaign_id)
    if not campaign:
        return jsonify({'error': 'Not found'}), 404

    if enrichment_jobs.get(campaign_id, {}).get('status') == 'running':
        return jsonify({'error': 'Enrichment already running'}), 409

    leads = db.get_leads(campaign_id)
    eligible = [l for l in leads if l.get('website') and not l.get('email')]

    if not eligible:
        return jsonify({'message': 'No leads need enrichment (all already have emails or no website)', 'total': 0})

    def run_enrichment():
        enrich_campaign(
            campaign_id=campaign_id,
            leads=leads,
            update_email_fn=db.update_lead_email,
            progress_store=enrichment_jobs,
            delay=0.5
        )

    t = threading.Thread(target=run_enrichment)
    t.daemon = True
    t.start()

    return jsonify({'success': True, 'total': len(eligible)}), 202


@app.route('/api/campaigns/<int:campaign_id>/enrich/status', methods=['GET'])
@login_required
def enrichment_status(campaign_id):
    job = enrichment_jobs.get(campaign_id)
    if not job:
        return jsonify({'status': 'idle', 'processed': 0, 'found': 0, 'total': 0})
    return jsonify(job)


# --- Export ---

@app.route('/api/campaigns/<int:campaign_id>/export', methods=['GET'])
@login_required
def export_campaign(campaign_id):
    campaign = db.get_campaign(campaign_id)
    if not campaign:
        return jsonify({'error': 'Not found'}), 404

    leads = db.get_leads(campaign_id)

    def generate():
        yield "Name,Address,Phone,Email,Website,Category,Rating,Reviews,Google URL,Status,Notes\n"
        for lead in leads:
            row = [
                str(lead.get('name', '')).replace(',', ' '),
                str(lead.get('address', '')).replace(',', ' '),
                str(lead.get('phone', '')).replace(',', ' '),
                str(lead.get('email', '')).replace(',', ' '),
                str(lead.get('website', '')).replace(',', ' '),
                str(lead.get('category', '')).replace(',', ' '),
                str(lead.get('rating', '')),
                str(lead.get('reviews', '')),
                str(lead.get('google_url', '')).replace(',', '%2C'),
                str(lead.get('call_status', 'Need to Call')).replace(',', ' '),
                str(lead.get('notes', '')).replace(',', ' ').replace('\r', ' ').replace('\n', ' | '),
            ]
            yield ','.join(row) + '\n'

    filename = f"leads_{campaign_id}_{campaign.get('name', 'export')}.csv"
    return Response(
        generate(),
        mimetype='text/csv',
        headers=csv_download_headers(filename)
    )


# --- Apify Webhook ---

@app.route('/api/webhook/apify/<int:campaign_id>', methods=['POST'])
def apify_webhook(campaign_id):
    """
    Called by Apify when a scrape run finishes.
    Payload contains eventType and resource (run object with defaultDatasetId).
    """
    payload = request.json or {}
    event_type = payload.get('eventType', '')
    resource = payload.get('resource', {})
    dataset_id = resource.get('defaultDatasetId')

    print(f"[Webhook] Campaign {campaign_id} | event={event_type} | dataset={dataset_id}")

    if event_type != 'ACTOR.RUN.SUCCEEDED' or not dataset_id:
        db.update_campaign_status(campaign_id, 'failed')
        return jsonify({'ok': False, 'reason': event_type}), 200

    try:
        results = fetch_dataset(dataset_id)
        for lead in results:
            db.insert_lead(campaign_id, lead)
        db.update_campaign_status(campaign_id, 'completed')
        print(f"[Webhook] Campaign {campaign_id} completed — {len(results)} leads inserted.")
    except Exception:
        print(f"[Webhook] Campaign {campaign_id} failed:\n{traceback.format_exc()}")
        db.update_campaign_status(campaign_id, 'failed')

    return jsonify({'ok': True}), 200


if __name__ == '__main__':
    app.run(debug=True, port=5000)
