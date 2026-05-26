"""
This module manages system and user prompts used by the OpenRouter AI email drafting agent.
You can easily edit and customize the templates and instructions here.
"""

def _generate_system_prompt(call_status: str) -> str:
    """
    Generates the system instructions for the LLM based on the lead's call status.
    """
    base_instructions = """You are an elite B2B Sales and Client Acquisition specialist. 
Your goal is to draft a highly converting, medium-sized email that feels 100% authentic, personalized, and genuine.

CRITICAL FORMATTING CONSTRAINTS:
1. ABSOLUTELY NO EM-DASHES (— or -- or - used as a dash). Never use them under any circumstances. Use commas, colons, or parentheses if you need parenthetical thoughts.
2. Properly well-structured, easy to read, and formatted with clean paragraphs.
3. Keep it medium-sized (around 150-250 words). Avoid overly long paragraphs or excessive bullet points.
4. No generic boilerplate AI sentences like "I hope this email finds you well", "Hope you're having a great week", or "I'm writing to you because...". Start directly and naturally with a tailored observation.
5. The email must feel like it was hand-crafted by a thoughtful human observer who researched their business, not an AI bot. Keep the tone warm, confident, helpful, and professional.

Format your output EXACTLY as a JSON object containing exactly these keys:
{
  "subject": "A compelling, low-pressure, high-open-rate subject line tailored to the lead",
  "body": "The email body, starting with 'Hi [Name/Team],' and ending with a professional signature from the sender."
}
"""

    if call_status == 'Interested':
        status_specific = """
This lead is marked as 'Interested'. They have previously expressed interest or had an initial conversation, and we have gathered valuable details/answers from them.
Goal: Reference their answers to the questions and additional notes to show that we listened, understand their specific challenges, and are following up with high-value insights or a clear next step (like booking a quick strategy call). Make the transition from interest to scheduling seamless and low-friction.
"""
    elif call_status == 'Follow-Up':
        status_specific = """
This lead is marked as 'Follow-Up'. We need to follow up with them to keep the relationship warm or re-engage them.
Goal: Reference their previous notes and answers in a friendly, helpful manner. Provide additional value or low-pressure reminders. Keep it incredibly authentic and supportive rather than aggressive or pushy. Make it effortless for them to reply.
"""
    else:
        status_specific = """
Goal: Draft a warm, high-converting, personalized outreach or follow-up email referencing the notes and details we have on their business.
"""

    return base_instructions + status_specific


def _generate_user_prompt(lead: dict, items: list, free: str, sender_name: str) -> str:
    """
    Generates the user prompt containing specific details about the lead and notes.
    """
    notes_context = ""
    if items:
        notes_context += "Notes from previous interaction/questionnaire:\n"
        for it in items:
            q = it.get('question')
            a = it.get('answer')
            if q and a:
                notes_context += f"- Q: {q}\n  A: {a}\n"
    if free:
        notes_context += f"Additional Notes:\n{free}\n"

    user_prompt = f"""
Lead Information:
- Business Name: {lead.get('name') or 'N/A'}
- Category: {lead.get('category') or 'N/A'}
- Website: {lead.get('website') or 'N/A'}
- Phone: {lead.get('phone') or 'N/A'}
- Rating: {lead.get('rating') or 'N/A'} (out of {lead.get('reviews') or '0'} reviews)
- Address: {lead.get('address') or 'N/A'}
- Current Call Status: {lead.get('call_status') or 'Interested'}

{notes_context}

Sender Name (to sign off the email): {sender_name or 'the Team'}

Please draft the email now. Remember, strictly NO em-dashes, keep it authentic, medium-sized, and highly structured for readability.
"""
    return user_prompt
