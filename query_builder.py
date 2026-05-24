import re
import os

def _call_llm(prompt: str) -> str | None:
    """
    Try OpenRouter first (OPENROUTER_API_KEY), then direct OpenAI (OPENAI_API_KEY).
    Both use the openai SDK — only base_url and key differ.
    Returns the raw JSON string from the model or None on failure.
    """
    from openai import OpenAI

    # --- Option 1: OpenRouter ---
    openrouter_key = os.getenv('OPENROUTER_API_KEY')
    if openrouter_key:
        try:
            client = OpenAI(
                api_key=openrouter_key,
                base_url="https://openrouter.ai/api/v1",
            )
            response = client.chat.completions.create(
                model="openai/gpt-4.1-mini",   # OpenRouter model ID
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that parses search requirements into JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"[OpenRouter] Failed: {e}. Trying OpenAI fallback...")

    # --- Option 2: Direct OpenAI ---
    openai_key = os.getenv('OPENAI_API_KEY')
    if openai_key:
        try:
            client = OpenAI(api_key=openai_key)
            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that parses search requirements into JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"[OpenAI] Failed: {e}. Falling back to heuristics...")

    return None


def parse_requirement(text):
    """
    Takes a plain English requirement and extracts the search query, location, and max results.
    Uses OpenRouter → OpenAI → regex heuristics in that priority order.
    """
    prompt = f"""
Extract the following information from the user's plain English request for finding Google Maps leads:
- search_query: What type of business are they looking for? (e.g. 'restaurant', 'dentist', 'plumber')
- location: Where are they looking? (e.g. 'New York, USA', 'London')
- max_results: How many results do they want? If not specified, default to 50. Provide just the integer.

User Request: "{text}"

Format the response exactly as a JSON object with keys: "search_query", "location", "max_results".
"""
    content = _call_llm(prompt)
    if content:
        try:
            import json
            result = json.loads(content)
            return {
                "search_query": result.get('search_query', 'business'),
                "location": result.get('location', ''),
                "max_results": int(result.get('max_results', 50))
            }
        except Exception as e:
            print(f"[query_builder] Failed to parse LLM JSON: {e}")
            pass
            
    # Fallback heuristics
    text = text.lower()
    
    # Try to extract numbers for max_results
    max_results = 50
    num_match = re.search(r'(\d+)\s+(leads|results|places|businesses|restaurants)', text)
    if num_match:
        max_results = int(num_match.group(1))
    elif 'top 10' in text: max_results = 10
    elif 'top 20' in text: max_results = 20
    elif 'top 100' in text: max_results = 100
    
    # Try to extract location (after 'in', 'around', 'near')
    location = ""
    loc_match = re.search(r'(in|around|near)\s+([a-zA-Z\s,]+)', text)
    if loc_match:
        # Get the words after 'in' until the end of sentence or another preposition
        raw_loc = loc_match.group(2).strip()
        location_parts = raw_loc.split(' for ')
        location = location_parts[0].strip()
    
    # Try to extract search query (everything before 'in' or general business words)
    search_query = text
    if loc_match:
        search_query = text[:loc_match.start()].strip()
        
    # Remove some stop words from search query
    stop_words = ['find', 'me', 'get', 'some', 'the', 'best', 'top', 'look', 'for', str(max_results), 'results', 'leads']
    query_words = search_query.split()
    query_words = [w for w in query_words if w not in stop_words]
    search_query = " ".join(query_words).strip()
    
    if not search_query:
        search_query = "businesses"

    return {
        "search_query": search_query,
        "location": location,
        "max_results": max_results
    }
