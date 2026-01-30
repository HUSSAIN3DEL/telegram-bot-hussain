import json
import os
import logging
import asyncio
import re
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    filters, 
    ContextTypes,
    CallbackQueryHandler
)

# ========== استيراد الإعدادات ==========
try:
    from config import *
except ImportError:
    print("❌ ملف config.py مفقود!")
    exit(1)

# ========== تهيئة السجلات ==========
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== التوكن من متغيرات البيئة ==========
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    print("❌ خطأ: BOT_TOKEN غير محدد!")
    exit(1)

# ========== قاعدة البيانات المتقدمة ==========
class AdvancedDatabase:
    def __init__(self):
        self.stickers = self._safe_load(STICKERS_FILE)
        self.texts = self._safe_load(TEXTS_FILE)
        self.users = self._safe_load(USERS_FILE)
        self.stats = self._safe_load(STATS_FILE)
        self._initialize_stats()
        
    def _safe_load(self, filename):
        try:
            if os.path.exists(filename):
                with open(filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            return {}
        except Exception as e:
            logger.error(f"خطأ في تحميل {filename}: {e}")
            return {}

    def _save_file(self, data, filename):
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"خطأ في حفظ {filename}: {e}")
            return False

    def _initialize_stats(self):
        required_stats = {
            "start_time": datetime.now().isoformat(),
            "total_users": 0,
            "total_stickers": len(self.stickers),
            "total_texts": len(self.texts),
            "total_responses": 0,
            "sticker_responses": 0,
            "text_responses": 0,
            "daily_stats": {},
            "user_stats": {}
        }
        
        for key, value in required_stats.items():
            if key not in self.stats:
                self.stats[key] = value
        
        self._save_file(self.stats, STATS_FILE)

    def save_all(self):
        self._save_file(self.stickers, STICKERS_FILE)
        self._save_file(self.texts, TEXTS_FILE)
        self._save_file(self.users, USERS_FILE)
        self._save_file(self.stats, STATS_FILE)
        return True

    def get_or_create_user(self, user_id, username="", first_name=""):
        user_key = str(user_id)
        
        if user_key not in self.users:
            self.users[user_key] = {
                "id": user_id,
                "username": username,
                "first_name": first_name,
                "joined_date": datetime.now().isoformat(),
                "usage_count": 0,
                "stickers_saved": 0,
                "texts_saved": 0,
                "last_active": datetime.now().isoformat(),
                "is_admin": user_id in ADMIN_IDS,
                "is_blocked": user_id in BLOCKED_USERS,
                "language": BOT_LANGUAGE
            }
            self.stats["total_users"] = len(self.users)
            self.save_all()
        
        self.users[user_key]["last_active"] = datetime.now().isoformat()
        return self.users[user_key]

    def find_sticker_response(self, file_id, user_id):
        """البحث عن رد نصي للملصق"""
        for sticker_id, data in self.stickers.items():
            if data.get("file_id") == file_id:
                data["usage"] += 1
                data["last_used"] = datetime.now().isoformat()
                
                self.stats["sticker_responses"] += 1
                self.stats["total_responses"] += 1
                
                user = self.get_or_create_user(user_id)
                user["usage_count"] += 1
                
                self.save_all()
                return data["response"]
        
        return None

    def find_text_response(self, message, user_id):
        """البحث عن رد نصي للكلمات"""
        msg_lower = message.strip().lower()
        
        if msg_lower in self.texts:
            return self._get_text_response(msg_lower, user_id)
        
        words = re.findall(r'[\w\u0600-\u06FF]+', msg_lower)
        for word in words:
            if word in self.texts:
                return self._get_text_response(word, user_id)
        
        return None
    
    def _get_text_response(self, keyword, user_id):
        text_data = self.texts[keyword]
        
        text_data["usage"] += 1
        text_data["last_used"] = datetime.now().isoformat()
        
        self.stats["text_responses"] += 1
        self.stats["total_responses"] += 1
        
        user = self.get_or_create_user(user_id)
        user["usage_count"] += 1
        
        self.save_all()
        return text_data["response"]

# ========== دوال المساعدة ==========
async def is_user_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """التحقق إذا كان المستخدم مشرفاً"""
    user_id = update.effective_user.id
    
    if user_id in ADMIN_IDS:
        return True
    
    if user_id in SUPER_ADMIN_IDS:
        return True
    
    if GROUP_ADMINS_ENABLED:
        try:
            chat = update.effective_chat
            if chat.type in ["group", "supergroup"]:
                member = await context.bot.get_chat_member(chat.id, user_id)
                return member.status in ["administrator", "creator"]
        except:
            pass
    
    return False

# ========== معالجات الأوامر ==========
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر البدء"""
    user = update.effective_user
    user_data = db.get_or_create_user(user.id, user.username, user.first_name)
    
    welcome_message = f"""
🌟 **مرحباً {user.first_name}!** 🌟

🤖 **{BOT_NAME} v{BOT_VERSION}**
👤 **المستخدم:** {user_data['usage_count']} استخدام
📅 **انضممت:** {datetime.fromisoformat(user_data['joined_date']).strftime(DATE_FORMAT)}
{'👑 **أنت مشرف**' if user_data['is_admin'] else ''}

📖 **الأوامر المتاحة:**
/help - عرض جميع الأوامر
/list - عرض جميع الردود
/stats - إحصائيات البوت
/search - البحث في الردود

👑 **أوامر للمشرفين:**
/ss - حفظ رد للملصق
/st - حفظ رد للكلمات
/del - حذف عنصر
/users - إدارة المستخدمين
"""
    
    keyboard = []
    if SHOW_HELP_BUTTON:
        keyboard.append([InlineKeyboardButton("📖 المساعدة", callback_data="cmd_help")])
    if SHOW_STATS_BUTTON:
        keyboard.append([InlineKeyboardButton("📊 الإحصائيات", callback_data="cmd_stats")])
    
    reply_markup = InlineKeyboardMarkup(keyboard) if ENABLE_BUTTONS else None
    
    await update.message.reply_text(
        welcome_message, 
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def handle_sticker_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الملصقات المرسلة"""
    user = update.effective_user
    sticker = update.message.sticker
    
    # منع الرد على غير المشرفين
    if not await is_user_admin(update, context):
        return
    
    if ENABLE_AUTO_RESPONSE and ENABLE_STICKER_RESPONSE:
        response = db.find_sticker_response(sticker.file_id, user.id)
        if response:
            await update.message.reply_text(response, disable_web_page_preview=True)

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة النصوص المرسلة"""
    user = update.effective_user
    message_text = update.message.text
    
    # منع الرد على غير المشرفين
    if not await is_user_admin(update, context):
        return
    
    if ENABLE_AUTO_RESPONSE and ENABLE_TEXT_RESPONSE:
        response = db.find_text_response(message_text, user.id)
        if response:
            await update.message.reply_text(response, disable_web_page_preview=True)

# ========== دالة التشغيل ==========
def main():
    """تشغيل البوت"""
    try:
        print(f"🚀 بدء تشغيل {BOT_NAME} v{BOT_VERSION}")
        
        app = Application.builder().token(TOKEN).build()
        
        # إضافة معالجات الأوامر
        app.add_handler(CommandHandler("start", start_command))
        
        # إضافة معالجات الرسائل
        app.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker_message))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
        
        app.run_polling(
            poll_interval=POLL_INTERVAL,
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
    
    except Exception as e:
        logger.error(f"خطأ في تشغيل البوت: {e}")

if __name__ == "__main__":
    main()
