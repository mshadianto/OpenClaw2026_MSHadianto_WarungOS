"""
🎭 Orchestrator — Chains 3 agents in autonomous workflow.

This is the entry point that user triggers (via /restock command or photo).
It runs Sentinel → Negotiator → Concierge in sequence with proper handoffs and edge-case handling.
"""
import asyncio
from agents import inventory_sentinel, procurement_negotiator, customer_concierge
from tools import db


async def run_full_restock_workflow(send_telegram_message):
    """
    Main autonomous workflow.
    
    Args:
        send_telegram_message: async callable that posts to Telegram chat.
                               Lets us stream updates per agent.
    
    Returns: dict summary of the entire run.
    """
    summary = {"agents_ran": [], "outcome": "unknown"}
    
    # ============ AGENT 1: INVENTORY SENTINEL ============
    await send_telegram_message("🦞 *WarungOS workflow dimulai...*\n\n_Memanggil Inventory Sentinel..._")
    
    sentinel_result = await asyncio.to_thread(inventory_sentinel.analyze_current_inventory)
    summary["agents_ran"].append("inventory_sentinel")
    summary["sentinel_result"] = sentinel_result
    
    await send_telegram_message(inventory_sentinel.format_for_telegram(sentinel_result))
    
    critical = sentinel_result.get("critical_items", [])
    if not critical or not sentinel_result.get("should_handoff_to_procurement"):
        await send_telegram_message("✅ *Workflow selesai.* Tidak ada item kritis, tidak perlu restock.")
        summary["outcome"] = "no_action_needed"
        return summary
    
    # ============ AGENT 2: PROCUREMENT NEGOTIATOR ============
    await send_telegram_message(f"\n_Mengaktivasi Procurement Negotiator untuk: {', '.join(critical)}..._")
    
    # Quantity logic: pesan 2x kebutuhan harian (buffer 14 hari)
    quantities_needed = {}
    for item in critical:
        item_data = next((i for i in sentinel_result.get("items", []) if i["name"] == item), None)
        if item_data:
            daily_avg = item_data.get("avg_daily_sold", 1) or 1
            quantities_needed[item] = max(int(daily_avg * 14), 5)
        else:
            quantities_needed[item] = 10
    
    excluded_suppliers = []
    decision = None
    po = None
    confirmation = None
    
    # Try up to 3 suppliers (edge case: rejection fallback chain)
    for attempt in range(3):
        if attempt > 0:
            await send_telegram_message(
                f"\n_🔄 Attempt {attempt + 1}: mencari supplier alternatif..._\n"
                f"_Excluded: {len(excluded_suppliers)} supplier sebelumnya_"
            )
        
        decision = await asyncio.to_thread(
            procurement_negotiator.select_best_supplier,
            critical, quantities_needed, excluded_suppliers
        )
        
        if "error" in decision:
            await send_telegram_message(
                f"🚨 *Escalation ke Owner:*\n"
                f"{decision['error']}\n\n"
                f"Sudah coba {attempt} supplier, semua tidak tersedia. "
                f"Mohon intervensi manual untuk restock {', '.join(critical)}."
            )
            summary["outcome"] = "escalated_no_supplier"
            return summary
        
        supplier_id = decision["selected_supplier_id"]
        
        po = await asyncio.to_thread(
            procurement_negotiator.generate_purchase_order,
            supplier_id,
            decision["selected_supplier_name"],
            quantities_needed,
            decision["total_cost_idr"]
        )
        
        await send_telegram_message(procurement_negotiator.format_for_telegram(decision, po))
        
        # Check supplier response (simulated in demo)
        confirmation = await asyncio.to_thread(
            procurement_negotiator.simulate_supplier_response,
            supplier_id, po["po_number"]
        )
        
        if confirmation["confirmed"]:
            await send_telegram_message(
                f"✅ *Supplier confirmed* PO `{po['po_number']}`.\n"
                f"_{decision['selected_supplier_name']} accepted the order._"
            )
            break
        else:
            await send_telegram_message(
                f"❌ *Supplier ditolak.*\n"
                f"🧠 Alasan: _{confirmation['reason']}_\n\n"
                f"_Agent autonomously selecting next-best supplier..._"
            )
            excluded_suppliers.append(supplier_id)
            decision = None
            po = None
            continue
    
    if not po or not confirmation or not confirmation.get("confirmed"):
        await send_telegram_message(
            f"🚨 *Escalation:* Semua {len(excluded_suppliers)} supplier yang dicoba menolak. "
            f"Workflow di-pause, mohon intervensi owner."
        )
        summary["outcome"] = "escalated_all_rejected"
        return summary
    
    summary["agents_ran"].append("procurement_negotiator")
    summary["decision"] = decision
    summary["po"] = po
    
    # ============ AGENT 3: CUSTOMER CONCIERGE ============
    await send_telegram_message(f"\n_Mengaktivasi Customer Concierge..._")
    
    concierge_result = await asyncio.to_thread(
        customer_concierge.compose_personalized_messages,
        critical,
        po["eta_estimate"] if po else "1-2 hari kerja"
    )
    
    await send_telegram_message(customer_concierge.format_for_telegram(concierge_result))
    summary["agents_ran"].append("customer_concierge")
    summary["concierge_result"] = concierge_result
    
    # ============ FINAL SUMMARY ============
    notified_count = concierge_result.get("count", 0)
    final_msg = (
        f"\n✅ *Workflow selesai — Zero human intervention.*\n\n"
        f"📊 Ringkasan:\n"
        f"• Critical items detected: {len(critical)}\n"
        f"• Supplier dipilih: {decision.get('selected_supplier_name', '-')}\n"
        f"• Total payment: Rp {decision.get('total_cost_idr', 0):,}\n"
        f"• PO number: `{po['po_number'] if po else '-'}`\n"
        f"• Customer notified: {notified_count}\n"
    )
    await send_telegram_message(final_msg)
    
    summary["outcome"] = "success"
    return summary
