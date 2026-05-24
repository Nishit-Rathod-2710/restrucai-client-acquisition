import os
import threading
import traceback
from flask import Flask, render_template, request, jsonify, Response, session, redirect, url_for
from flask_bcrypt import Bcrypt
from dotenv import load_dotenv
from functools import wraps

import db
from query_builder import parse_requirement
from apify_service import run_scraper
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
                str(lead.get('notes', '')).replace(',', ' '),
            ]
            yield ','.join(row) + '\n'

    filename = f"admin_leads_{campaign_id}_{campaign.get('name','export').replace(' ','_')}.csv"
    return Response(generate(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename={filename}'})


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
                    headers={'Content-Disposition': 'attachment; filename=admin_users_export.csv'})


# --- Campaigns ---

@app.route('/api/campaigns', methods=['GET'])
@login_required
def get_campaigns():
    campaigns = db.get_campaigns()
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
        max_results=parsed['max_results']
    )

    def scrape_job(cid, q, loc, mx):
        try:
            results = run_scraper(q, loc, mx)
            for lead in results:
                db.insert_lead(cid, lead)
            db.update_campaign_status(cid, 'completed')
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
                str(lead.get('notes', '')).replace(',', ' '),
            ]
            yield ','.join(row) + '\n'

    filename = f"leads_{campaign_id}_{campaign.get('name', 'export').replace(' ', '_')}.csv"
    return Response(
        generate(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


if __name__ == '__main__':
    app.run(debug=True, port=5000)
