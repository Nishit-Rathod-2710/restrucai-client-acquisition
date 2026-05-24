import os
import json
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

_supabase: Client = create_client(
    os.environ['SUPABASE_URL'],
    os.environ['SUPABASE_KEY'],
)


def init_db():
    print('[db] Supabase client ready.')


# --- Auth ---

def get_user_by_username(username):
    res = _supabase.table('users').select('*').eq('username', username).limit(1).execute()
    return res.data[0] if res.data else None


def get_user_by_id(user_id):
    res = _supabase.table('users').select('*').eq('id', user_id).limit(1).execute()
    return res.data[0] if res.data else None


def create_user(username, email, password_hash):
    res = _supabase.table('users').insert({
        'username': username,
        'email': email,
        'password_hash': password_hash,
    }).execute()
    return res.data[0]


# --- Admin ---

def get_all_users():
    res = _supabase.table('users').select('id, username, email, is_admin, apify_enabled, created_at').order('created_at', desc=False).execute()
    return res.data


def delete_user(user_id):
    _supabase.table('users').delete().eq('id', user_id).execute()


def set_apify_enabled_global(enabled: bool):
    _supabase.table('users').update({'apify_enabled': enabled}).neq('is_admin', True).execute()


def set_apify_enabled_user(user_id, enabled: bool):
    _supabase.table('users').update({'apify_enabled': enabled}).eq('id', user_id).execute()


def get_all_campaigns_with_user():
    res = _supabase.table('campaigns').select(
        '*, leads(count), users(username)'
    ).order('created_at', desc=True).execute()
    rows = res.data
    for row in rows:
        count_list = row.pop('leads', [])
        row['lead_count'] = count_list[0]['count'] if count_list else 0
        user_obj = row.pop('users', None)
        row['username'] = user_obj['username'] if isinstance(user_obj, dict) else '—'
    return rows


def get_campaigns_by_user(user_id):
    res = _supabase.table('campaigns').select(
        '*, leads(count)'
    ).eq('user_id', user_id).order('created_at', desc=True).execute()
    rows = res.data
    for row in rows:
        count_list = row.pop('leads', [])
        row['lead_count'] = count_list[0]['count'] if count_list else 0
    return rows


def get_global_stats():
    users_res = _supabase.table('users').select('id, is_admin').execute()
    camps_res = _supabase.table('campaigns').select('id, status').execute()
    leads_res = _supabase.table('leads').select('id').execute()
    total_users = sum(1 for u in (users_res.data or []) if not u.get('is_admin'))
    total_campaigns = len(camps_res.data or [])
    total_leads = len(leads_res.data or [])
    running = sum(1 for c in (camps_res.data or []) if c.get('status') == 'running')
    return {
        'total_users': total_users,
        'total_campaigns': total_campaigns,
        'total_leads': total_leads,
        'running_campaigns': running,
    }


# --- Campaigns ---

def create_campaign(name, query, location, max_results, user_id=None):
    res = _supabase.table('campaigns').insert({
        'user_id': user_id,
        'name': name,
        'search_query': query,
        'location': location,
        'max_results': max_results,
        'status': 'running',
    }).execute()
    return res.data[0]['id']


def update_campaign_status(campaign_id, status):
    _supabase.table('campaigns').update({'status': status}).eq('id', campaign_id).execute()


def get_campaigns(user_id=None):
    q = _supabase.table('campaigns').select(
        '*, leads(count), lead_statuses:leads(call_status)'
    )
    if user_id is not None:
        q = q.eq('user_id', user_id)
    res = q.order('created_at', desc=True).execute()
    rows = res.data
    for row in rows:
        count_list = row.pop('leads', [])
        row['lead_count'] = count_list[0]['count'] if count_list else 0
        status_summary = {}
        for lead in row.pop('lead_statuses', []):
            s = lead.get('call_status') or 'Need to Call'
            status_summary[s] = status_summary.get(s, 0) + 1
        row['status_summary'] = status_summary
    return rows


def get_campaign(campaign_id):
    res = _supabase.table('campaigns').select('*').eq('id', campaign_id).limit(1).execute()
    return res.data[0] if res.data else None


def delete_campaign(campaign_id):
    _supabase.table('campaigns').delete().eq('id', campaign_id).execute()


# --- Leads ---

def insert_lead(campaign_id, lead_data):
    _supabase.table('leads').insert({
        'campaign_id': campaign_id,
        'name': lead_data.get('name'),
        'address': lead_data.get('address'),
        'phone': lead_data.get('phone'),
        'email': lead_data.get('email'),
        'website': lead_data.get('website'),
        'rating': lead_data.get('rating'),
        'reviews': lead_data.get('reviews'),
        'category': lead_data.get('category'),
        'latitude': lead_data.get('latitude'),
        'longitude': lead_data.get('longitude'),
        'google_url': lead_data.get('google_url'),
        'raw_json': json.dumps(lead_data.get('raw_json', {})),
        'call_status': 'Need to Call',
        'notes': '',
    }).execute()


def get_leads(campaign_id):
    res = _supabase.table('leads').select('*').eq('campaign_id', campaign_id).order('rating', desc=True).execute()
    return res.data


def get_lead(lead_id):
    res = _supabase.table('leads').select('*').eq('id', lead_id).limit(1).execute()
    lead = res.data[0] if res.data else None
    if lead and lead.get('raw_json'):
        lead['raw_json'] = json.loads(lead['raw_json'])
    return lead


def update_lead_email(lead_id, email):
    _supabase.table('leads').update({'email': email.strip()}).eq('id', lead_id).execute()


def update_lead_status(lead_id, call_status):
    _supabase.table('leads').update({'call_status': call_status}).eq('id', lead_id).execute()


def update_lead_notes(lead_id, notes):
    _supabase.table('leads').update({'notes': notes}).eq('id', lead_id).execute()


if __name__ == '__main__':
    init_db()
    print("Supabase connection verified.")
