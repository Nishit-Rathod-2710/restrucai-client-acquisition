from apify_client import ApifyClient
import os
import traceback

def start_scraper(query, location, max_results, webhook_url):
    """
    Starts the Apify actor run asynchronously with a webhook.
    Returns the run ID immediately — does NOT wait for completion.
    Apify will POST to webhook_url when the run finishes.
    """
    api_token = os.getenv('APIFY_API_TOKEN')
    if not api_token or api_token == 'your_apify_token_here':
        raise Exception("APIFY_API_TOKEN is not set or invalid in .env file")

    client = ApifyClient(api_token)

    run_input = {
        "searchStringsArray": [query],
        "locationQuery": location if location else None,
        "maxCrawledPlacesPerSearch": max_results,
        "language": "en",
        "searchMatching": "all",
        "placeMinimumStars": "",
        "website": "allPlaces",
        "skipClosedPlaces": False,
        "scrapePlaceDetailPage": False,
        "maxReviews": 0,
        "reviewsSort": "newest",
        "reviewsOrigin": "all",
        "maxImages": 0,
        "maxQuestions": 0,
        "scrapeContacts": True,
    }

    print(f"[Apify] Starting async run — query='{query}' | location='{location}' | max={max_results}")
    print(f"[Apify] Webhook URL: {webhook_url}")

    try:
        run = client.actor("compass~crawler-google-places").start(
            run_input=run_input,
            webhooks=[{
                "eventTypes": ["ACTOR.RUN.SUCCEEDED", "ACTOR.RUN.FAILED", "ACTOR.RUN.ABORTED"],
                "requestUrl": webhook_url,
            }]
        )
        run_id = run.get("id")
        dataset_id = run.get("defaultDatasetId")
        print(f"[Apify] Run started — runId={run_id} | datasetId={dataset_id}")
        return run_id, dataset_id
    except Exception as e:
        print(f"[Apify] Failed to start actor: {e}")
        traceback.print_exc()
        raise


def fetch_dataset(dataset_id):
    """
    Fetches and normalises all items from a completed Apify dataset.
    Called from the webhook handler after Apify signals success.
    """
    api_token = os.getenv('APIFY_API_TOKEN')
    client = ApifyClient(api_token)

    results = []
    try:
        for item in client.dataset(dataset_id).iterate_items():
            email = item.get('email', '')
            if not email:
                contact_info = item.get('contactInfo', [])
                if isinstance(contact_info, list):
                    for contact in contact_info:
                        if isinstance(contact, dict) and contact.get('email'):
                            email = contact['email']
                            break
            if not email:
                emails = item.get('emails', [])
                if isinstance(emails, list) and emails:
                    email = emails[0] if isinstance(emails[0], str) else emails[0].get('value', '')

            lead = {
                "name": item.get("title", ""),
                "address": item.get("address", ""),
                "phone": item.get("phoneUnformatted", "") or item.get("phone", ""),
                "email": email or "",
                "website": item.get("website", ""),
                "rating": item.get("totalScore") or 0.0,
                "reviews": item.get("reviewsCount") or 0,
                "category": item.get("categoryName") or (
                    item.get("categories", [None])[0] if item.get("categories") else ""
                ),
                "latitude": (item.get("location") or {}).get("lat", 0.0),
                "longitude": (item.get("location") or {}).get("lng", 0.0),
                "google_url": item.get("url", ""),
                "raw_json": item
            }
            results.append(lead)
    except Exception as e:
        print(f"[Apify] Failed to fetch dataset {dataset_id}: {e}")
        traceback.print_exc()
        raise

    print(f"[Apify] Fetched {len(results)} results from dataset {dataset_id}.")
    return results


def run_scraper(query, location, max_results=50):
    """
    Synchronous fallback — used locally where background threads work fine.
    Kept for local development / testing.
    """
    api_token = os.getenv('APIFY_API_TOKEN')
    if not api_token or api_token == 'your_apify_token_here':
        raise Exception("APIFY_API_TOKEN is not set or invalid in .env file")

    client = ApifyClient(api_token)

    run_input = {
        "searchStringsArray": [query],
        "locationQuery": location if location else None,
        "maxCrawledPlacesPerSearch": max_results,
        "language": "en",
        "searchMatching": "all",
        "placeMinimumStars": "",
        "website": "allPlaces",
        "skipClosedPlaces": False,
        "scrapePlaceDetailPage": False,
        "maxReviews": 0,
        "reviewsSort": "newest",
        "reviewsOrigin": "all",
        "maxImages": 0,
        "maxQuestions": 0,
        "scrapeContacts": True,
    }

    print(f"[Apify] Starting scraper — query='{query}' | location='{location}' | max={max_results}")

    try:
        run = client.actor("compass~crawler-google-places").call(run_input=run_input)
    except Exception as e:
        print(f"[Apify] Actor run FAILED: {e}")
        traceback.print_exc()
        raise

    print(f"[Apify] Run complete. Dataset: {run.get('defaultDatasetId')} | Status: {run.get('status')}")
    return fetch_dataset(run["defaultDatasetId"])
