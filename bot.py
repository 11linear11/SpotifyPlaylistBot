import asyncio
import json
import os
import logging
from pathlib import Path
from typing import List, Tuple, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from telegram.error import TelegramError

from SpotifyApiCall import SpotifyAPI
from DeezerApiCall import DeemixDownloader


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class PlaylistConfig:
    """Configuration for a single playlist"""
    url: str
    name: str
    added_by: int
    added_at: str
    channel_id: str
    last_check: Optional[str] = None
    track_count: int = 0


class ConfigManager:
    """Manages bot configuration and playlists"""
    
    def __init__(self, config_file: str = 'config.json'):
        self.config_file = config_file
        self.config = self._load_config()
    
    def _load_config(self) -> dict:
        """Load configuration from file"""
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            'playlists': [],
            'settings': {
                'check_interval': 6 * 3600,
                'bitrate': '128',
                'download_dir': './downloads'
            }
        }
    
    def save_config(self):
        """Save configuration to file"""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)
    
    def add_playlist(self, url: str, name: str, user_id: int, channel_id: str) -> bool:
        """Add a new playlist"""
        if any(p['url'] == url for p in self.config['playlists']):
            return False
        
        playlist = PlaylistConfig(
            url=url,
            name=name,
            added_by=user_id,
            added_at=datetime.now().isoformat(),
            channel_id=channel_id
        )
        self.config['playlists'].append(asdict(playlist))
        self.save_config()
        return True
    
    def remove_playlist(self, url: str) -> bool:
        """Remove a playlist"""
        original_length = len(self.config['playlists'])
        self.config['playlists'] = [
            p for p in self.config['playlists'] if p['url'] != url
        ]
        if len(self.config['playlists']) < original_length:
            self.save_config()
            return True
        return False
    
    def get_playlists(self) -> List[dict]:
        """Get all playlists"""
        return self.config['playlists']
    
    def get_playlist_channel(self, url: str) -> Optional[str]:
        """Get channel ID for a playlist"""
        for playlist in self.config['playlists']:
            if playlist['url'] == url:
                return playlist['channel_id']
        return None
    
    def set_playlist_channel(self, url: str, channel_id: str) -> bool:
        """Set channel ID for a playlist"""
        for playlist in self.config['playlists']:
            if playlist['url'] == url:
                playlist['channel_id'] = channel_id
                self.save_config()
                return True
        return False
    
    def update_playlist_check(self, url: str, track_count: int) -> bool:
        """Update last check time and track count for a playlist"""
        for playlist in self.config['playlists']:
            if playlist['url'] == url:
                playlist['last_check'] = datetime.now().isoformat()
                playlist['track_count'] = track_count
                self.save_config()
                return True
        return False


class SpotifyTelegramBot:
    """Enhanced Telegram bot with playlist management"""
    
    def __init__(self):
        # Environment variables
        self.telegram_token = os.getenv('TELEGRAM_TOKEN')
        self.channel_id = os.getenv('CHANNEL_ID')
        self.spotify_client_id = os.getenv('SPOTIFY_CLIENT_ID')
        self.spotify_client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
        self.admin_ids = [int(id.strip()) for id in os.getenv('ADMIN_IDS', '').split(',') if id.strip()]
        self.deezer_arl = os.getenv('DEEZER_ARL', '')
        
        if not all([self.telegram_token, self.channel_id, 
                   self.spotify_client_id, self.spotify_client_secret]):
            raise ValueError("Missing required environment variables")
        
        # Initialize services
        self.config_manager = ConfigManager()
        self.spotify = SpotifyAPI(self.spotify_client_id, self.spotify_client_secret)
        self.downloader = DeemixDownloader()
        
        # Setup Deezer ARL if provided
        if self.deezer_arl:
            try:
                self.downloader.set_arl(self.deezer_arl)
                logger.info("✅ Deezer ARL configured from environment")
            except Exception as e:
                logger.warning(f"⚠️ Failed to setup ARL from environment: {e}")
        else:
            logger.warning("⚠️ DEEZER_ARL not set in environment. Downloads will fail until configured.")
        
        # Setup download directory
        self.download_dir = self.config_manager.config['settings']['download_dir']
        Path(self.download_dir).mkdir(parents=True, exist_ok=True)
        
        # Track database
        self.tracks_db_file = 'tracks_database.json'
        self.tracks_db = self._load_tracks_db()
        
        logger.info("🤖 Bot initialized successfully")
    
    def _load_tracks_db(self) -> dict:
        """Load tracks database"""
        if os.path.exists(self.tracks_db_file):
            with open(self.tracks_db_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def _save_tracks_db(self):
        """Save tracks database"""
        with open(self.tracks_db_file, 'w', encoding='utf-8') as f:
            json.dump(self.tracks_db, f, indent=2, ensure_ascii=False)
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return user_id in self.admin_ids
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        is_admin = self.is_admin(user.id)
        
        # Create inline keyboard with quick actions
        if is_admin:
            keyboard = [
                [
                    InlineKeyboardButton("🎵 افزودن پلی‌لیست", callback_data="add_playlist"),
                ],
                [
                    InlineKeyboardButton("📋 مشاهده پلی‌لیست‌ها", callback_data="list_playlists"),
                    InlineKeyboardButton("🔗 ارتباط چنل‌ها", callback_data="show_all_links")
                ],
                [
                    InlineKeyboardButton("🔄 چک فوری", callback_data="check_now"),
                    InlineKeyboardButton("📊 آمار و وضعیت", callback_data="show_stats")
                ],
                [
                    InlineKeyboardButton("⚙️ مدیریت", callback_data="show_management"),
                    InlineKeyboardButton("💡 راهنما", callback_data="show_help")
                ]
            ]
        else:
            keyboard = [
                [
                    InlineKeyboardButton("📋 پلی‌لیست‌ها", callback_data="list_playlists"),
                    InlineKeyboardButton("📊 آمار", callback_data="show_stats")
                ],
                [
                    InlineKeyboardButton("💡 راهنما", callback_data="show_help")
                ]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Create beautiful welcome message
        access_level = "🔐 <b>دسترسی: ادمین</b>" if is_admin else "👤 <b>دسترسی: کاربر</b>"
        
        welcome_message = f"""╭─────────────────────╮
│   🎵 ربات اسپاتیفای   │
╰─────────────────────╯

👋 سلام <b>{user.first_name}</b> عزیز!

🤖 من ربات مدیریت و اشتراک‌گذاری پلی‌لیست‌های اسپاتیفای هستم.

{access_level}

┌ 🎯 <b>قابلیت‌های من:</b>
├─ 📡 مانیتورینگ خودکار پلی‌لیست‌ها
├─ 🎼 دانلود و ارسال آهنگ‌های جدید
├─ 📺 پشتیبانی از چند چنل
└─ ⏰ بررسی هر 6 ساعت

💫 از دکمه‌های زیر برای شروع استفاده کنید:
"""
        
        # Add admin commands if user is admin
        if is_admin:
            welcome_message = welcome_message.replace(
                "💫 از دکمه‌های زیر برای شروع استفاده کنید:",
                """
┌ ⚡️ <b>دستورات سریع:</b>
├─ /addplaylist → افزودن پلی‌لیست
├─ /linkplaylist → ارتباط به چنل
├─ /showlinks → مشاهده ارتباطات
└─ /checkplaylists → چک فوری

💫 از دکمه‌های زیر برای شروع استفاده کنید:"""
            )
        
        await update.message.reply_text(
            welcome_message, 
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        is_admin = self.is_admin(update.effective_user.id)
        
        help_text = """
╭──────────────────╮
│  � راهنمای کامل  │
╰──────────────────╯

<b>📚 دستورات اصلی:</b>

🎵 <b>افزودن پلی‌لیست</b>
└─ /addplaylist
   ورودی‌ها: لینک، نام، چنل

🔗 <b>مدیریت چنل‌ها</b>
├─ /linkplaylist → تغییر چنل پلی‌لیست
├─ /showlinks → مشاهده ارتباطات
└─ /setchannel → تنظیم چنل (روش قدیم)

📋 <b>مشاهده اطلاعات</b>
├─ /listplaylists → لیست پلی‌لیست‌ها
├─ /stats → آمار کامل ربات
└─ /help → این راهنما

"""
        
        if is_admin:
            help_text += """<b>⚙️ دستورات مدیریتی:</b>

🗑 <b>حذف پلی‌لیست</b>
└─ /removeplaylist
   حذف یک پلی‌لیست

🔄 <b>چک دستی</b>
└─ /checkplaylists
   بررسی فوری همه پلی‌لیست‌ها

🎧 <b>تنظیم Deezer</b>
├─ /setuparl → راهنمای دریافت ARL
└─ /setarl [TOKEN] → ثبت توکن

"""
        
        help_text += """
┌─────────────────────
│ <b>ℹ️ اطلاعات مفید:</b>
├─ ⏰ چک خودکار هر 6 ساعت
├─ 🎼 دانلود با کیفیت 128kbps
├─ 📺 پشتیبانی چند چنل
└─ 💾 ذخیره‌سازی خودکار

<b>💬 نیاز به کمک؟</b>
از دکمه‌های منو استفاده کنید!
"""
        
        keyboard = [[
            InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_start")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            help_text, 
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    
    async def add_playlist_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /addplaylist command"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text(
                "⛔️ <b>دسترسی محدود</b>\n\n"
                "فقط ادمین‌ها می‌توانند پلی‌لیست اضافه کنند.",
                parse_mode='HTML'
            )
            return
        
        message = """
╭──────────────────────╮
│  🎵 افزودن پلی‌لیست   │
╰──────────────────────╯

<b>مرحله 1 از 3:</b> لینک پلی‌لیست

📎 لطفا لینک پلی‌لیست اسپاتیفای را ارسال کنید:

<b>مثال:</b>
<code>https://open.spotify.com/playlist/37i9dQZF1DX...</code>

💡 <i>لینک را از اپلیکیشن Spotify کپی کنید</i>

❌ برای لغو: /cancel
"""
        await update.message.reply_text(message, parse_mode='HTML')
        context.user_data['awaiting_playlist_url'] = True
    
    async def set_channel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /setchannel command"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("⛔️ فقط ادمین‌ها می‌توانند چنل تنظیم کنند.")
            return
        
        playlists = self.config_manager.get_playlists()
        if not playlists:
            await update.message.reply_text("📭 هیچ پلی‌لیستی برای تنظیم چنل وجود ندارد.")
            return
        
        message = "برای تنظیم چنل، شماره پلی‌لیست را ارسال کنید:\n\n"
        for i, playlist in enumerate(playlists, 1):
            message += f"{i}. {playlist['name']}\n"
        message += "\nیا /cancel برای لغو"
        
        await update.message.reply_text(message)
        context.user_data['awaiting_channel_playlist'] = True
    
    async def link_playlist_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /linkplaylist command - ارتباط دادن پلی‌لیست به چنل"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("⛔️ فقط ادمین‌ها می‌توانند پلی‌لیست را به چنل مرتبط کنند.")
            return
        
        playlists = self.config_manager.get_playlists()
        if not playlists:
            await update.message.reply_text("📭 هیچ پلی‌لیستی برای ارتباط با چنل وجود ندارد.")
            return
        
        # ایجاد دکمه‌های inline برای انتخاب پلی‌لیست
        keyboard = []
        for i, playlist in enumerate(playlists):
            current_channel = playlist.get('channel_id', 'تنظیم نشده')
            keyboard.append([
                InlineKeyboardButton(
                    f"🎵 {playlist['name'][:30]} (چنل: {current_channel})",
                    callback_data=f"link_playlist_{i}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("❌ انصراف", callback_data="cancel_action")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🔗 *ارتباط پلی‌لیست به چنل*\n\n"
            "لطفا پلی‌لیستی که می‌خواهید به چنل جدید مرتبط کنید را انتخاب کنید:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def show_links_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /showlinks command - نمایش ارتباط پلی‌لیست‌ها با چنل‌ها"""
        playlists = self.config_manager.get_playlists()
        
        if not playlists:
            await update.message.reply_text("📭 هیچ پلی‌لیستی ثبت نشده است.")
            return
        
        message = "🔗 *ارتباط پلی‌لیست‌ها با چنل‌ها:*\n\n"
        
        for i, playlist in enumerate(playlists, 1):
            channel_id = playlist.get('channel_id', '❌ تنظیم نشده')
            track_count = playlist.get('track_count', 0)
            last_check = playlist.get('last_check', 'هرگز')
            
            if last_check != 'هرگز':
                try:
                    last_check = datetime.fromisoformat(last_check).strftime('%Y-%m-%d %H:%M')
                except:
                    pass
            
            message += f"{i}. 🎵 *{playlist['name']}*\n"
            message += f"   📺 چنل: `{channel_id}`\n"
            message += f"   📊 تعداد آهنگ: {track_count}\n"
            message += f"   🕐 آخرین چک: {last_check}\n"
            message += f"   🔗 [لینک پلی‌لیست]({playlist['url']})\n\n"
        
        # ایجاد دکمه برای ویرایش سریع
        if self.is_admin(update.effective_user.id):
            keyboard = [[
                InlineKeyboardButton("🔗 ارتباط پلی‌لیست به چنل", callback_data="show_link_menu")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(message, parse_mode='Markdown')
    
    async def list_playlists_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /listplaylists command"""
        playlists = self.config_manager.get_playlists()
        
        if not playlists:
            await update.message.reply_text("📭 هیچ پلی‌لیستی ثبت نشده است.")
            return
        
        message = "📋 پلی‌لیست‌های ثبت شده:\n\n"
        
        # Create inline keyboard for each playlist
        keyboard = []
        
        for i, playlist in enumerate(playlists, 1):
            last_check = playlist.get('last_check', 'هرگز')
            if last_check != 'هرگز':
                last_check = datetime.fromisoformat(last_check).strftime('%Y-%m-%d %H:%M')
            
            message += f"{i}. 🎵 {playlist['name']}\n"
            message += f"   📊 تعداد آهنگ: {playlist.get('track_count', 0)}\n"
            message += f"   🕐 آخرین چک: {last_check}\n"
            message += f"   🔗 {playlist['url']}\n\n"
            
            # Add button for each playlist to send immediately
            if self.is_admin(update.effective_user.id):
                keyboard.append([
                    InlineKeyboardButton(
                        f"📤 ارسال فوری: {playlist['name'][:20]}...",
                        callback_data=f"send_playlist_{i-1}"
                    )
                ])
        
        # Add general check button
        if self.is_admin(update.effective_user.id):
            keyboard.append([
                InlineKeyboardButton("🔄 چک و ارسال همه", callback_data="check_now")
            ])
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        await update.message.reply_text(message, reply_markup=reply_markup)
    
    async def remove_playlist_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /removeplaylist command"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("⛔️ فقط ادمین‌ها می‌توانند پلی‌لیست حذف کنند.")
            return
        
        playlists = self.config_manager.get_playlists()
        if not playlists:
            await update.message.reply_text("📭 هیچ پلی‌لیستی برای حذف وجود ندارد.")
            return
        
        message = "برای حذف، شماره پلی‌لیست را ارسال کنید:\n\n"
        for i, playlist in enumerate(playlists, 1):
            message += f"{i}. {playlist['name']}\n"
        message += "\nیا /cancel برای لغو"
        
        await update.message.reply_text(message)
        context.user_data['awaiting_playlist_remove'] = True
    
    async def check_playlists_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /checkplaylists command"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("⛔️ فقط ادمین‌ها می‌توانند چک دستی انجام دهند.")
            return
        
        await update.message.reply_text("🔄 در حال چک پلی‌لیست‌ها...")
        await self.check_all_playlists()
        await update.message.reply_text("✅ چک پلی‌لیست‌ها تکمیل شد.")
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command"""
        playlists = self.config_manager.get_playlists()
        total_tracks = sum(self.tracks_db.get(p['url'], {}).get('total_tracks', 0) 
                          for p in playlists)
        total_sent = sum(self.tracks_db.get(p['url'], {}).get('sent_tracks', 0) 
                        for p in playlists)
        pending_tracks = total_tracks - total_sent
        
        # Check ARL status
        arl_status = "🟢 فعال" if self.deezer_arl else "🔴 غیرفعال"
        
        # Calculate success rate
        success_rate = (total_sent / total_tracks * 100) if total_tracks > 0 else 0
        
        # Get unique channels
        channels = set(p.get('channel_id', '') for p in playlists if p.get('channel_id'))
        
        stats_message = f"""
╭────────────────────╮
│  📊 آمار و وضعیت   │
╰────────────────────╯

<b>📈 آمار کلی:</b>
┌─────────────────────
├─ 🎵 پلی‌لیست‌ها: <b>{len(playlists)}</b>
├─ 📺 چنل‌ها: <b>{len(channels)}</b>
├─ 🎼 کل آهنگ‌ها: <b>{total_tracks}</b>
├─ ✅ ارسال شده: <b>{total_sent}</b>
├─ ⏳ در انتظار: <b>{pending_tracks}</b>
└─ 📊 نرخ موفقیت: <b>{success_rate:.1f}%</b>

<b>⚙️ تنظیمات:</b>
┌─────────────────────
├─ ⏰ بازه چک: <b>6 ساعت</b>
├─ 🎚️ کیفیت: <b>128kbps</b>
├─ 🎧 Deezer ARL: {arl_status}
└─ 🤖 وضعیت: <b>🟢 فعال</b>

<b>💡 نکته:</b> ربات به صورت خودکار
هر 6 ساعت پلی‌لیست‌ها را بررسی می‌کند.
"""
        
        keyboard = [
            [
                InlineKeyboardButton("🔄 رفرش", callback_data="show_stats"),
                InlineKeyboardButton("📋 پلی‌لیست‌ها", callback_data="list_playlists")
            ],
            [
                InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            stats_message,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    
    async def setup_arl_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /setuparl command"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("⛔️ فقط ادمین‌ها می‌توانند ARL را تنظیم کنند.")
            return
        
        help_text = """
🎧 راهنمای تنظیم Deezer ARL:

1. به https://www.deezer.com بروید و لاگین کنید
2. F12 را بزنید (Developer Tools)
3. به تب Application (Chrome) یا Storage (Firefox) بروید
4. Cookies → https://www.deezer.com را باز کنید
5. کوکی 'arl' را پیدا کنید و مقدارش را کپی کنید
6. دستور زیر را بفرستید:

/setarl YOUR_ARL_TOKEN_HERE

⚠️ توجه: این توکن محرمانه است، بعد از ارسال پیام خود را حذف کنید!
"""
        await update.message.reply_text(help_text)
    
    async def set_arl_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /setarl command"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("⛔️ فقط ادمین‌ها می‌توانند ARL را تنظیم کنند.")
            # Delete user's message for security
            try:
                await update.message.delete()
            except:
                pass
            return
        
        if not context.args:
            await update.message.reply_text(
                "❌ لطفا ARL token را بعد از دستور وارد کنید:\n"
                "/setarl YOUR_ARL_TOKEN\n\n"
                "برای راهنما: /setuparl"
            )
            return
        
        arl_token = context.args[0]
        
        # Delete the message containing ARL for security
        try:
            await update.message.delete()
        except:
            pass
        
        try:
            # Setup ARL in downloader
            self.downloader.set_arl(arl_token)
            self.deezer_arl = arl_token
            
            # Save to environment file for persistence
            env_file = '.env'
            if os.path.exists(env_file):
                with open(env_file, 'r') as f:
                    lines = f.readlines()
                
                with open(env_file, 'w') as f:
                    arl_found = False
                    for line in lines:
                        if line.startswith('DEEZER_ARL='):
                            f.write(f'DEEZER_ARL={arl_token}\n')
                            arl_found = True
                        else:
                            f.write(line)
                    
                    if not arl_found:
                        f.write(f'\nDEEZER_ARL={arl_token}\n')
            
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="✅ Deezer ARL با موفقیت تنظیم شد!\n\n"
                     "حالا می‌توانید آهنگ‌ها را دانلود کنید."
            )
            logger.info("✅ Deezer ARL configured successfully")
            
        except Exception as e:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"❌ خطا در تنظیم ARL:\n{str(e)}"
            )
            logger.error(f"Failed to setup ARL: {e}")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages"""
        user_data = context.user_data
        text = update.message.text
        
        if text == '/cancel':
            user_data.clear()
            await update.message.reply_text("❌ عملیات لغو شد.")
            return
        
        # Handle playlist URL input
        if user_data.get('awaiting_playlist_url'):
            if 'spotify.com/playlist' not in text:
                await update.message.reply_text(
                    "❌ <b>لینک نامعتبر</b>\n\n"
                    "لطفا یک لینک معتبر اسپاتیفای ارسال کنید.\n\n"
                    "<b>مثال صحیح:</b>\n"
                    "<code>https://open.spotify.com/playlist/...</code>",
                    parse_mode='HTML'
                )
                return
            
            user_data['playlist_url'] = text
            user_data['awaiting_playlist_url'] = False
            user_data['awaiting_playlist_name'] = True
            
            await update.message.reply_text(
                "✅ <b>لینک دریافت شد!</b>\n\n"
                "╭──────────────────────╮\n"
                "│  🎵 افزودن پلی‌لیست   │\n"
                "╰──────────────────────╯\n\n"
                "<b>مرحله 2 از 3:</b> نام پلی‌لیست\n\n"
                "📝 یک نام دلخواه برای این پلی‌لیست وارد کنید:\n\n"
                "<b>مثال:</b> <code>پلی‌لیست راک من</code>\n\n"
                "❌ برای لغو: /cancel",
                parse_mode='HTML'
            )
            return
        
        # Handle playlist name input
        if user_data.get('awaiting_playlist_name'):
            url = user_data.get('playlist_url')
            name = text
            
            user_data['playlist_name'] = name
            user_data['awaiting_playlist_name'] = False
            user_data['awaiting_playlist_channel'] = True
            
            await update.message.reply_text(
                "✅ <b>نام دریافت شد!</b>\n\n"
                "╭──────────────────────╮\n"
                "│  🎵 افزودن پلی‌لیست   │\n"
                "╰──────────────────────╯\n\n"
                "<b>مرحله 3 از 3:</b> چنل مقصد\n\n"
                "📺 ID چنل مورد نظر را ارسال کنید:\n\n"
                "<b>فرمت‌های مجاز:</b>\n"
                "▫️ <code>@channelname</code> (چنل عمومی)\n"
                "▫️ <code>-1001234567890</code> (چنل خصوصی)\n\n"
                "💡 ربات باید در چنل Admin باشد\n\n"
                "❌ برای لغو: /cancel",
                parse_mode='HTML'
            )
            return
        
        # Handle playlist channel input
        if user_data.get('awaiting_playlist_channel'):
            channel_id = text.strip()
            
            # Handle @username format
            if channel_id.startswith('@'):
                channel_id = channel_id[1:]  # Remove @ symbol
            
            # Basic validation
            if not channel_id or len(channel_id) < 3:
                await update.message.reply_text(
                    "❌ <b>ID چنل نامعتبر</b>\n\n"
                    "لطفا یک ID معتبر وارد کنید:\n"
                    "▫️ <code>@channelname</code>\n"
                    "▫️ <code>-1001234567890</code>",
                    parse_mode='HTML'
                )
                return
            
            url = user_data.get('playlist_url')
            name = user_data.get('playlist_name')
            
            if self.config_manager.add_playlist(url, name, update.effective_user.id, channel_id):
                keyboard = [
                    [
                        InlineKeyboardButton("📤 ارسال فوری", callback_data="send_latest_playlist")
                    ],
                    [
                        InlineKeyboardButton("📋 مشاهده پلی‌لیست‌ها", callback_data="list_playlists")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    "╭─────────────────╮\n"
                    "│  ✅ موفقیت‌آمیز!  │\n"
                    "╰─────────────────╯\n\n"
                    f"🎵 <b>پلی‌لیست:</b> {name}\n"
                    f"📺 <b>چنل:</b> <code>{channel_id}</code>\n"
                    f"📡 <b>وضعیت:</b> فعال\n\n"
                    "✨ پلی‌لیست با موفقیت اضافه شد!\n\n"
                    "💫 آهنگ‌های جدید به صورت خودکار\n"
                    "به چنل شما ارسال می‌شوند.\n\n"
                    "🔽 می‌توانید الان هم چک کنید:",
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
            else:
                await update.message.reply_text(
                    "⚠️ <b>توجه!</b>\n\n"
                    "این پلی‌لیست قبلاً اضافه شده است.\n\n"
                    "از /listplaylists برای مشاهده لیست استفاده کنید.",
                    parse_mode='HTML'
                )
            
            user_data.clear()
            return
        
        # Handle playlist removal
        if user_data.get('awaiting_playlist_remove'):
            try:
                index = int(text) - 1
                playlists = self.config_manager.get_playlists()
                
                if 0 <= index < len(playlists):
                    playlist = playlists[index]
                    if self.config_manager.remove_playlist(playlist['url']):
                        await update.message.reply_text(f"✅ پلی‌لیست '{playlist['name']}' حذف شد.")
                    else:
                        await update.message.reply_text("❌ خطا در حذف پلی‌لیست.")
                else:
                    await update.message.reply_text("❌ شماره نامعتبر است.")
            except ValueError:
                await update.message.reply_text("❌ لطفا یک عدد معتبر وارد کنید.")
            
            user_data.clear()
            return
        
        # Handle channel playlist selection
        if user_data.get('awaiting_channel_playlist'):
            try:
                index = int(text) - 1
                playlists = self.config_manager.get_playlists()
                
                if 0 <= index < len(playlists):
                    playlist = playlists[index]
                    user_data['selected_playlist_url'] = playlist['url']
                    user_data['awaiting_channel_playlist'] = False
                    user_data['awaiting_channel_id'] = True
                    
                    await update.message.reply_text(
                        f"✅ پلی‌لیست '{playlist['name']}' انتخاب شد.\n"
                        f"حالا ID چنل مورد نظر را ارسال کنید:\n"
                        f"مثال: @channelname یا -1001234567890"
                    )
                else:
                    await update.message.reply_text("❌ شماره نامعتبر است.")
            except ValueError:
                await update.message.reply_text("❌ لطفا یک عدد معتبر وارد کنید.")
            
            return
        
        # Handle channel ID input
        if user_data.get('awaiting_channel_id'):
            channel_id = text.strip()
            
            # Handle @username format
            if channel_id.startswith('@'):
                channel_id = channel_id[1:]  # Remove @ symbol
            
            # Basic validation
            if not channel_id or len(channel_id) < 3:
                await update.message.reply_text("❌ ID چنل نامعتبر است.")
                return
            
            playlist_url = user_data.get('selected_playlist_url')
            
            if self.config_manager.set_playlist_channel(playlist_url, channel_id):
                playlist_name = None
                for playlist in self.config_manager.get_playlists():
                    if playlist['url'] == playlist_url:
                        playlist_name = playlist['name']
                        break
                
                await update.message.reply_text(
                    f"✅ چنل برای پلی‌لیست '{playlist_name}' تنظیم شد: {channel_id}"
                )
            else:
                await update.message.reply_text("❌ خطا در تنظیم چنل.")
            
            user_data.clear()
            return
        
        # Handle new channel ID for link playlist command
        if user_data.get('awaiting_new_channel_id'):
            channel_id = text.strip()
            
            # Handle @username format
            if channel_id.startswith('@'):
                channel_id = channel_id[1:]  # Remove @ symbol
            
            # Basic validation
            if not channel_id or len(channel_id) < 3:
                await update.message.reply_text("❌ ID چنل نامعتبر است.")
                return
            
            playlist_url = user_data.get('selected_playlist_for_link')
            
            if self.config_manager.set_playlist_channel(playlist_url, channel_id):
                playlist_name = None
                for playlist in self.config_manager.get_playlists():
                    if playlist['url'] == playlist_url:
                        playlist_name = playlist['name']
                        break
                
                keyboard = [[
                    InlineKeyboardButton("🔗 مشاهده تمام ارتباطات", callback_data="show_all_links"),
                    InlineKeyboardButton("📤 ارسال فوری", callback_data=f"send_playlist_{self.config_manager.get_playlists().index([p for p in self.config_manager.get_playlists() if p['url'] == playlist_url][0])}")
                ]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    f"✅ چنل برای پلی‌لیست '{playlist_name}' به `{channel_id}` تغییر یافت!\n\n"
                    f"حالا آهنگ‌های جدید این پلی‌لیست به این چنل ارسال می‌شوند.",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text("❌ خطا در تنظیم چنل.")
            
            user_data.clear()
            return
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        data = query.data
        
        # Check admin for restricted actions
        if data in ['add_playlist', 'remove_playlist', 'check_now', 'show_link_menu', 'show_management'] or \
           data.startswith('send_playlist_') or data.startswith('link_playlist_'):
            if not self.is_admin(user_id):
                await query.edit_message_text(
                    "⛔️ <b>دسترسی محدود</b>\n\n"
                    "این عملیات فقط برای ادمین‌ها مجاز است.",
                    parse_mode='HTML'
                )
                return
        
        # Handle different callbacks
        if data == "back_to_start":
            # Show start menu again
            user = query.from_user
            is_admin = self.is_admin(user.id)
            
            if is_admin:
                keyboard = [
                    [
                        InlineKeyboardButton("🎵 افزودن پلی‌لیست", callback_data="add_playlist"),
                    ],
                    [
                        InlineKeyboardButton("📋 مشاهده پلی‌لیست‌ها", callback_data="list_playlists"),
                        InlineKeyboardButton("🔗 ارتباط چنل‌ها", callback_data="show_all_links")
                    ],
                    [
                        InlineKeyboardButton("🔄 چک فوری", callback_data="check_now"),
                        InlineKeyboardButton("📊 آمار و وضعیت", callback_data="show_stats")
                    ],
                    [
                        InlineKeyboardButton("⚙️ مدیریت", callback_data="show_management"),
                        InlineKeyboardButton("💡 راهنما", callback_data="show_help")
                    ]
                ]
            else:
                keyboard = [
                    [
                        InlineKeyboardButton("📋 پلی‌لیست‌ها", callback_data="list_playlists"),
                        InlineKeyboardButton("📊 آمار", callback_data="show_stats")
                    ],
                    [
                        InlineKeyboardButton("💡 راهنما", callback_data="show_help")
                    ]
                ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            welcome_message = f"""
╭─────────────────────╮
│   🎵 ربات اسپاتیفای   │
╰─────────────────────╯

👋 سلام <b>{user.first_name}</b> عزیز!

🤖 من ربات مدیریت و اشتراک‌گذاری پلی‌لیست‌های اسپاتیفای هستم.

{'🔐 <b>دسترسی: ادمین</b>' if is_admin else '👤 <b>دسترسی: کاربر</b>'}

💫 از دکمه‌های زیر برای شروع استفاده کنید:
"""
            await query.edit_message_text(
                welcome_message,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        
        elif data == "show_management":
            # Show management menu
            keyboard = [
                [
                    InlineKeyboardButton("➕ افزودن پلی‌لیست", callback_data="add_playlist"),
                    InlineKeyboardButton("🗑 حذف پلی‌لیست", callback_data="remove_playlist")
                ],
                [
                    InlineKeyboardButton("🔗 تنظیم چنل", callback_data="show_link_menu"),
                    InlineKeyboardButton("🔄 چک فوری", callback_data="check_now")
                ],
                [
                    InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "╭────────────────╮\n"
                "│  ⚙️ پنل مدیریت  │\n"
                "╰────────────────╯\n\n"
                "<b>عملیات مدیریتی:</b>\n\n"
                "▫️ افزودن پلی‌لیست جدید\n"
                "▫️ حذف پلی‌لیست\n"
                "▫️ تنظیم و تغییر چنل\n"
                "▫️ چک و ارسال فوری\n\n"
                "💡 یکی از گزینه‌های زیر را انتخاب کنید:",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        
        elif data == "add_playlist":
            message = """
╭──────────────────────╮
│  🎵 افزودن پلی‌لیست   │
╰──────────────────────╯

<b>مرحله 1 از 3:</b> لینک پلی‌لیست

📎 لطفا لینک پلی‌لیست اسپاتیفای را ارسال کنید:

<b>مثال:</b>
<code>https://open.spotify.com/playlist/37i9dQZF1DX...</code>

💡 <i>لینک را از اپلیکیشن Spotify کپی کنید</i>

❌ برای لغو: /cancel
"""
            await query.edit_message_text(message, parse_mode='HTML')
            context.user_data['awaiting_playlist_url'] = True
        
        elif data == "list_playlists":
            await self.show_playlists_with_buttons(query)
        
        elif data == "remove_playlist":
            await self.handle_remove_callback(query, context)
        
        elif data == "check_now":
            await query.edit_message_text(
                "🔄 <b>در حال بررسی پلی‌لیست‌ها...</b>\n\n"
                "لطفا صبر کنید، این کار ممکن است چند دقیقه طول بکشد.",
                parse_mode='HTML'
            )
            await self.check_all_playlists()
            
            keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.message.reply_text(
                "✅ <b>چک تکمیل شد!</b>\n\n"
                "تمام پلی‌لیست‌ها بررسی شدند و آهنگ‌های جدید ارسال شدند.",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        
        elif data == "show_stats":
            await self.show_stats_callback(query)
        
        elif data == "show_help":
            await self.show_help_callback(query)
        
        elif data == "show_link_menu":
            # نمایش منوی ارتباط پلی‌لیست به چنل
            await self.show_link_menu_callback(query, context)
        
        elif data.startswith("link_playlist_"):
            # کاربر یک پلی‌لیست را برای ارتباط انتخاب کرد
            playlist_index = int(data.split("_")[-1])
            await self.handle_link_playlist_selection(query, context, playlist_index)
        
        elif data == "cancel_action":
            await query.edit_message_text("❌ عملیات لغو شد.")
            context.user_data.clear()
        
        elif data == "show_all_links":
            # نمایش تمام ارتباطات پلی‌لیست‌ها با چنل‌ها
            await self.show_all_links_callback(query)
        
        elif data.startswith("send_playlist_"):
            # Send specific playlist immediately
            playlist_index = int(data.split("_")[-1])
            await self.send_specific_playlist(query, playlist_index)
        
        elif data == "send_latest_playlist":
            # Send the last added playlist
            playlists = self.config_manager.get_playlists()
            if playlists:
                await query.edit_message_text("🔄 در حال چک و ارسال پلی‌لیست جدید...")
                await self.check_playlist(playlists[-1]['url'])
                await query.message.reply_text("✅ پلی‌لیست جدید چک و ارسال شد.")
    
    async def show_playlists_with_buttons(self, query):
        """Show playlists with inline buttons"""
        playlists = self.config_manager.get_playlists()
        
        if not playlists:
            await query.edit_message_text("📭 هیچ پلی‌لیستی ثبت نشده است.")
            return
        
        message = "📋 پلی‌لیست‌های ثبت شده:\n\n"
        keyboard = []
        
        for i, playlist in enumerate(playlists, 1):
            last_check = playlist.get('last_check', 'هرگز')
            if last_check != 'هرگز':
                last_check = datetime.fromisoformat(last_check).strftime('%Y-%m-%d %H:%M')
            
            message += f"{i}. 🎵 {playlist['name']}\n"
            message += f"   📊 تعداد آهنگ: {playlist.get('track_count', 0)}\n"
            message += f"   🕐 آخرین چک: {last_check}\n\n"
            
            # Add send button for each playlist
            keyboard.append([
                InlineKeyboardButton(
                    f"📤 ارسال: {playlist['name'][:20]}...",
                    callback_data=f"send_playlist_{i-1}"
                )
            ])
        
        # Add check all button
        keyboard.append([
            InlineKeyboardButton("🔄 چک و ارسال همه", callback_data="check_now")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup)
    
    async def handle_remove_callback(self, query, context):
        """Handle remove playlist callback"""
        playlists = self.config_manager.get_playlists()
        if not playlists:
            await query.edit_message_text("📭 هیچ پلی‌لیستی برای حذف وجود ندارد.")
            return
        
        message = "برای حذف، شماره پلی‌لیست را ارسال کنید:\n\n"
        for i, playlist in enumerate(playlists, 1):
            message += f"{i}. {playlist['name']}\n"
        message += "\nیا /cancel برای لغو"
        
        await query.edit_message_text(message)
        context.user_data['awaiting_playlist_remove'] = True
    
    async def show_stats_callback(self, query):
        """Show statistics via callback"""
        playlists = self.config_manager.get_playlists()
        total_tracks = sum(self.tracks_db.get(p['url'], {}).get('total_tracks', 0) 
                          for p in playlists)
        total_sent = sum(self.tracks_db.get(p['url'], {}).get('sent_tracks', 0) 
                        for p in playlists)
        pending_tracks = total_tracks - total_sent
        
        # Check ARL status
        arl_status = "🟢 فعال" if self.deezer_arl else "🔴 غیرفعال"
        
        # Calculate success rate
        success_rate = (total_sent / total_tracks * 100) if total_tracks > 0 else 0
        
        # Get unique channels
        channels = set(p.get('channel_id', '') for p in playlists if p.get('channel_id'))
        
        stats_message = f"""
╭────────────────────╮
│  📊 آمار و وضعیت   │
╰────────────────────╯

<b>📈 آمار کلی:</b>
┌─────────────────────
├─ 🎵 پلی‌لیست‌ها: <b>{len(playlists)}</b>
├─ 📺 چنل‌ها: <b>{len(channels)}</b>
├─ 🎼 کل آهنگ‌ها: <b>{total_tracks}</b>
├─ ✅ ارسال شده: <b>{total_sent}</b>
├─ ⏳ در انتظار: <b>{pending_tracks}</b>
└─ 📊 نرخ موفقیت: <b>{success_rate:.1f}%</b>

<b>⚙️ تنظیمات:</b>
┌─────────────────────
├─ ⏰ بازه چک: <b>6 ساعت</b>
├─ 🎚️ کیفیت: <b>128kbps</b>
├─ 🎧 Deezer ARL: {arl_status}
└─ 🤖 وضعیت: <b>🟢 فعال</b>

<b>💡 نکته:</b> ربات به صورت خودکار
هر 6 ساعت پلی‌لیست‌ها را بررسی می‌کند.
"""
        
        keyboard = [
            [
                InlineKeyboardButton("� رفرش", callback_data="show_stats"),
                InlineKeyboardButton("📋 پلی‌لیست‌ها", callback_data="list_playlists")
            ],
            [
                InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            stats_message,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    
    async def show_help_callback(self, query):
        """Show help via callback"""
        is_admin = self.is_admin(query.from_user.id)
        
        help_text = """
╭──────────────────╮
│  � راهنمای کامل  │
╰──────────────────╯

<b>📚 دستورات اصلی:</b>

🎵 <b>افزودن پلی‌لیست</b>
└─ /addplaylist
   ورودی‌ها: لینک، نام، چنل

🔗 <b>مدیریت چنل‌ها</b>
├─ /linkplaylist → تغییر چنل
├─ /showlinks → مشاهده ارتباطات
└─ /setchannel → تنظیم چنل

📋 <b>مشاهده اطلاعات</b>
├─ /listplaylists → لیست پلی‌لیست‌ها
├─ /stats → آمار کامل
└─ /help → این راهنما

"""
        
        if is_admin:
            help_text += """<b>⚙️ دستورات مدیریتی:</b>

🗑 <b>حذف</b> → /removeplaylist
🔄 <b>چک فوری</b> → /checkplaylists
🎧 <b>تنظیم ARL</b> → /setuparl

"""
        
        help_text += """
┌─────────────────────
│ <b>ℹ️ اطلاعات:</b>
├─ ⏰ چک خودکار هر 6 ساعت
├─ 🎼 کیفیت 128kbps
├─ 📺 پشتیبانی چند چنل
└─ 💾 ذخیره خودکار

💬 از دکمه‌های منو استفاده کنید!
"""
        
        keyboard = [[
            InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_start")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            help_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    
    async def show_link_menu_callback(self, query, context):
        """نمایش منوی ارتباط پلی‌لیست به چنل"""
        playlists = self.config_manager.get_playlists()
        
        if not playlists:
            await query.edit_message_text("📭 هیچ پلی‌لیستی برای ارتباط با چنل وجود ندارد.")
            return
        
        # ایجاد دکمه‌های inline برای انتخاب پلی‌لیست
        keyboard = []
        for i, playlist in enumerate(playlists):
            current_channel = playlist.get('channel_id', 'تنظیم نشده')
            keyboard.append([
                InlineKeyboardButton(
                    f"🎵 {playlist['name'][:30]} (چنل: {current_channel})",
                    callback_data=f"link_playlist_{i}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("❌ انصراف", callback_data="cancel_action")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🔗 *ارتباط پلی‌لیست به چنل*\n\n"
            "لطفا پلی‌لیستی که می‌خواهید به چنل جدید مرتبط کنید را انتخاب کنید:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def handle_link_playlist_selection(self, query, context, playlist_index: int):
        """مدیریت انتخاب پلی‌لیست برای ارتباط به چنل"""
        playlists = self.config_manager.get_playlists()
        
        if 0 <= playlist_index < len(playlists):
            playlist = playlists[playlist_index]
            current_channel = playlist.get('channel_id', 'تنظیم نشده')
            
            context.user_data['selected_playlist_for_link'] = playlist['url']
            context.user_data['awaiting_new_channel_id'] = True
            
            await query.edit_message_text(
                f"🎵 پلی‌لیست انتخاب شده: *{playlist['name']}*\n"
                f"📺 چنل فعلی: `{current_channel}`\n\n"
                f"لطفا ID چنل جدید را ارسال کنید:\n"
                f"مثال: @channelname یا -1001234567890\n\n"
                f"یا /cancel برای لغو",
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text("❌ پلی‌لیست یافت نشد.")
    
    async def show_all_links_callback(self, query):
        """نمایش تمام ارتباطات پلی‌لیست‌ها با چنل‌ها"""
        playlists = self.config_manager.get_playlists()
        
        if not playlists:
            await query.edit_message_text("📭 هیچ پلی‌لیستی ثبت نشده است.")
            return
        
        message = "🔗 *ارتباط پلی‌لیست‌ها با چنل‌ها:*\n\n"
        
        for i, playlist in enumerate(playlists, 1):
            channel_id = playlist.get('channel_id', '❌ تنظیم نشده')
            track_count = playlist.get('track_count', 0)
            last_check = playlist.get('last_check', 'هرگز')
            
            if last_check != 'هرگز':
                try:
                    last_check = datetime.fromisoformat(last_check).strftime('%Y-%m-%d %H:%M')
                except:
                    pass
            
            message += f"{i}. 🎵 *{playlist['name']}*\n"
            message += f"   📺 چنل: `{channel_id}`\n"
            message += f"   📊 تعداد آهنگ: {track_count}\n"
            message += f"   🕐 آخرین چک: {last_check}\n\n"
        
        keyboard = [[
            InlineKeyboardButton("🔗 تغییر ارتباط", callback_data="show_link_menu"),
            InlineKeyboardButton("🔙 بازگشت", callback_data="list_playlists")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def send_specific_playlist(self, query, playlist_index: int):
        """Send specific playlist immediately"""
        playlists = self.config_manager.get_playlists()
        
        if 0 <= playlist_index < len(playlists):
            playlist = playlists[playlist_index]
            await query.edit_message_text(f"🔄 در حال چک و ارسال پلی‌لیست '{playlist['name']}'...")
            
            await self.check_playlist(playlist['url'])
            
            await query.message.reply_text(
                f"✅ پلی‌لیست '{playlist['name']}' چک شد و آهنگ‌های جدید ارسال شدند."
            )
        else:
            await query.edit_message_text("❌ پلی‌لیست یافت نشد.")
    
    async def send_audio_to_channel(self, file_path: str, track_name: str, 
                                   artist_name: str, channel_id: str, 
                                   max_retries: int = 3, timeout: int = 120) -> bool:
        """Send audio file to specified channel with retry mechanism"""
        
        if not os.path.exists(file_path):
            logger.error(f"❌ File not found: {file_path}")
            return False
        
        # Get file size for logging
        file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
        logger.info(f"📦 File size: {file_size:.2f} MB")
        
        caption = (
            f"🎵 <b>{track_name}</b>\n"
            f"🎤 {artist_name}\n\n"
            f"#موسیقی #دانلود"
        )
        
        bot = Bot(token=self.telegram_token)
        
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"📤 Attempt {attempt}/{max_retries}: Sending {track_name}")
                
                with open(file_path, 'rb') as audio:
                    # Set timeout for send operation
                    await asyncio.wait_for(
                        bot.send_audio(
                            chat_id=channel_id,
                            audio=audio,
                            caption=caption,
                            parse_mode='HTML',
                            title=track_name,
                            performer=artist_name,
                            read_timeout=timeout,
                            write_timeout=timeout,
                            connect_timeout=30,
                            pool_timeout=30
                        ),
                        timeout=timeout + 30  # Total timeout
                    )
                
                logger.info(f"✅ Successfully sent: {track_name} - {artist_name} to {channel_id}")
                return True
                
            except asyncio.TimeoutError:
                logger.warning(f"⏱️ Timeout on attempt {attempt}/{max_retries} for {track_name}")
                if attempt < max_retries:
                    wait_time = attempt * 5  # Exponential backoff
                    logger.info(f"⏳ Waiting {wait_time}s before retry...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"❌ Failed after {max_retries} attempts (timeout): {track_name}")
                    return False
                    
            except TelegramError as e:
                error_msg = str(e)
                logger.error(f"⚠️ Telegram error on attempt {attempt}/{max_retries}: {error_msg}")
                
                # Handle specific Telegram errors
                if "file is too big" in error_msg.lower():
                    logger.error(f"❌ File too large: {track_name} ({file_size:.2f} MB)")
                    return False
                elif "chat not found" in error_msg.lower() or "channel" in error_msg.lower():
                    logger.error(f"❌ Channel not found or bot not admin: {channel_id}")
                    return False
                elif "flood" in error_msg.lower() or "too many requests" in error_msg.lower():
                    # Rate limiting
                    wait_time = 60 * attempt  # Wait longer for rate limits
                    logger.warning(f"🚫 Rate limited. Waiting {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    if attempt == max_retries:
                        return False
                else:
                    # Other Telegram errors - retry
                    if attempt < max_retries:
                        wait_time = attempt * 10
                        logger.info(f"⏳ Retrying in {wait_time}s...")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"❌ Failed after {max_retries} attempts: {track_name}")
                        return False
                        
            except Exception as e:
                logger.error(f"❌ Unexpected error on attempt {attempt}/{max_retries}: {type(e).__name__}: {e}")
                if attempt < max_retries:
                    wait_time = attempt * 5
                    logger.info(f"⏳ Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"❌ Failed after {max_retries} attempts: {track_name}")
                    return False
        
        return False
    
    async def check_playlist(self, playlist_url: str):
        """Check a single playlist for new tracks"""
        try:
            logger.info(f"🔍 Checking playlist: {playlist_url}")
            
            # Get tracks from Spotify
            tracks = await asyncio.to_thread(
                self.spotify.get_playlist_tracks,
                playlist_url
            )
            
            if not tracks:
                logger.warning(f"No tracks found for {playlist_url}")
                return
            
            # Initialize playlist in DB if not exists
            if playlist_url not in self.tracks_db:
                self.tracks_db[playlist_url] = {
                    'tracks': {},
                    'total_tracks': 0,
                    'sent_tracks': 0
                }
            
            playlist_data = self.tracks_db[playlist_url]
            new_tracks = []
            unsent_tracks = []
            
            # Find new tracks and unsent tracks
            for track in tracks:
                track_id = track['id']
                if track_id not in playlist_data['tracks']:
                    # This is a completely new track
                    new_tracks.append(track)
                    playlist_data['tracks'][track_id] = {
                        'name': track['name'],
                        'artists': track['artists'],
                        'added_at': datetime.now().isoformat(),
                        'sent': False
                    }
                elif not playlist_data['tracks'][track_id].get('sent', False):
                    # This track exists but hasn't been sent yet
                    unsent_tracks.append(track)
            
            playlist_data['total_tracks'] = len(tracks)
            self._save_tracks_db()
            
            # Update config
            self.config_manager.update_playlist_check(playlist_url, len(tracks))
            
            # Combine new and unsent tracks
            tracks_to_process = new_tracks + unsent_tracks
            
            if tracks_to_process:
                if new_tracks:
                    logger.info(f"🎵 Found {len(new_tracks)} new tracks")
                if unsent_tracks:
                    logger.info(f"📤 Found {len(unsent_tracks)} unsent tracks")
                await self.process_new_tracks(playlist_url, tracks_to_process)
            else:
                logger.info("✅ No new or unsent tracks")
                
        except Exception as e:
            logger.error(f"Error checking playlist: {e}", exc_info=True)
    
    async def process_new_tracks(self, playlist_url: str, tracks: List[dict]):
        """Download and send new tracks"""
        try:
            logger.info(f"🎬 Processing {len(tracks)} tracks for {playlist_url}")
            
            # Check if ARL is configured
            if not self.deezer_arl:
                logger.error("❌ Deezer ARL not configured!")
                # Notify admin
                for admin_id in self.admin_ids:
                    try:
                        bot = Bot(token=self.telegram_token)
                        await bot.send_message(
                            chat_id=admin_id,
                            text="❌ خطا: Deezer ARL تنظیم نشده است!\n\n"
                                 "برای تنظیم از دستور /setuparl استفاده کنید."
                        )
                    except:
                        pass
                return
            
            # Get channel ID for this playlist
            channel_id = self.config_manager.get_playlist_channel(playlist_url)
            if not channel_id:
                logger.error(f"❌ No channel configured for playlist: {playlist_url}")
                # Notify admin
                for admin_id in self.admin_ids:
                    try:
                        bot = Bot(token=self.telegram_token)
                        await bot.send_message(
                            chat_id=admin_id,
                            text=f"❌ خطا: چنلی برای این پلی‌لیست تنظیم نشده است!\n\n"
                                 f"URL: {playlist_url}\n\n"
                                 f"از دستور /linkplaylist برای تنظیم چنل استفاده کنید."
                        )
                    except:
                        pass
                return
            
            logger.info(f"📺 Target channel: {channel_id}")
            
            tracks_to_download = [
                (track['name'], ', '.join(track['artists']))
                for track in tracks
            ]
            
            logger.info(f"📥 Downloading {len(tracks_to_download)} tracks...")
            logger.info(f"📋 Tracks to download: {[t[0] for t in tracks_to_download]}")
            
            # Download tracks
            downloaded = await asyncio.to_thread(
                self.downloader.download_tracks,
                tracks_to_download,
                output_dir=self.download_dir,
                bitrate=self.config_manager.config['settings']['bitrate']
            )
            
            if not downloaded:
                logger.warning("⚠️ No tracks were downloaded")
                logger.warning("⚠️ This might be due to Deezer download issues or ARL problems")
                return
            
            logger.info(f"✅ Downloaded {len(downloaded)} tracks: {[t[0] for t in downloaded]}")
            
            # Send to channel
            playlist_data = self.tracks_db[playlist_url]
            success_count = 0
            failed_count = 0
            failed_tracks = []
            
            logger.info(f"📤 Starting to send {len(downloaded)} tracks to channel {channel_id}...")
            
            for track_name, artist_name, file_path in downloaded:
                logger.info(f"📤 Sending: {track_name} - {artist_name}")
                logger.info(f"📁 File path: {file_path}")
                
                # Try to send with retry mechanism
                send_success = await self.send_audio_to_channel(
                    file_path, track_name, artist_name, channel_id
                )
                
                if send_success:
                    # Mark as sent
                    for track in tracks:
                        if track['name'] == track_name:
                            playlist_data['tracks'][track['id']]['sent'] = True
                            playlist_data['sent_tracks'] += 1
                            success_count += 1
                            logger.info(f"✅ Marked as sent: {track_name}")
                            break
                    
                    # Rate limiting between successful sends
                    await asyncio.sleep(3)
                else:
                    failed_count += 1
                    failed_tracks.append(f"{track_name} - {artist_name}")
                    logger.error(f"❌ Failed to send after all retries: {track_name}")
                    
                    # Still wait a bit before next track
                    await asyncio.sleep(5)
                
                # Clean up downloaded file
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        logger.info(f"🗑️ Cleaned up: {file_path}")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to delete file {file_path}: {e}")
            
            # Save database
            self._save_tracks_db()
            
            # Log summary
            logger.info(f"📊 Summary: {success_count} succeeded, {failed_count} failed out of {len(downloaded)} tracks")
            
            if success_count > 0:
                logger.info(f"✅ Successfully sent {success_count} tracks to {channel_id}")
            
            # Notify admin about failures if any
            if failed_count > 0:
                logger.error(f"❌ Failed to send {failed_count} tracks")
                error_message = (
                    f"⚠️ گزارش ارسال آهنگ‌ها:\n\n"
                    f"✅ موفق: {success_count}\n"
                    f"❌ ناموفق: {failed_count}\n\n"
                    f"آهنگ‌های ناموفق:\n"
                )
                for track in failed_tracks[:5]:  # Only show first 5
                    error_message += f"• {track}\n"
                
                if len(failed_tracks) > 5:
                    error_message += f"\n... و {len(failed_tracks) - 5} آهنگ دیگر"
                
                for admin_id in self.admin_ids:
                    try:
                        bot = Bot(token=self.telegram_token)
                        await bot.send_message(
                            chat_id=admin_id,
                            text=error_message
                        )
                    except Exception as notify_error:
                        logger.error(f"Failed to notify admin {admin_id}: {notify_error}")
            
        except Exception as e:
            logger.error(f"Error processing tracks: {e}", exc_info=True)
            # Notify admin of error
            for admin_id in self.admin_ids:
                try:
                    bot = Bot(token=self.telegram_token)
                    await bot.send_message(
                        chat_id=admin_id,
                        text=f"❌ خطا در پردازش آهنگ‌ها:\n{str(e)}"
                    )
                except:
                    pass
    
    async def check_all_playlists(self):
        """Check all playlists for new tracks"""
        playlists = self.config_manager.get_playlists()
        
        if not playlists:
            logger.info("No playlists to check")
            return
        
        logger.info(f"🔄 Checking {len(playlists)} playlists...")
        
        for playlist in playlists:
            await self.check_playlist(playlist['url'])
            await asyncio.sleep(5)  # Delay between playlists
    
    async def periodic_check(self):
        """Periodic playlist checking"""
        while True:
            try:
                await self.check_all_playlists()
                
                check_interval = self.config_manager.config['settings']['check_interval']
                logger.info(f"⏰ Next check in {check_interval // 3600} hours")
                await asyncio.sleep(check_interval)
                
            except Exception as e:
                logger.error(f"Error in periodic check: {e}", exc_info=True)
                await asyncio.sleep(3600)  # Retry in 1 hour
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Global error handler"""
        try:
            logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
            
            # Get error details
            error_message = str(context.error)
            error_type = type(context.error).__name__
            
            # Notify user if possible
            if update and update.effective_message:
                try:
                    await update.effective_message.reply_text(
                        "❌ متأسفانه خطایی رخ داد. لطفا دوباره تلاش کنید.\n\n"
                        "در صورت تکرار، به ادمین اطلاع دهید."
                    )
                except:
                    pass
            
            # Notify admin for critical errors
            critical_errors = [
                'NetworkError', 'TimedOut', 'RetryAfter', 
                'Conflict', 'Unauthorized'
            ]
            
            if error_type in critical_errors:
                for admin_id in self.admin_ids:
                    try:
                        bot = Bot(token=self.telegram_token)
                        await bot.send_message(
                            chat_id=admin_id,
                            text=f"🚨 خطای حیاتی:\n\n"
                                 f"نوع: {error_type}\n"
                                 f"پیام: {error_message[:200]}"
                        )
                    except:
                        pass
                        
        except Exception as e:
            logger.error(f"Error in error handler: {e}", exc_info=True)
    
    def run(self):
        """Run the bot"""
        # Create application
        app = Application.builder().token(self.telegram_token).build()
        
        # Add error handler
        app.add_error_handler(self.error_handler)
        
        # Add handlers
        app.add_handler(CommandHandler("start", self.start_command))
        app.add_handler(CommandHandler("help", self.help_command))
        app.add_handler(CommandHandler("addplaylist", self.add_playlist_command))
        app.add_handler(CommandHandler("linkplaylist", self.link_playlist_command))
        app.add_handler(CommandHandler("showlinks", self.show_links_command))
        app.add_handler(CommandHandler("setchannel", self.set_channel_command))
        app.add_handler(CommandHandler("listplaylists", self.list_playlists_command))
        app.add_handler(CommandHandler("removeplaylist", self.remove_playlist_command))
        app.add_handler(CommandHandler("checkplaylists", self.check_playlists_command))
        app.add_handler(CommandHandler("stats", self.stats_command))
        app.add_handler(CommandHandler("setuparl", self.setup_arl_command))
        app.add_handler(CommandHandler("setarl", self.set_arl_command))
        app.add_handler(CallbackQueryHandler(self.button_callback))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        # Start periodic check
        app.job_queue.run_once(lambda _: asyncio.create_task(self.periodic_check()), 10)
        
        # Run bot
        logger.info("🚀 Bot is running...")
        app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    try:
        bot = SpotifyTelegramBot()
        bot.run()
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)