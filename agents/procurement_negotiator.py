"""
💼 Procurement Negotiator
Autonomous purchasing agent. Multi-criteria supplier selection + payment generation.

Responsibilities:
- Query supplier database for needed items
- Score suppliers using multi-criteria: price (35%) + rating (25%) + ETA (25%) + MOQ fit (15%)
- Generate Purchase Order with line items
- Create payment via DOKU MCP (Virtual Account / QRIS) — Phase 7
- Handle supplier rejection by falling back to next-best option (max 3 attempts)
- Hand off restock ETA to Customer Concierge
"""
import json
import random
import string
from datetime import datetime
from tools import db, llm, doku_mcp

AGENT_NAME = "💼 Procurement Negotiator"

SYSTEM_PROMPT = """You are Procurement Negotiator, an autonomous purchasing agent for UMKM in Indonesia. 
You optimize across multiple criteria, never just price. You are analytical, cost-conscious, and decisive.

When ranking suppliers, use this weighting:
- Price (lower is better): 35%
- Rating (higher is better): 25%
- ETA (faster is better): 25%
- MOQ-friendly: 15%

Your reasoning MUST be transparent — always explain WHY you picked a supplier.
"""


def _generate_po_number() -> str:
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"PO-{datetime.now().strftime('%Y%m%d')}-{suffix}"


def find_suppliers_for_items(critical_items: list[str]) -> dict:
    """Look up all suppliers that can fulfill the critical items."""
    placeholders = ','.join(['?'] * len(critical_items))
    rows = db.query_all(f"""
        SELECT s.id as supplier_id, s.name, s.rating, s.avg_eta_hours, s.moq_friendly,
               o.item_name, o.unit_price, o.moq
        FROM suppliers s
        JOIN supplier_offerings o ON s.id = o.supplier_id
        WHERE o.item_name IN ({placeholders}) AND o.in_stock = 1
        ORDER BY o.item_name, o.unit_price
    """, tuple(critical_items))
    
    # Group by supplier
    by_supplier = {}
    for r in rows:
        sid = r['supplier_id']
        if sid not in by_supplier:
            by_supplier[sid] = {
                'supplier_id': sid,
                'name': r['name'],
                'rating': r['rating'],
                'eta_hours': r['avg_eta_hours'],
                'moq_friendly': bool(r['moq_friendly']),
                'items': {}
            }
        by_supplier[sid]['items'][r['item_name']] = {
            'unit_price': r['unit_price'],
            'moq': r['moq']
        }
    
    return by_supplier


def select_best_supplier(critical_items: list[str], quantities_needed: dict, exclude_ids: list[int] = None) -> dict:
    """
    Core agent logic: LLM-driven supplier selection with explicit reasoning.
    
    quantities_needed: {"Ayam Fillet": 10, "Cabai Merah": 5}
    exclude_ids: suppliers already tried and rejected
    """
    exclude_ids = exclude_ids or []
    db.log_agent_action(AGENT_NAME, "supplier_search_started", {
        "items": critical_items,
        "quantities": quantities_needed,
        "excluding": exclude_ids
    })
    
    all_suppliers = find_suppliers_for_items(critical_items)
    
    # Filter out excluded + suppliers missing items
    candidates = {
        sid: s for sid, s in all_suppliers.items()
        if sid not in exclude_ids
        and all(item in s['items'] for item in critical_items)
    }
    
    if not candidates:
        db.log_agent_action(AGENT_NAME, "no_supplier_available", {"excluded": exclude_ids})
        return {"error": "Tidak ada supplier yang bisa memenuhi semua item kritis."}
    
    # Build comparison table for LLM
    supplier_summary = []
    for sid, s in candidates.items():
        total_cost = sum(
            s['items'][item]['unit_price'] * quantities_needed.get(item, s['items'][item]['moq'])
            for item in critical_items
        )
        supplier_summary.append({
            'supplier_id': sid,
            'name': s['name'],
            'rating': s['rating'],
            'eta_hours': s['eta_hours'],
            'moq_friendly': s['moq_friendly'],
            'items_pricing': {k: v['unit_price'] for k, v in s['items'].items()},
            'moq_requirements': {k: v['moq'] for k, v in s['items'].items()},
            'estimated_total_cost_idr': total_cost
        })
    
    user_prompt = f"""Pilih supplier TERBAIK dari kandidat berikut untuk restock kritis.

ITEM YANG DIBUTUHKAN (dengan kuantitas):
{json.dumps(quantities_needed, ensure_ascii=False, indent=2)}

KANDIDAT SUPPLIER:
{json.dumps(supplier_summary, ensure_ascii=False, indent=2)}

ATURAN SCORING:
- Harga lebih murah = lebih baik (35% bobot)
- Rating lebih tinggi = lebih baik (25% bobot)
- ETA lebih cepat = lebih baik (25% bobot)
- MOQ-friendly (true) = lebih baik (15% bobot)

Output WAJIB format JSON valid (tanpa markdown):
{{
  "selected_supplier_id": angka,
  "selected_supplier_name": "...",
  "total_cost_idr": angka,
  "reasoning": "2-3 kalimat menjelaskan KENAPA supplier ini terpilih, sebutkan trade-off dengan kandidat lain",
  "comparison_summary": [
    {{"name": "Supplier A", "score": 0.87, "pros": "...", "cons": "..."}},
    ...
  ]
}}

Output HANYA JSON.
"""
    
    response = llm.chat(SYSTEM_PROMPT, user_prompt, max_tokens=1500, temperature=0.4)
    
    try:
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()
        decision = json.loads(cleaned)
    except json.JSONDecodeError as e:
        db.log_agent_action(AGENT_NAME, "decision_parse_error", {"error": str(e), "raw": response[:500]})
        return {"error": "Decision parse failed", "raw": response}
    
    db.log_agent_action(AGENT_NAME, "supplier_selected", {
        "supplier_id": decision.get("selected_supplier_id"),
        "supplier_name": decision.get("selected_supplier_name"),
        "total_cost": decision.get("total_cost_idr")
    })
    
    return decision


def generate_purchase_order(supplier_id: int, supplier_name: str, items_with_qty: dict, total_cost: int) -> dict:
    """
    Create PO record + invoke DOKU MCP to generate Virtual Account for B2B payment.
    
    This is the integration point with DOKU MCP Server.
    The agent autonomously creates a payable invoice for the supplier.
    """
    po_number = _generate_po_number()
    items_json = json.dumps(items_with_qty, ensure_ascii=False)
    
    # 1. Create PO in our DB
    po_id = db.execute("""
        INSERT INTO purchase_orders (po_number, supplier_id, items_json, total_amount, status)
        VALUES (?, ?, ?, ?, 'PENDING')
    """, (po_number, supplier_id, items_json, total_cost))
    
    db.log_agent_action(AGENT_NAME, "po_db_created", {"po_number": po_number, "amount": total_cost})
    
    # 2. Call DOKU MCP to create Virtual Account (this is THE autonomous payment step)
    db.log_agent_action(AGENT_NAME, "doku_mcp_calling", {"po_number": po_number})
    va_response = doku_mcp.create_virtual_account(
        invoice_number=po_number,
        amount_idr=total_cost,
        customer_name=supplier_name,
    )
    
    # 3. Extract VA data
    va_data = va_response.get("data", {})
    va_number = va_data.get("virtualAccountNumber") or va_data.get("va_number") or "PENDING"
    bank = va_data.get("bank", "BCA")
    
    db.log_agent_action(AGENT_NAME, "doku_va_created", {
        "po_number": po_number,
        "va_number": va_number,
        "bank": bank,
        "source": va_response.get("source"),
    })
    
    # 4. Update PO with VA number
    db.execute("UPDATE purchase_orders SET doku_va_number = ? WHERE id = ?", (va_number, po_id))
    
    po = {
        "po_id": po_id,
        "po_number": po_number,
        "supplier_id": supplier_id,
        "supplier_name": supplier_name,
        "items": items_with_qty,
        "total_amount": total_cost,
        "status": "PENDING_PAYMENT",
        "eta_estimate": "1-2 hari kerja",
        "doku_va_number": va_number,
        "doku_bank": bank,
        "doku_source": va_response.get("source"),
    }
    
    db.log_agent_action(AGENT_NAME, "purchase_order_created", po)
    return po


def format_for_telegram(decision: dict, po: dict = None) -> str:
    """Render decision + PO for Telegram."""
    if "error" in decision:
        return f"⚠️ {AGENT_NAME} error: {decision['error']}"
    
    lines = [
        f"{AGENT_NAME} — Keputusan Pembelian",
        "",
        f"🏆 *Supplier terpilih:* {decision.get('selected_supplier_name')}",
        f"💰 *Total estimasi:* Rp {decision.get('total_cost_idr', 0):,}",
        "",
        f"🧠 *Reasoning:*",
        f"{decision.get('reasoning', '-')}",
    ]
    
    if decision.get("comparison_summary"):
        lines.append("")
        lines.append("*Perbandingan kandidat:*")
        for c in decision["comparison_summary"]:
            lines.append(f"• {c['name']} (score: {c.get('score', 0):.2f}) — {c.get('pros', '')}")
    
    if po:
        lines.append("")
        lines.append(f"📄 *Purchase Order:* `{po['po_number']}`")
        lines.append(f"⏱️ ETA: {po['eta_estimate']}")
        lines.append("")
        lines.append(f"💳 *DOKU Virtual Account Generated*")
        lines.append(f"🏦 Bank: {po.get('doku_bank', 'BCA')}")
        lines.append(f"🔢 VA Number: `{po.get('doku_va_number', '-')}`")
        lines.append(f"💰 Amount: Rp {po['total_amount']:,}")
        lines.append(f"_(source: {po.get('doku_source', 'doku_mcp')})_")
        lines.append("")
        lines.append("→ PO + VA sudah dikirim ke supplier. Selanjutnya notify customer waitlist...")
    
    return "\n".join(lines)
