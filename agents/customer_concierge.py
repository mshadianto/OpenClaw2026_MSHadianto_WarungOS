"""
📱 Customer Concierge
Engagement agent that maintains customer trust via proactive personalized notifications.

Responsibilities:
- Query waitlist for customers waiting on specific items
- Compose personalized messages (use name, context, casual but respectful)
- Dispatch via Telegram (in real deployment: WhatsApp via Fonnte/DOKU PayChat)
- Track delivery status per message
- Summarize outcomes back to owner
"""
import json
from tools import db, llm

AGENT_NAME = "📱 Customer Concierge"

SYSTEM_PROMPT = """You are Customer Concierge, a warm and professional engagement agent for an Indonesian warung. 
You speak Bahasa Indonesia naturally, use Mas/Mbak/Bu/Pak appropriately, and make every message feel PERSONAL — 
never templated.

Rules:
- Always use customer's name and reference EXACTLY what they asked for
- Casual but respectful Bahasa Indonesia
- Include estimated availability time (use realistic phrases like "Insya Allah Kamis sore")
- Sign off as "— WarungOS"
- Keep each message under 4 sentences
"""


def get_waitlist_for_items(items: list[str]) -> list[dict]:
    """Get customers waiting for any of the restocked items."""
    placeholders = ','.join(['?'] * len(items))
    return db.query_all(f"""
        SELECT * FROM customer_waitlist 
        WHERE item_requested IN ({placeholders}) AND notified = 0
        ORDER BY id
    """, tuple(items))


def compose_personalized_messages(restocked_items: list[str], eta_estimate: str = "1-2 hari kerja") -> dict:
    """Generate personalized WhatsApp-style message for each waiting customer."""
    db.log_agent_action(AGENT_NAME, "compose_started", {"items": restocked_items, "eta": eta_estimate})
    
    waitlist = get_waitlist_for_items(restocked_items)
    
    if not waitlist:
        db.log_agent_action(AGENT_NAME, "no_customers_waiting", {"items": restocked_items})
        return {"messages": [], "count": 0, "note": "Tidak ada customer di waitlist untuk item ini."}
    
    customers_data = [
        {
            "id": c['id'],
            "name": c['customer_name'],
            "phone": c['phone'],
            "item": c['item_requested'],
            "quantity": c['quantity'],
            "notes": c['notes']
        }
        for c in waitlist
    ]
    
    user_prompt = f"""Buatkan pesan WhatsApp personal untuk tiap customer yang menunggu stok.

CUSTOMERS YANG MENUNGGU:
{json.dumps(customers_data, ensure_ascii=False, indent=2)}

INFO RESTOCK:
- Item yang sudah diorder: {', '.join(restocked_items)}
- ETA datang: {eta_estimate}

Buat pesan TIAP customer yang:
- Pakai nama mereka (Mas/Mbak/Bu/Pak sesuai konteks)
- Sebutin EXACT item yang mereka pesan + jumlahnya
- Mention notes mereka kalau relevan (contoh: "untuk catering Kamis")
- Casual tapi sopan
- Sign off "— WarungOS"

Output WAJIB format JSON valid (tanpa markdown):
{{
  "messages": [
    {{
      "customer_id": angka,
      "customer_name": "...",
      "phone": "...",
      "message_text": "Halo Bu Sari, ..."
    }}
  ]
}}

Output HANYA JSON.
"""
    
    response = llm.chat(SYSTEM_PROMPT, user_prompt, max_tokens=1500, temperature=0.7)
    
    try:
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()
        result = json.loads(cleaned)
    except json.JSONDecodeError as e:
        db.log_agent_action(AGENT_NAME, "compose_parse_error", {"error": str(e), "raw": response[:500]})
        return {"error": "Compose parse failed", "raw": response}
    
    # Mark as notified in DB (in real deployment, only after successful send)
    for msg in result.get("messages", []):
        db.execute("UPDATE customer_waitlist SET notified = 1 WHERE id = ?", (msg["customer_id"],))
    
    result["count"] = len(result.get("messages", []))
    db.log_agent_action(AGENT_NAME, "messages_composed", {"count": result["count"]})
    
    return result


def format_for_telegram(result: dict) -> str:
    """Render composed messages for Telegram preview."""
    if "error" in result:
        return f"⚠️ {AGENT_NAME} error: {result['error']}"
    
    if result.get("count", 0) == 0:
        return f"{AGENT_NAME} — Tidak ada customer waitlist untuk item ini."
    
    lines = [
        f"{AGENT_NAME} — {result['count']} Pesan Terkirim",
        ""
    ]
    
    for msg in result.get("messages", [])[:5]:  # Show first 5
        lines.append(f"📨 *{msg['customer_name']}* ({msg['phone']})")
        lines.append(f"_{msg['message_text']}_")
        lines.append("")
    
    if result['count'] > 5:
        lines.append(f"... dan {result['count'] - 5} pesan lainnya")
    
    return "\n".join(lines)
