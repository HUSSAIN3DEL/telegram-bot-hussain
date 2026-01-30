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
        # تحميل الملفات مع القيم الافتراضية
        self.stickers = self._safe_load(STICKERS_FILE)
        self.texts = self._safe_load(TEXTS_FILE)
        self.users = self._safe_load(USERS_FILE)
        self.stats = self._safe_load(STATS_FILE)
        
        # تهيئة الإحصائيات
        self._initialize_stats()
        
    def _safe_load(self, filename):
        """تحميل ملف JSON بشكل آمن"""
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
        """حفظ البيانات في ملف"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"خطأ في حفظ {filename}: {e}")
            return False
    
    def _initialize_stats(self):
        """تهيئة الإحصائيات المفقودة"""
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
        """حفظ جميع البيانات"""
        self._save_file(self.stickers, STICKERS_FILE)
        self._save_file(self.texts, TEXTS_FILE)
        self._save_file(self.users, USERS_FILE)
        self._save_file(self.stats, STATS_FILE)
        return True
    
    def get_or_create_user(self, user_id, username="", first_name=""):
        """الحصول على بيانات المستخدم أو إنشائها"""
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
    
    def add_sticker_response(self, file_id, keywords, response_text, user_id):
        """إضافة رد نصي للملصق"""
        sticker_id = f"sticker_{len(self.stickers) + 1}"
        
        self.stickers[sticker_id] = {
            "file_id": file_id,
            "keywords": keywords,
            "response": response_text,
            "created_by": user_id,
            "created_at": datetime.now().isoformat(),
            "usage": 0,
            "last_used": None
        }
        
        self.stats["total_stickers"] = len(self.stickers)
        
        user = self.get_or_create_user(user_id)
        user["stickers_saved"] += 1
        
        self.save_all()
        return sticker_id
    
    def find_sticker_response(self, file_id, user_id):
        """البحث عن رد نصي للملصق"""
        user = self.get_or_create_user(user_id)
        if not user.get("is_admin", False):  # إضافة التحقق من صلاحيات المستخدم هنا
            return None
        
        for sticker_id, data in self.stickers.items():
            if data.get("file_id") == file_id:
                data["usage"] += 1
                data["last_used"] = datetime.now().isoformat()
                
                self.stats["sticker_responses"] += 1
                self.stats["total_responses"] += 1
                
                user["usage_count"] += 1
                
                self.save_all()
                return data["response"]
        
        return None
    
    def add_text_response(self, keywords, response_text, user_id):
        """إضافة رد نصي للكلمات"""
        for keyword in keywords:
            keyword_lower = keyword.strip().lower()
            if keyword_lower and keyword_lower not in self.texts:
                self.texts[keyword_lower] = {
                    "keyword": keyword.strip(),
                    "response": response_text,
                    "keywords": keywords,
                    "created_by": user_id,
                    "created_at": datetime.now().isoformat(),
                    "usage": 0,
                    "last_used": None
                }
        
        self.stats["total_texts"] = len(self.texts)
        
        user = self.get_or_create_user(user_id)
        user["texts_saved"] += 1
        
        self.save_all()
        return True
    
    def find_text_response(self, message, user_id):
        """البحث عن رد نصي للكلمات"""
        user = self.get_or_create_user(user_id)
        if not user.get("is_admin", False):  # إضافة التحقق من صلاحيات المستخدم هنا
            return None
        
        msg_lower = message.strip().lower()
        
        if msg_lower in self.texts:
            return self._get_text_response(msg_lower, user_id)
        
        words = re.findall(r'[\w\u0600-\u06FF]+', msg_lower)
        for word in words:
            if word in self.texts:
                return self._get_text_response(word, user_id)
        
        return None
    
    def _get_text_response(self, keyword, user_id):
        """الحصول على الرد وتحديث الإحصائيات"""
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
    print(f"🚀 بدء تشغيل {BOT_NAME} v{BOT_VERSION}")
    print(f"👤 المطور: {BOT_CREATOR}")
    print("=" * 50)
    print("⚙️ الإعدادات النشطة:")
    print(f"• الرد التلقائي: {'✅' if ENABLE_AUTO_RESPONSE else '❌'}")
    print(f"• تأخير الرد: {RESPONSE_DELAY} ثانية")
    print("=" * 50)
    
    # إنشاء التطبيق
    app = Application.builder().token(TOKEN).build()
    
    # إضافة معالجات الأوامر
    app.add_handler(CommandHandler("start", start_command))
    
    # إضافة معالجات الرسائل
    app.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    # بدء الاستقبال
    app.run_polling(
        poll_interval=POLL_INTERVAL,
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )
    
if __name__ == "__main__":
    # إنشاء مجلد data إذا لم يكن موجوداً
    if not os.path.exists("data"):
        os.makedirs("data", exist_ok=True)
    
    main()    print("2. على GitHub: Settings → Secrets → Actions → New repository secret")
    print("3. أضف التوكن الجديد من @BotFather")
    exit(1)

# ========== قاعدة البيانات المتقدمة ==========
class AdvancedDatabase:
    def __init__(self):
        # تحميل الملفات مع القيم الافتراضية
        self.stickers = self._safe_load(STICKERS_FILE)
        self.texts = self._safe_load(TEXTS_FILE)
        self.users = self._safe_load(USERS_FILE)
        self.stats = self._safe_load(STATS_FILE)
        
        # تهيئة الإحصائيات
        self._initialize_stats()
        
    def _safe_load(self, filename):
        """تحميل ملف JSON بشكل آمن"""
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
        """حفظ البيانات في ملف"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"خطأ في حفظ {filename}: {e}")
            return False
    
    def _initialize_stats(self):
        """تهيئة الإحصائيات المفقودة"""
        # قائمة المفاتيح المطلوبة
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
        
        # إضافة المفاتيح المفقودة
        for key, value in required_stats.items():
            if key not in self.stats:
                self.stats[key] = value
        
        # حفظ الإحصائيات المحدثة
        self._save_file(self.stats, STATS_FILE)
    
    def save_all(self):
        """حفظ جميع البيانات"""
        self._save_file(self.stickers, STICKERS_FILE)
        self._save_file(self.texts, TEXTS_FILE)
        self._save_file(self.users, USERS_FILE)
        self._save_file(self.stats, STATS_FILE)
        return True
    
    # ========== إدارة المستخدمين ==========
    def get_or_create_user(self, user_id, username="", first_name=""):
        """الحصول على بيانات المستخدم أو إنشائها"""
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
        
        # تحديث وقت النشاط الأخير
        self.users[user_key]["last_active"] = datetime.now().isoformat()
        return self.users[user_key]
    
    # ========== إدارة الملصقات ==========
    def add_sticker_response(self, file_id, keywords, response_text, user_id):
        """إضافة رد نصي للملصق"""
        sticker_id = f"sticker_{len(self.stickers) + 1}"
        
        self.stickers[sticker_id] = {
            "file_id": file_id,
            "keywords": keywords,
            "response": response_text,
            "created_by": user_id,
            "created_at": datetime.now().isoformat(),
            "usage": 0,
            "last_used": None
        }
        
        self.stats["total_stickers"] = len(self.stickers)
        
        # تحديث إحصائيات المستخدم
        user = self.get_or_create_user(user_id)
        user["stickers_saved"] += 1
        
        self.save_all()
        return sticker_id
    
    def find_sticker_response(self, file_id, user_id):
        """البحث عن رد نصي للملصق"""
        for sticker_id, data in self.stickers.items():
            if data.get("file_id") == file_id:
                # تحديث الإحصائيات
                data["usage"] += 1
                data["last_used"] = datetime.now().isoformat()
                
                self.stats["sticker_responses"] += 1
                self.stats["total_responses"] += 1
                
                # تحديث الإحصائيات اليومية
                today = datetime.now().strftime("%Y-%m-%d")
                if "daily_stats" not in self.stats:
                    self.stats["daily_stats"] = {}
                if today not in self.stats["daily_stats"]:
                    self.stats["daily_stats"][today] = {"stickers": 0, "texts": 0}
                self.stats["daily_stats"][today]["stickers"] += 1
                
                # تحديث إحصائيات المستخدم
                user = self.get_or_create_user(user_id)
                user["usage_count"] += 1
                
                self.save_all()
                return data["response"]
        
        return None
    
    # ========== إدارة النصوص ==========
    def add_text_response(self, keywords, response_text, user_id):
        """إضافة رد نصي للكلمات"""
        for keyword in keywords:
            keyword_lower = keyword.strip().lower()
            if keyword_lower and keyword_lower not in self.texts:
                self.texts[keyword_lower] = {
                    "keyword": keyword.strip(),
                    "response": response_text,
                    "keywords": keywords,
                    "created_by": user_id,
                    "created_at": datetime.now().isoformat(),
                    "usage": 0,
                    "last_used": None
                }
        
        self.stats["total_texts"] = len(self.texts)
        
        # تحديث إحصائيات المستخدم
        user = self.get_or_create_user(user_id)
        user["texts_saved"] += 1
        
        self.save_all()
        return True
    
    def find_text_response(self, message, user_id):
        """البحث عن رد نصي للكلمات"""
        msg_lower = message.strip().lower()
        
        # البحث المباشر
        if msg_lower in self.texts:
            return self._get_text_response(msg_lower, user_id)
        
        # البحث في الكلمات
        words = re.findall(r'[\w\u0600-\u06FF]+', msg_lower)
        for word in words:
            if word in self.texts:
                return self._get_text_response(word, user_id)
        
        # البحث التقريبي إذا مفعل
        if FUZZY_SEARCH:
            for keyword in self.texts.keys():
                if keyword in msg_lower:
                    return self._get_text_response(keyword, user_id)
        
        return None
    
    def _get_text_response(self, keyword, user_id):
        """الحصول على الرد وتحديث الإحصائيات"""
        text_data = self.texts[keyword]
        
        # تحديث الإحصائيات
        text_data["usage"] += 1
        text_data["last_used"] = datetime.now().isoformat()
        
        self.stats["text_responses"] += 1
        self.stats["total_responses"] += 1
        
        # تحديث الإحصائيات اليومية
        today = datetime.now().strftime("%Y-%m-%d")
        if "daily_stats" not in self.stats:
            self.stats["daily_stats"] = {}
        if today not in self.stats["daily_stats"]:
            self.stats["daily_stats"][today] = {"stickers": 0, "texts": 0}
        self.stats["daily_stats"][today]["texts"] += 1
        
        # تحديث إحصائيات المستخدم
        user = self.get_or_create_user(user_id)
        user["usage_count"] += 1
        
        self.save_all()
        return text_data["response"]
    
    # ========== الحذف والإدارة ==========
    def delete_item(self, item_type, item_id, user_id):
        """حذف عنصر"""
        user = self.get_or_create_user(user_id)
        
        if not user.get("is_admin", False):
            return False
        
        if item_type == "sticker" and item_id in self.stickers:
            del self.stickers[item_id]
            self.stats["total_stickers"] = len(self.stickers)
            self.save_all()
            return True
        
        elif item_type == "text":
            item_id_lower = item_id.lower()
            if item_id_lower in self.texts:
                del self.texts[item_id_lower]
                self.stats["total_texts"] = len(self.texts)
                self.save_all()
                return True
        
        return False
    
    def get_all_items(self):
        """الحصول على جميع العناصر"""
        return {
            "stickers": self.stickers,
            "texts": self.texts,
            "stats": self.stats
        }
    
    def get_delete_list(self):
        """الحصول على قائمة العناصر للحذف"""
        items = []
        
        # إضافة الملصقات
        for sticker_id, data in self.stickers.items():
            keywords = ", ".join(data.get("keywords", []))[:20]
            items.append({
                "number": len(items) + 1,
                "type": "sticker",
                "id": sticker_id,
                "name": f"ملصق: {keywords}"
            })
        
        # إضافة النصوص
        for keyword, data in self.texts.items():
            response = data.get("response", "")[:20]
            items.append({
                "number": len(items) + 1,
                "type": "text",
                "id": keyword,
                "name": f"نص: {keyword} → {response}"
            })
        
        return items

# ========== تهيئة قاعدة البيانات ==========
db = AdvancedDatabase()

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

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر المساعدة"""
    help_text = f"""
📚 **دليل استخدام {BOT_NAME}**

**👑 أوامر المشرفين:**
• `/ss` - حفظ رد نصي للملصق (يطلب ملصق → كلمات → نص)
• `/st كلمات` - حفظ رد نصي (يطلب النص)
• `/del نوع معرف` - حذف عنصر
• `/users` - إدارة المستخدمين
• `/backup` - إنشاء نسخة احتياطية
• `/settings` - إعدادات البوت

**👥 أوامر عامة:**
• `/list` - عرض جميع الردود
• `/list ص` - عرض صفحة معينة
• `/search كلمة` - البحث في الردود
• `/stats` - إحصائيات البوت
• `/myinfo` - معلومات حسابك
• `/settings` - إعداداتك الشخصية

**⚙️ إعدادات البوت:**
• الرد التلقائي: {'✅ مفعل' if ENABLE_AUTO_RESPONSE else '❌ معطل'}
• تأخير الرد: {RESPONSE_DELAY} ثانية
• الحد الأقصى للعناصر: {MAX_LIST_ITEMS}
"""
    
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض الإحصائيات"""
    stats = db.stats
    
    # حساب بعض الإحصائيات الإضافية
    try:
        start_time = datetime.fromisoformat(stats.get("start_time", datetime.now().isoformat()))
        total_days = (datetime.now() - start_time).days
        total_days = max(total_days, 1)
        avg_daily = stats.get("total_responses", 0) // total_days
    except:
        total_days = 1
        avg_daily = 0
    
    stats_message = f"""
📊 **إحصائيات {BOT_NAME}**

**📈 عام:**
• وقت البدء: {datetime.fromisoformat(stats.get('start_time')).strftime(DATE_FORMAT) if stats.get('start_time') else 'غير معروف'}
• أيام التشغيل: {total_days} يوم
• متوسط يومي: {avg_daily} رد

**🎯 الردود:**
• الكلية: {stats.get('total_responses', 0)}
• للملصقات: {stats.get('sticker_responses', 0)}
• للنصوص: {stats.get('text_responses', 0)}

**🗂️ التخزين:**
• المستخدمين: {stats.get('total_users', 0)}
• الملصقات: {stats.get('total_stickers', 0)}
• النصوص: {stats.get('total_texts', 0)}

**📅 اليوم ({datetime.now().strftime('%Y-%m-%d')}):**
• الملصقات: {stats.get('daily_stats', {}).get(datetime.now().strftime('%Y-%m-%d'), {}).get('stickers', 0)}
• النصوص: {stats.get('daily_stats', {}).get(datetime.now().strftime('%Y-%m-%d'), {}).get('texts', 0)}
"""
    
    if SHOW_TOP_USERS > 0:
        # الحصول على أفضل المستخدمين
        users_list = []
        for user_id, user_data in db.users.items():
            if isinstance(user_data, dict):
                users_list.append((user_id, user_data))
        
        users_sorted = sorted(
            users_list,
            key=lambda x: x[1].get("usage_count", 0),
            reverse=True
        )[:SHOW_TOP_USERS]
        
        if users_sorted:
            stats_message += "\n**🏆 أفضل المستخدمين:**\n"
            for i, (user_id, user_data) in enumerate(users_sorted, 1):
                name = user_data.get("first_name", "مستخدم")
                stats_message += f"{i}. {name}: {user_data.get('usage_count', 0)} استخدام\n"
    
    await update.message.reply_text(stats_message, parse_mode="Markdown")

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض القائمة"""
    try:
        items = db.get_all_items()
        
        # عرض الملصقات
        stickers_msg = "🎨 **الملصقات:**\n"
        if items["stickers"]:
            for sid, data in items["stickers"].items():
                keywords = ", ".join(data.get("keywords", []))
                usage = data.get("usage", 0)
                stickers_msg += f"\n🆔 **{sid}**\n🔑 {keywords}\n📊 استخدم: {usage} مرة\n"
        else:
            stickers_msg += "لا توجد ملصقات\n"
        
        # عرض النصوص
        texts_msg = "\n💬 **النصوص:**\n"
        if items["texts"]:
            for kw, data in items["texts"].items():
                response = data.get("response", "")[:30]
                if len(data.get("response", "")) > 30:
                    response += "..."
                usage = data.get("usage", 0)
                texts_msg += f"\n🔑 **{kw}**\n💬 {response}\n📊 استخدم: {usage} مرة\n"
        else:
            texts_msg += "لا توجد نصوص\n"
        
        # إرسال الرسائل
        await update.message.reply_text(stickers_msg, parse_mode="Markdown")
        await asyncio.sleep(0.3)
        await update.message.reply_text(texts_msg, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"خطأ في /list: {e}")
        await update.message.reply_text("📋 **القائمة فارغة حالياً**")

# ========== حفظ الملصقات والنصوص ==========
async def save_sticker_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء عملية حفظ ملصق"""
    if not await is_user_admin(update, context):
        await update.message.reply_text("⛔️ هذا الأمر للمشرفين فقط!")
        return
    
    # وضع المستخدم في حالة انتظار الملصق
    context.user_data["save_mode"] = "sticker"
    context.user_data["save_step"] = 1
    
    await update.message.reply_text(
        "🎨 **حفظ رد نصي للملصق**\n\n"
        "📤 **الخطوة 1 من 3:**\n"
        "أرسل الملصق الذي تريد ربط رد نصي به..."
    )

async def save_text_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء عملية حفظ نص"""
    if not await is_user_admin(update, context):
        await update.message.reply_text("⛔️ هذا الأمر للمشرفين فقط!")
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ يجب تحديد الكلمات المفتاحية!\n"
            "📝 الاستخدام: /st كلمة1,كلمة2,كلمة3"
        )
        return
    
    keywords = [k.strip() for k in " ".join(context.args).split(",") if k.strip()]
    
    if not keywords:
        await update.message.reply_text("❌ يجب كتابة كلمات مفتاحية صحيحة!")
        return
    
    # وضع المستخدم في حالة انتظار النص
    context.user_data["save_mode"] = "text"
    context.user_data["save_step"] = 2
    context.user_data["keywords"] = keywords
    
    await update.message.reply_text(
        f"📝 **حفظ رد نصي**\n\n"
        f"🔑 الكلمات المفتاحية: {', '.join(keywords)}\n"
        f"📤 **الخطوة 2 من 2:**\n"
        f"أرسل النص الذي تريد ربطه بهذه الكلمات..."
    )

# ========== معالجة الرسائل ==========
async def handle_sticker_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الملصقات المرسلة"""
    user = update.effective_user
    sticker = update.message.sticker
    
    # الحالة 1: المستخدم في وضع حفظ الملصق (الخطوة 1)
    if context.user_data.get("save_mode") == "sticker" and context.user_data.get("save_step") == 1:
        context.user_data["sticker_file_id"] = sticker.file_id
        context.user_data["save_step"] = 2
        
        await update.message.reply_text(
            "✅ **تم استلام الملصق!**\n\n"
            "📝 **الخطوة 2 من 3:**\n"
            "اكتب الكلمات المفتاحية لهذا الملصق\n"
            "(مفصولة بفاصلة، مثال: عين,عينك,نور)"
        )
        return
    
    # الحالة 2: البحث عن رد للملصق المرسل
    if ENABLE_AUTO_RESPONSE and ENABLE_STICKER_RESPONSE:
        response = db.find_sticker_response(sticker.file_id, user.id)
        if response:
            if RESPONSE_DELAY > 0:
                await asyncio.sleep(RESPONSE_DELAY)
            await update.message.reply_text(response)

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة النصوص المرسلة"""
    user = update.effective_user
    message_text = update.message.text
    
    # ========== حالة الحفظ ==========
    
    # حالة 1: حفظ ملصق (الخطوة 2 - الكلمات المفتاحية)
    if (context.user_data.get("save_mode") == "sticker" and 
        context.user_data.get("save_step") == 2):
        
        keywords = [k.strip() for k in message_text.split(",") if k.strip()]
        
        if not keywords:
            await update.message.reply_text("❌ يجب كتابة كلمات مفتاحية صحيحة!")
            return
        
        context.user_data["keywords"] = keywords
        context.user_data["save_step"] = 3
        
        await update.message.reply_text(
            "✅ **تم حفظ الكلمات المفتاحية!**\n\n"
            "💬 **الخطوة 3 من 3:**\n"
            "اكتب النص الذي تريد ربطه بهذا الملصق\n"
            "(سيكون هذا هو رد البوت عند إرسال الملصق)"
        )
        return
    
    # حالة 2: حفظ ملصق (الخطوة 3 - النص)
    elif (context.user_data.get("save_mode") == "sticker" and 
          context.user_data.get("save_step") == 3):
        
        sticker_id = db.add_sticker_response(
            context.user_data.get("sticker_file_id"),
            context.user_data.get("keywords", []),
            message_text,
            user.id
        )
        
        # تنظيف بيانات المستخدم
        for key in ["save_mode", "save_step", "sticker_file_id", "keywords"]:
            context.user_data.pop(key, None)
        
        await update.message.reply_text(
            f"🎉 **تم الحفظ بنجاح!** 🎉\n\n"
            f"🆔 **المعرف:** {sticker_id}\n"
            f"🔑 **الكلمات:** {', '.join(context.user_data.get('keywords', []))}\n"
            f"💬 **الرد:** {message_text[:50]}{'...' if len(message_text) > 50 else ''}"
        )
        return
    
    # حالة 3: حفظ نص (الخطوة 2 - النص)
    elif (context.user_data.get("save_mode") == "text" and 
          context.user_data.get("save_step") == 2):
        
        keywords = context.user_data.get("keywords", [])
        
        if db.add_text_response(keywords, message_text, user.id):
            # تنظيف بيانات المستخدم
            for key in ["save_mode", "save_step", "keywords"]:
                context.user_data.pop(key, None)
            
            await update.message.reply_text(
                f"✅ **تم حفظ الرد النصي!**\n\n"
                f"🔑 **الكلمات:** {', '.join(keywords)}\n"
                f"💬 **الرد:** {message_text[:50]}{'...' if len(message_text) > 50 else ''}"
            )
        else:
            await update.message.reply_text("❌ فشل في حفظ الرد!")
        return
    
    # ========== البحث عن رد تلقائي ==========
    if ENABLE_AUTO_RESPONSE and ENABLE_TEXT_RESPONSE:
        # البحث عن رد نصي
        response = db.find_text_response(message_text, user.id)
        
        if response:
            if RESPONSE_DELAY > 0:
                await asyncio.sleep(RESPONSE_DELAY)
            await update.message.reply_text(response)

# ========== الحذف بالأرقام ==========
async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف عنصر"""
    if not await is_user_admin(update, context):
        await update.message.reply_text("⛔️ هذا الأمر للمشرفين فقط!")
        return
    
    # الحصول على جميع العناصر
    items = db.get_delete_list()
    
    if not items:
        await update.message.reply_text("📭 لا توجد عناصر للحذف!")
        return
    
    # حفظ القائمة في بيانات المستخدم
    context.user_data["delete_items"] = items
    
    # إنشاء رسالة القائمة
    list_message = "🗑️ **اختر رقم العنصر للحذف:**\n\n"
    for item in items:
        list_message += f"{item['number']}. {item['name']}\n"
    
    list_message += f"\n📝 **للحذف اكتب:**\n`/delnum <الرقم>`\nمثال: `/delnum 1`"
    
    await update.message.reply_text(list_message, parse_mode="Markdown")

async def delete_number_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف عنصر باستخدام الرقم"""
    if not await is_user_admin(update, context):
        await update.message.reply_text("⛔️ هذا الأمر للمشرفين فقط!")
        return
    
    if "delete_items" not in context.user_data:
        await update.message.reply_text("❌ استخدم /del أولاً لعرض القائمة!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ يجب تحديد رقم!\n📝 مثال: /delnum 1")
        return
    
    try:
        item_number = int(context.args[0])
        items = context.user_data["delete_items"]
        
        if 1 <= item_number <= len(items):
            item = items[item_number - 1]
            
            if db.delete_item(item["type"], item["id"], update.effective_user.id):
                # تنظيف بيانات المستخدم
                context.user_data.pop("delete_items", None)
                
                await update.message.reply_text(
                    f"✅ **تم الحذف بنجاح!**\n"
                    f"🗑️ **العنصر المحذوف:** {item['name']}"
                )
            else:
                await update.message.reply_text(f"❌ فشل في حذف العنصر رقم {item_number}")
        else:
            await update.message.reply_text(f"❌ الرقم {item_number} غير صالح!")
    
    except ValueError:
        await update.message.reply_text("❌ يجب إدخال رقم صحيح!")

# ========== أوامر إضافية ==========
async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إدارة المستخدمين"""
    if not await is_user_admin(update, context):
        await update.message.reply_text("⛔️ هذا الأمر للمشرفين فقط!")
        return
    
    users = db.users
    total_users = len(users)
    
    message = f"👥 **إدارة المستخدمين**\n\n"
    message += f"📊 إجمالي المستخدمين: {total_users}\n\n"
    
    # عرض أفضل 10 مستخدمين
    users_list = []
    for user_id, user_data in users.items():
        if isinstance(user_data, dict):
            users_list.append((user_id, user_data))
    
    users_sorted = sorted(
        users_list,
        key=lambda x: x[1].get("usage_count", 0),
        reverse=True
    )[:10]
    
    if users_sorted:
        message += "🏆 **أفضل المستخدمين:**\n"
        for i, (user_id, user_data) in enumerate(users_sorted, 1):
            name = user_data.get("first_name", "مجهول")
            username = user_data.get("username", "لا يوجد")
            usage = user_data.get("usage_count", 0)
            message += f"{i}. {name} (@{username}): {usage} استخدام\n"
    
    await update.message.reply_text(message, parse_mode="Markdown")

async def myinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معلومات المستخدم"""
    user = update.effective_user
    user_data = db.get_or_create_user(user.id, user.username, user.first_name)
    
    message = f"👤 **معلومات حسابك**\n\n"
    message += f"🆔 **المعرف:** {user.id}\n"
    message += f"👤 **الاسم:** {user_data.get('first_name', 'غير معروف')}\n"
    if user.username:
        message += f"📱 **اليوزر:** @{user.username}\n"
    message += f"📅 **تاريخ الانضمام:** {datetime.fromisoformat(user_data.get('joined_date')).strftime(DATE_FORMAT)}\n"
    message += f"🔄 **عدد الاستخدامات:** {user_data.get('usage_count', 0)}\n"
    message += f"🎨 **الملصقات المحفوظة:** {user_data.get('stickers_saved', 0)}\n"
    message += f"💬 **النصوص المحفوظة:** {user_data.get('texts_saved', 0)}\n"
    message += f"👑 **الحالة:** {'مشرف' if user_data.get('is_admin', False) else 'مستخدم عادي'}\n"
    
    await update.message.reply_text(message, parse_mode="Markdown")

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نسخ احتياطي"""
    if not await is_user_admin(update, context):
        await update.message.reply_text("⛔️ هذا الأمر للمشرفين فقط!")
        return
    
    try:
        # حفظ جميع البيانات أولاً
        db.save_all()
        
        # إنشاء نسخة احتياطية يدوية
        backup_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(BACKUP_DIR, backup_time)
        os.makedirs(backup_dir, exist_ok=True)
        
        files_to_backup = [
            (STICKERS_FILE, "stickers.json"),
            (TEXTS_FILE, "texts.json"),
            (USERS_FILE, "users.json"),
            (STATS_FILE, "stats.json")
        ]
        
        import shutil
        for source, filename in files_to_backup:
            if os.path.exists(source):
                shutil.copy2(source, os.path.join(backup_dir, filename))
        
        await update.message.reply_text(
            f"✅ **تم إنشاء نسخة احتياطية!**\n\n"
            f"📂 **المجلد:** {backup_dir}\n"
            f"🕒 **الوقت:** {datetime.now().strftime(DATE_FORMAT)}\n"
            f"📊 **الملفات:** {len(files_to_backup)} ملف"
        )
    except Exception as e:
        logger.error(f"خطأ في النسخ الاحتياطي: {e}")
        await update.message.reply_text("❌ فشل في إنشاء النسخة الاحتياطية!")

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إعدادات البوت"""
    message = f"⚙️ **إعدادات {BOT_NAME}**\n\n"
    
    message += "**📊 الحالة:**\n"
    message += f"• الرد التلقائي: {'✅ مفعل' if ENABLE_AUTO_RESPONSE else '❌ معطل'}\n"
    message += f"• ردود الملصقات: {'✅ مفعل' if ENABLE_STICKER_RESPONSE else '❌ معطل'}\n"
    message += f"• ردود النصوص: {'✅ مفعل' if ENABLE_TEXT_RESPONSE else '❌ معطل'}\n"
    message += f"• تتبع الإحصائيات: {'✅ مفعل' if TRACK_STATS else '❌ معطل'}\n\n"
    
    message += "**⚙️ الإعدادات:**\n"
    message += f"• تأخير الرد: {RESPONSE_DELAY} ثانية\n"
    message += f"• الحد الأقصى للعناصر: {MAX_LIST_ITEMS}\n"
    message += f"• نتائج البحث: {MAX_SEARCH_RESULTS}\n\n"
    
    message += "**📁 التخزين:**\n"
    stats = db.stats
    message += f"• الملصقات: {stats.get('total_stickers', 0)}\n"
    message += f"• النصوص: {stats.get('total_texts', 0)}\n"
    message += f"• المستخدمين: {stats.get('total_users', 0)}\n"
    
    await update.message.reply_text(message, parse_mode="Markdown")

# ========== معالج الاستدعاء ==========
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أزرار الإنلاين"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    # إرسال رسالة جديدة بدلاً من تعديل الرسالة القديمة
    try:
        if data == "cmd_help":
            await help_command(update, context)
        elif data == "cmd_stats":
            await stats_command(update, context)
        else:
            await query.edit_message_text("⚙️ أمر غير معروف")
    except Exception as e:
        logger.error(f"خطأ في معالج الاستدعاء: {e}")
        await query.message.reply_text("⚠️ حدث خطأ في معالجة الطلب")

# ========== معالج الأخطاء ==========
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الأخطاء العام"""
    logger.error(f"حدث خطأ: {context.error}", exc_info=True)
    
    if SHOW_ERRORS_TO_USER:
        try:
            if update and update.message:
                await update.message.reply_text("⚠️ حدث خطأ، تم تسجيله.")
        except:
            pass

# ========== الدالة الرئيسية ==========
def main():
    """تشغيل البوت"""
    print(f"🚀 بدء تشغيل {BOT_NAME} v{BOT_VERSION}")
    print(f"👤 المطور: {BOT_CREATOR}")
    print("=" * 50)
    print("⚙️ الإعدادات النشطة:")
    print(f"• الرد التلقائي: {'✅' if ENABLE_AUTO_RESPONSE else '❌'}")
    print(f"• تأخير الرد: {RESPONSE_DELAY} ثانية")
    print(f"• أزرار تفاعلية: {'✅' if ENABLE_BUTTONS else '❌'}")
    print(f"• إحصائيات: {'✅' if TRACK_STATS else '❌'}")
    print("=" * 50)
    
    # إنشاء التطبيق
    app = Application.builder().token(TOKEN).build()
    
    # إضافة معالجات الأوامر
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("ss", save_sticker_command))
    app.add_handler(CommandHandler("st", save_text_command))
    app.add_handler(CommandHandler("del", delete_command))
    app.add_handler(CommandHandler("delnum", delete_number_command))
    app.add_handler(CommandHandler("users", users_command))
    app.add_handler(CommandHandler("myinfo", myinfo_command))
    app.add_handler(CommandHandler("backup", backup_command))
    app.add_handler(CommandHandler("settings", settings_command))
    
    # إضافة معالجات الرسائل
    app.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    # إضافة معالج الاستدعاء (للأزرار)
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    # إضافة معالج الأخطاء
    app.add_error_handler(error_handler)
    
    print(f"✅ {BOT_NAME} يعمل الآن!")
    print("💡 استخدم /start للبدء")
    print("👑 استخدم /help لمعرفة الأوامر")
    
    # بدء الاستقبال
    app.run_polling(
        poll_interval=POLL_INTERVAL,
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )
    
if __name__ == "__main__":
    # إنشاء مجلد data إذا لم يكن موجوداً
    if not os.path.exists("data"):
        os.makedirs("data", exist_ok=True)
    
    # تهيئة الملفات إذا لم تكن موجودة
    for file_path in [STICKERS_FILE, TEXTS_FILE, USERS_FILE, STATS_FILE]:
        if not os.path.exists(file_path):
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump({}, f, ensure_ascii=False, indent=2)
    
    main()
