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

SENDER CONTACT DETAILS (include naturally in the signature; you may also reference the website inline in the body when it adds credibility, e.g. linking a relevant case study or service page):
- Website: www.restrucai.com
- Business Phone: +91 90825 87107
- LinkedIn: https://www.linkedin.com/in/nishit-rathod/

Signature requirements:
- End with a clean, professional signature block that includes the sender's name followed by these three contact lines (Website, Phone, LinkedIn).
- Do NOT invent any other contact details (no fake email, no fake address, no fake title).
- Keep the signature compact, 4 to 5 lines max.

Format your output EXACTLY as a JSON object containing exactly these keys:
{
  "subject": "A compelling, low-pressure, high-open-rate subject line tailored to the lead",
  "body": "The email body, starting with 'Hi [Name/Team],' and ending with a professional signature from the sender that includes the website, phone, and LinkedIn."
}
"""

    if call_status == 'Interested':
        status_specific = """
This lead is marked as 'Interested'. The lead is NEW/FRESH and we are reaching out to them for the first time as a fresh prospect.
Goal: Draft a highly personalized, compelling B2B FRESH OUTREACH / FIRST-TOUCH email.
Instructions:
1. Do NOT write this as a follow-up or refer to any past calls, past meetings, or speak as if we have already communicated.
2. Treat them as a brand new prospect whom we want to pitch and start a relationship with.
3. Incorporate the answers/insights from the questionnaire and notes dynamically as "background research/custom observations" we did on their business. Use these insights to tailor the outreach, showing that we have analyzed their business, challenges, or goals.
4. Keep the pitch fresh, warm, low-pressure, and highly personalized, ending with a clear call to action to connect or schedule a brief strategy call.
"""
    elif call_status == 'Follow-Up':
        status_specific = """
This lead is marked as 'Follow-Up'. We have previously communicated or sent an initial outreach, and we now need to follow up with them to keep the relationship warm or re-engage them.
Goal: Draft a friendly, supportive B2B FOLLOW-UP email.
Instructions:
1. Reference the previous interaction, questions answered, or notes in a friendly, helpful manner (e.g., "Following up on our recent chat...", "Checking in on the points we discussed...").
2. Provide additional value, a gentle, low-pressure reminder, or supportive ideas.
3. Keep it warm, extremely authentic, and low-friction, making it effortless and natural for them to reply.
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
        notes_context += "Custom Questionnaire & Lead Details:\n"
        for it in items:
            q = it.get('question')
            a = it.get('answer')
            if q and a:
                notes_context += f"- Q: {q}\n  A: {a}\n"
    if free:
        notes_context += f"Additional Notes/Context:\n{free}\n"

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

