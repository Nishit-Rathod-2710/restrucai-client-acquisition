from apify_client import ApifyClient
import os
import traceback

def run_scraper(query, location, max_results=50):
    """
    Runs the Apify Google Maps Scraper Actor.
    Returns a list of normalized lead dictionaries.
    """
    api_token = os.getenv('APIFY_API_TOKEN')
    if not api_token or api_token == 'your_apify_token_here':
        raise Exception("APIFY_API_TOKEN is not set or invalid in .env file")

    client = ApifyClient(api_token)

    # Use only well-documented, non-deprecated input fields.
    # Null values for optional fields are omitted to avoid schema validation errors.
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
        "scrapeContacts": True,   # enables email scraping from business websites
    }

    print(f"[Apify] Starting scraper — query='{query}' | location='{location}' | max={max_results}")

    try:
        # Use the stable actor slug (compass~crawler-google-places) instead of the legacy numeric ID
        run = client.actor("compass~crawler-google-places").call(run_input=run_input)
    except Exception as e:
        print(f"[Apify] Actor run FAILED: {e}")
        traceback.print_exc()
        raise

    print(f"[Apify] Run complete. Dataset: {run.get('defaultDatasetId')} | Status: {run.get('status')}")

    results = []
    try:
        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            # Extract email from contactInfo array or top-level field
            email = item.get('email', '')
            if not email:
                contact_info = item.get('contactInfo', [])
                if isinstance(contact_info, list):
                    for contact in contact_info:
                        if isinstance(contact, dict) and contact.get('email'):
                            email = contact['email']
                            break
            # Also check emails list
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
        print(f"[Apify] Failed to iterate dataset items: {e}")
        traceback.print_exc()
        raise

    print(f"[Apify] Fetched {len(results)} results.")
    return results
