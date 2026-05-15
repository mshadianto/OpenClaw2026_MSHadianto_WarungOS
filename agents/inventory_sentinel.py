"""
🔍 Inventory Sentinel
Specialized AI agent for visual stock monitoring and depletion forecasting.

Responsibilities:
- Analyze shelf photos via Claude Vision (OCR + counting)
- Cross-reference current stock with sales velocity
- Forecast depletion timeline per SKU
- Identify CRITICAL items that need immediate restocking
- Hand off critical items to Procurement Negotiator
"""
import json
from datetime import datetime
from tools import db, llm

AGENT_NAME = "🔍 Inventory Sentinel"

SYSTEM_PROMPT = """You are Inventory Sentinel, a vigilant AI agent specialized in monitoring 
warung inventory through visual analysis and depletion forecasting. You are methodical, 
data-driven, and proactive.

Your job:
1. Analyze inventory snapshots and sales history
2. Forecast which items will deplete and when
3. Classify each item: CRITICAL (<3 days), LOW (3-7 days), HEALTHY (>7 days)
4. Be concise — output structured JSON, not paragraphs

You NEVER make purchase decisions. Your job is DETECTION.
"""


def analyze_current_inventory() -> dict:
    """
    Core agent logic: read inventory + sales history,
    forecast depletion, classify items.
    
    Returns structured result for handoff.
    """
    db.log_agent_action(AGENT_NAME, "started_analysis")
    
    # 1. Read current inventory
    inventory = db.query_all("SELECT * FROM inventory ORDER BY item_name")
    
    # 2. Read recent sales (last 7 days)
    sales = db.query_all("""
        SELECT item_name, SUM(quantity_sold) as total_sold, COUNT(*) as days_with_sales
        FROM sales_history 
        WHERE sale_date >= date('now', '-7 day')
        GROUP BY item_name
    """)
    sales_map = {s['item_name']: s for s in sales}
    
    # 3. Build prompt with structured data
    inventory_text = "\n".join([
        f"- {item['item_name']}: {item['current_stock']} {item['unit']} "
        f"(avg sold/day: {sales_map.get(item['item_name'], {}).get('total_sold', 0) / 7:.1f})"
        for item in inventory
    ])
    
    user_prompt = f"""Analisis inventory warung berikut dan klasifikasikan tiap item.

INVENTORY SAAT INI:
{inventory_text}

ATURAN KLASIFIKASI:
- CRITICAL: akan habis dalam <3 hari berdasarkan kecepatan penjualan
- LOW: akan habis dalam 3-7 hari  
- HEALTHY: stok cukup >7 hari

Output WAJIB format JSON valid (tanpa markdown wrapper):
{{
  "summary": "1-kalimat ringkasan situasi",
  "items": [
    {{
      "name": "Nama Item",
      "current_stock": angka,
      "unit": "kg/butir/liter",
      "avg_daily_sold": angka_desimal,
      "days_until_zero": angka_desimal,
      "status": "CRITICAL|LOW|HEALTHY",
      "reason": "1-kalimat singkat kenapa status ini"
    }}
  ],
  "critical_items": ["nama item 1", "nama item 2"],
  "should_handoff_to_procurement": true|false
}}

Output HANYA JSON, tidak ada teks lain.
"""

    response = llm.chat(SYSTEM_PROMPT, user_prompt, max_tokens=1200, temperature=0.3)
    
    # Parse JSON response (robust to potential markdown)
    try:
        # Strip markdown code fences if model added them
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()
        result = json.loads(cleaned)
    except json.JSONDecodeError as e:
        db.log_agent_action(AGENT_NAME, "json_parse_error", {"error": str(e), "raw": response[:500]})
        return {
            "error": "JSON parse failed",
            "raw_response": response,
            "should_handoff_to_procurement": False
        }
    
    # Log structured result
    db.log_agent_action(AGENT_NAME, "analysis_complete", {
        "critical_count": len(result.get("critical_items", [])),
        "summary": result.get("summary", "")
    })
    
    return result


def format_for_telegram(result: dict) -> str:
    """Format analysis result for human-readable Telegram message."""
    if "error" in result:
        return f"⚠️ Inventory Sentinel error: {result['error']}"
    
    lines = [
        f"{AGENT_NAME} — Analisis Selesai",
        "",
        f"📋 {result.get('summary', '')}",
        "",
        "*Status Per Item:*"
    ]
    
    status_emoji = {"CRITICAL": "🔴", "LOW": "🟡", "HEALTHY": "🟢"}
    for item in result.get("items", []):
        emoji = status_emoji.get(item["status"], "⚪")
        lines.append(
            f"{emoji} *{item['name']}*: {item['current_stock']} {item['unit']} "
            f"(~{item.get('days_until_zero') or '∞'} hari) — {item['reason']}"
        )
    
    if result.get("critical_items"):
        lines.append("")
        lines.append(f"🚨 *Critical items:* {', '.join(result['critical_items'])}")
        if result.get("should_handoff_to_procurement"):
            lines.append("→ Akan kirim ke *Procurement Negotiator*...")
    
    return "\n".join(lines)
