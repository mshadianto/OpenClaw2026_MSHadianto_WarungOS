"""WarungOS Telegram Bot — Autonomous Multi-Agent System."""
import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

from agents import orchestrator, inventory_sentinel
import base64

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


WELCOME_MSG = """🦞 *Selamat datang di WarungOS*

Saya adalah _autonomous multi-agent system_ untuk operasional warung Anda. Tim 3 AI agent kerja kolaboratif tanpa intervensi manusia:

🔍 *Inventory Sentinel* — pantau stok & forecast
💼 *Procurement Negotiator* — pilih supplier + bayar via DOKU
📱 *Customer Concierge* — notify customer waitlist

*Perintah:*
/restock — Jalankan workflow restock otomatis
/status — Cek status sistem & aktivitas agent terakhir
/reset — Reset demo data ke kondisi awal
/help — Tampilkan bantuan

_Powered by Claude Sonnet 4.6 via Sumopod + DOKU MCP_
"""


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME_MSG, parse_mode=ParseMode.MARKDOWN)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME_MSG, parse_mode=ParseMode.MARKDOWN)


async def restock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Trigger the full autonomous restock workflow."""
    chat_id = update.effective_chat.id
    
    async def send(text: str):
        """Helper to send a message and handle markdown errors gracefully."""
        try:
            await context.bot.send_message(
                chat_id=chat_id, 
                text=text, 
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.warning(f"Markdown send failed, retrying plain: {e}")
            await context.bot.send_message(chat_id=chat_id, text=text)
    
    try:
        summary = await orchestrator.run_full_restock_workflow(send)
        logger.info(f"Workflow completed: {summary.get('outcome')}")
    except Exception as e:
        logger.exception("Workflow error")
        await send(f"⚠️ Workflow error: {str(e)[:300]}")


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show recent agent activity log."""
    from tools import db
    activities = db.get_recent_activity(limit=10)
    if not activities:
        await update.message.reply_text("📊 Belum ada aktivitas agent.")
        return
    
    lines = ["📊 *Aktivitas Agent Terakhir:*\n"]
    for a in activities:
        lines.append(f"• `{a['created_at'][:19]}` — {a['agent_name']}: {a['action']}")
    
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset demo data to fresh state."""
    import subprocess
    try:
        subprocess.run(
            ["sqlite3", "data/warungos.db"],
            input=open("data/seed.sql").read(),
            text=True,
            check=True
        )
        await update.message.reply_text("✅ Demo data direset ke kondisi awal.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Reset gagal: {e}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fallback: any non-command text → general assistant."""
    from tools import llm
    user_text = update.message.text
    try:
        reply = llm.chat(
            system="Kamu adalah WarungOS, asisten AI untuk pemilik UMKM Indonesia. Untuk menjalankan workflow restock otomatis, beritahu user untuk kirim /restock. Untuk cek aktivitas, /status. Jawab singkat & ramah.",
            user=user_text,
            max_tokens=300
        )
        await update.message.reply_text(reply)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)[:200]}")



async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Receive shelf photo, run Vision OCR, then auto-trigger restock workflow.
    
    This is the headline UX: 1 photo → autonomous multi-agent workflow.
    """
    chat_id = update.effective_chat.id
    
    async def send(text: str):
        try:
            await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await context.bot.send_message(chat_id=chat_id, text=text)
    
    await send("📸 *Foto diterima.* Inventory Sentinel sedang menganalisis...")
    
    # 1. Download photo from Telegram
    photo = update.message.photo[-1]  # highest resolution
    photo_file = await photo.get_file()
    photo_bytes = await photo_file.download_as_bytearray()
    image_b64 = base64.b64encode(bytes(photo_bytes)).decode()
    
    # 2. Run vision analysis
    import asyncio
    vision_result = await asyncio.to_thread(
        inventory_sentinel.analyze_shelf_photo, image_b64, "jpeg"
    )
    
    if "error" in vision_result:
        await send(f"⚠️ Vision analysis gagal: {vision_result['error']}")
        return
    
    if vision_result.get("overall_quality") == "poor":
        await send(
            "🔴 *Kualitas foto kurang baik.*\n\n"
            "Mohon kirim ulang foto dengan:\n"
            "• Pencahayaan cukup\n"
            "• Fokus ke rak/stok\n"
            "• Jarak dekat (1-2 meter)"
        )
        return
    
    # 3. Update inventory DB from vision
    db_update = await asyncio.to_thread(
        inventory_sentinel.update_inventory_from_vision, vision_result
    )
    
    # 4. Show vision result
    await send(inventory_sentinel.format_vision_result(vision_result, db_update))
    
    # 5. Auto-trigger full workflow
    await send("\n🤖 *Auto-triggering restock workflow...*")
    try:
        summary = await orchestrator.run_full_restock_workflow(send)
        logger.info(f"Photo-triggered workflow completed: {summary.get('outcome')}")
    except Exception as e:
        logger.exception("Photo workflow error")
        await send(f"⚠️ Workflow error: {str(e)[:300]}")



def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    app = Application.builder().token(token).build()
    
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("restock", restock_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("reset", reset_cmd))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🦞 WarungOS bot starting — Multi-Agent System ready")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
