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


def analyze_shelf_photo(image_base64: str, image_format: str = "jpeg") -> dict:
    """
    Analyze a photo of a warung shelf using Claude Vision via Sumopod.
    
    Args:
        image_base64: base64-encoded image content
        image_format: 'jpeg' or 'png'
    
    Returns: structured detection result with items, quantities, confidence.
    """
    db.log_agent_action(AGENT_NAME, "vision_analysis_started")
    
    from openai import OpenAI
    import os
    client = OpenAI(
        api_key=os.getenv("SUMOPOD_API_KEY"),
        base_url=os.getenv("SUMOPOD_BASE_URL"),
    )
    
    vision_prompt = """Analisis foto rak/stok warung Indonesia ini. Identifikasi tiap item yang terlihat dan estimasi jumlahnya.

Output WAJIB format JSON valid (tanpa markdown wrapper):
{
  "items_detected": [
    {
      "name": "Nama Item (Bahasa Indonesia, format Title Case)",
      "estimated_quantity": angka,
      "unit": "kg | butir | liter | bungkus | botol | dus",
      "confidence": 0.0-1.0
    }
  ],
  "overall_quality": "good | fair | poor",
  "summary": "1-kalimat ringkasan apa yang terlihat di foto"
}

PENTING:
- Pakai nama item sederhana yang umum di warung (Ayam Fillet, Cabai Merah, Telur Ayam, Beras Premium, dll)
- Confidence < 0.5 berarti gak yakin, jangan dimasukin
- Jika foto blur/gelap/bukan rak warung, set overall_quality=poor

Output HANYA JSON.
"""
    
    try:
        completion = client.chat.completions.create(
            model=os.getenv("SUMOPOD_MODEL", "claude-sonnet-4-6"),
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": vision_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{image_format};base64,{image_base64}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=1500,
            temperature=0.3,
        )
        response = completion.choices[0].message.content
    except Exception as e:
        db.log_agent_action(AGENT_NAME, "vision_error", {"error": str(e)})
        return {"error": f"Vision call failed: {e}"}
    
    # Parse JSON
    try:
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()
        result = json.loads(cleaned)
    except json.JSONDecodeError as e:
        db.log_agent_action(AGENT_NAME, "vision_parse_error", {"error": str(e), "raw": response[:300]})
        return {"error": "JSON parse failed", "raw": response}
    
    # Filter low-confidence items
    items = [
        item for item in result.get("items_detected", [])
        if item.get("confidence", 0) >= 0.5
    ]
    result["items_detected"] = items
    result["high_confidence_count"] = len(items)
    
    db.log_agent_action(AGENT_NAME, "vision_analysis_complete", {
        "items_count": len(items),
        "quality": result.get("overall_quality")
    })
    
    return result


def update_inventory_from_vision(vision_result: dict) -> dict:
    """
    Update the inventory table based on vision detection.
    Updates existing items, ignores new ones (for safety in demo).
    """
    if "error" in vision_result:
        return {"updated": 0, "error": vision_result["error"]}
    
    updated = []
    skipped = []
    
    for item in vision_result.get("items_detected", []):
        name = item["name"]
        qty = int(item["estimated_quantity"])
        
        # Check if item exists in inventory
        existing = db.query_all("SELECT * FROM inventory WHERE LOWER(item_name) = LOWER(?)", (name,))
        if existing:
            db.execute(
                "UPDATE inventory SET current_stock = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (qty, existing[0]["id"])
            )
            updated.append({"name": name, "new_stock": qty, "old_stock": existing[0]["current_stock"]})
        else:
            skipped.append(name)
    
    db.log_agent_action(AGENT_NAME, "inventory_updated_from_vision", {
        "updated_count": len(updated),
        "skipped": skipped
    })
    
    return {"updated": updated, "skipped": skipped}


def format_vision_result(vision_result: dict, db_update: dict) -> str:
    """Format vision detection result for Telegram."""
    if "error" in vision_result:
        return f"⚠️ Vision analysis error: {vision_result['error']}"
    
    quality = vision_result.get("overall_quality", "unknown")
    quality_emoji = {"good": "✅", "fair": "🟡", "poor": "🔴"}.get(quality, "⚪")
    
    lines = [
        f"📸 *Inventory Sentinel — Vision Analysis*",
        "",
        f"{quality_emoji} Kualitas foto: *{quality}*",
        f"📋 {vision_result.get('summary', '')}",
        "",
        f"*Item terdeteksi:* {vision_result.get('high_confidence_count', 0)}"
    ]
    
    for item in vision_result.get("items_detected", []):
        conf_pct = int(item.get("confidence", 0) * 100)
        lines.append(
            f"• {item['name']}: ~{item['estimated_quantity']} {item['unit']} "
            f"(confidence {conf_pct}%)"
        )
    
    if db_update.get("updated"):
        lines.append("")
        lines.append(f"💾 *{len(db_update['updated'])} item di-update di database:*")
        for u in db_update["updated"][:5]:
            lines.append(f"  - {u['name']}: {u['old_stock']} → {u['new_stock']}")
    
    if db_update.get("skipped"):
        lines.append("")
        lines.append(f"_({len(db_update['skipped'])} item baru di-skip untuk safety: {', '.join(db_update['skipped'][:3])}...)_")
    
    return "\n".join(lines)
