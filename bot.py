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
        
        # Create inline keyboard with quick actions
        keyboard = []
        
        if self.is_admin(user.id):
            keyboard = [
                [
                    InlineKeyboardButton("➕ افزودن پلی‌لیست", callback_data="add_playlist"),
                    InlineKeyboardButton("📋 لیست پلی‌لیست‌ها", callback_data="list_playlists")
                ],
                [
                    InlineKeyboardButton("🔄 چک و ارسال فوری", callback_data="check_now"),
                    InlineKeyboardButton("📊 آمار", callback_data="show_stats")
                ],
                [
                    InlineKeyboardButton("❌ حذف پلی‌لیست", callback_data="remove_playlist"),
                    InlineKeyboardButton("❓ راهنما", callback_data="show_help")
                ]
            ]
        else:
            keyboard = [
                [
                    InlineKeyboardButton("📋 لیست پلی‌لیست‌ها", callback_data="list_playlists"),
                    InlineKeyboardButton("📊 آمار", callback_data="show_stats")
                ],
                [
                    InlineKeyboardButton("❓ راهنما", callback_data="show_help")
                ]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_message = f"""
👋 سلام {user.first_name}!

من یک ربات مدیریت پلی‌لیست اسپاتیفای هستم.

📋 دستورات موجود:
/addplaylist - افزودن پلی‌لیست جدید
/setchannel - تنظیم چنل برای پلی‌لیست
/listplaylists - نمایش پلی‌لیست‌ها
/removeplaylist - حذف پلی‌لیست
/checkplaylists - چک دستی پلی‌لیست‌ها
/stats - آمار ربات
/help - راهنما

{'⚠️ شما دسترسی ادمین ندارید.' if not self.is_admin(user.id) else '✅ شما ادمین هستید - از دکمه‌های زیر استفاده کنید:'}
"""
        await update.message.reply_text(welcome_message, reply_markup=reply_markup)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = """
📖 راهنمای استفاده:

1️⃣ افزودن پلی‌لیست:
/addplaylist
سپس لینک پلی‌لیست و نام دلخواه را ارسال کنید.

2️⃣ تنظیم چنل برای پلی‌لیست:
/setchannel
سپس شماره پلی‌لیست و ID چنل را وارد کنید.

3️⃣ مشاهده پلی‌لیست‌ها:
/listplaylists

4️⃣ حذف پلی‌لیست:
/removeplaylist
سپس شماره پلی‌لیست را وارد کنید.

5️⃣ چک دستی:
/checkplaylists
برای چک فوری تمام پلی‌لیست‌ها

6️⃣ آمار:
/stats
برای مشاهده آمار ربات

7️⃣ تنظیم Deezer ARL:
/setuparl - راهنمای دریافت ARL
/setarl TOKEN - تنظیم ARL token

⏰ ربات هر 6 ساعت به صورت خودکار پلی‌لیست‌ها را چک می‌کند.
🎵 می‌توانید با دکمه‌های inline هر پلی‌لیست را جداگانه ارسال کنید.
"""
        await update.message.reply_text(help_text)
    
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
        
        # Check ARL status
        arl_status = "✅ فعال" if self.deezer_arl else "❌ تنظیم نشده"
        
        stats_message = f"""
📊 آمار ربات:

🎵 تعداد پلی‌لیست‌ها: {len(playlists)}
🎼 کل آهنگ‌ها: {total_tracks}
✅ آهنگ‌های ارسال شده: {total_sent}
⏰ بازه چک: 6 ساعت
🎚️ کیفیت: 128kbps
🎧 Deezer ARL: {arl_status}
"""
        await update.message.reply_text(stats_message)
    
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
                await update.message.reply_text("❌ لینک نامعتبر است. لطفا یک لینک معتبر ارسال کنید.")
                return
            
            user_data['playlist_url'] = text
            user_data['awaiting_playlist_url'] = False
            user_data['awaiting_playlist_name'] = True
            await update.message.reply_text("✅ لینک دریافت شد.\nحالا یک نام برای این پلی‌لیست وارد کنید:")
            return
        
        # Handle playlist name input
        if user_data.get('awaiting_playlist_name'):
            url = user_data.get('playlist_url')
            name = text
            
            user_data['playlist_name'] = name
            user_data['awaiting_playlist_name'] = False
            user_data['awaiting_playlist_channel'] = True
            
            await update.message.reply_text(
                f"✅ لینک و نام دریافت شد.\n"
                f"حالا ID چنل مورد نظر را ارسال کنید:\n"
                f"مثال: @channelname یا -1001234567890\n\n"
                f"یا /cancel برای لغو"
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
                await update.message.reply_text("❌ ID چنل نامعتبر است.")
                return
            
            url = user_data.get('playlist_url')
            name = user_data.get('playlist_name')
            
            if self.config_manager.add_playlist(url, name, update.effective_user.id, channel_id):
                keyboard = [[
                    InlineKeyboardButton("📤 ارسال فوری آهنگ‌های این پلی‌لیست", callback_data="send_latest_playlist")
                ]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    f"✅ پلی‌لیست '{name}' با موفقیت اضافه شد!\n"
                    f"چنل تنظیم شده: {channel_id}\n\n"
                    f"می‌خواهید الان آهنگ‌های آن را چک و ارسال کنید؟",
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_text("⚠️ این پلی‌لیست قبلا اضافه شده است.")
            
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
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        data = query.data
        
        # Check admin for restricted actions
        if data in ['add_playlist', 'remove_playlist', 'check_now'] or data.startswith('send_playlist_'):
            if not self.is_admin(user_id):
                await query.edit_message_text("⛔️ فقط ادمین‌ها می‌توانند این عملیات را انجام دهند.")
                return
        
        # Handle different callbacks
        if data == "add_playlist":
            await query.edit_message_text(
                "لطفا لینک پلی‌لیست اسپاتیفای را ارسال کنید:\n"
                "مثال: https://open.spotify.com/playlist/...\n\n"
                "یا /cancel برای لغو"
            )
            context.user_data['awaiting_playlist_url'] = True
        
        elif data == "list_playlists":
            await self.show_playlists_with_buttons(query)
        
        elif data == "remove_playlist":
            await self.handle_remove_callback(query, context)
        
        elif data == "check_now":
            await query.edit_message_text("🔄 در حال چک و ارسال تمام پلی‌لیست‌ها...")
            await self.check_all_playlists()
            await query.message.reply_text("✅ چک و ارسال تمام پلی‌لیست‌ها تکمیل شد.")
        
        elif data == "show_stats":
            await self.show_stats_callback(query)
        
        elif data == "show_help":
            await self.show_help_callback(query)
        
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
        
        stats_message = f"""
📊 آمار ربات:

🎵 تعداد پلی‌لیست‌ها: {len(playlists)}
🎼 کل آهنگ‌ها: {total_tracks}
✅ آهنگ‌های ارسال شده: {total_sent}
⏰ بازه چک: 6 ساعت
🎚️ کیفیت: 128kbps
"""
        
        keyboard = [[
            InlineKeyboardButton("🔙 بازگشت", callback_data="list_playlists")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(stats_message, reply_markup=reply_markup)
    
    async def show_help_callback(self, query):
        """Show help via callback"""
        help_text = """
📖 راهنمای استفاده:

1️⃣ افزودن پلی‌لیست:
/addplaylist یا دکمه "افزودن پلی‌لیست"

2️⃣ تنظیم چنل:
/setchannel یا دکمه "تنظیم چنل"

3️⃣ مشاهده پلی‌لیست‌ها:
/listplaylists یا دکمه "لیست پلی‌لیست‌ها"

4️⃣ ارسال فوری:
از دکمه "ارسال فوری" کنار هر پلی‌لیست

5️⃣ چک همه:
دکمه "چک و ارسال همه"

⏰ ربات هر 6 ساعت به صورت خودکار چک می‌کند.
"""
        
        keyboard = [[
            InlineKeyboardButton("🔙 بازگشت به منو", callback_data="show_main_menu")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(help_text, reply_markup=reply_markup)
    
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
                                   artist_name: str, channel_id: str) -> bool:
        """Send audio file to specified channel"""
        try:
            if not os.path.exists(file_path):
                logger.error(f"File not found: {file_path}")
                return False
            
            caption = (
                f"🎵 <b>{track_name}</b>\n"
                f"🎤 {artist_name}\n\n"
                f"#موسیقی #دانلود"
            )
            
            bot = Bot(token=self.telegram_token)
            with open(file_path, 'rb') as audio:
                await bot.send_audio(
                    chat_id=channel_id,
                    audio=audio,
                    caption=caption,
                    parse_mode='HTML',
                    title=track_name,
                    performer=artist_name
                )
            
            logger.info(f"✅ Sent: {track_name} - {artist_name} to {channel_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending file: {e}")
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
            
            # Find new tracks
            for track in tracks:
                track_id = track['id']
                if track_id not in playlist_data['tracks']:
                    new_tracks.append(track)
                    playlist_data['tracks'][track_id] = {
                        'name': track['name'],
                        'artists': track['artists'],
                        'added_at': datetime.now().isoformat(),
                        'sent': False
                    }
            
            playlist_data['total_tracks'] = len(tracks)
            self._save_tracks_db()
            
            # Update config
            self.config_manager.update_playlist_check(playlist_url, len(tracks))
            
            if new_tracks:
                logger.info(f"🎵 Found {len(new_tracks)} new tracks")
                await self.process_new_tracks(playlist_url, new_tracks)
            else:
                logger.info("✅ No new tracks")
                
        except Exception as e:
            logger.error(f"Error checking playlist: {e}", exc_info=True)
    
    async def process_new_tracks(self, playlist_url: str, tracks: List[dict]):
        """Download and send new tracks"""
        try:
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
            
            tracks_to_download = [
                (track['name'], ', '.join(track['artists']))
                for track in tracks
            ]
            
            logger.info(f"📥 Downloading {len(tracks_to_download)} tracks...")
            
            # Download tracks
            downloaded = await asyncio.to_thread(
                self.downloader.download_tracks,
                tracks_to_download,
                output_dir=self.download_dir,
                bitrate=self.config_manager.config['settings']['bitrate']
            )
            
            if not downloaded:
                logger.warning("⚠️ No tracks were downloaded")
                return
            
            logger.info(f"✅ Downloaded {len(downloaded)} tracks")
            
            # Send to channel
            playlist_data = self.tracks_db[playlist_url]
            success_count = 0
            
            # Get channel ID for this playlist
            channel_id = self.config_manager.get_playlist_channel(playlist_url)
            if not channel_id:
                logger.error(f"❌ No channel configured for playlist: {playlist_url}")
                return
            
            for track_name, artist_name, file_path in downloaded:
                if await self.send_audio_to_channel(file_path, track_name, artist_name, channel_id):
                    # Mark as sent
                    for track in tracks:
                        if track['name'] == track_name:
                            playlist_data['tracks'][track['id']]['sent'] = True
                            playlist_data['sent_tracks'] += 1
                            success_count += 1
                            break
                    
                    await asyncio.sleep(2)  # Rate limiting
                
                # Clean up downloaded file
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        logger.info(f"🗑️ Cleaned up: {file_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete file {file_path}: {e}")
            
            self._save_tracks_db()
            logger.info(f"✅ Successfully sent {success_count}/{len(downloaded)} tracks to {channel_id}")
            
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
    
    def run(self):
        """Run the bot"""
        # Create application
        app = Application.builder().token(self.telegram_token).build()
        
        # Add handlers
        app.add_handler(CommandHandler("start", self.start_command))
        app.add_handler(CommandHandler("help", self.help_command))
        app.add_handler(CommandHandler("addplaylist", self.add_playlist_command))
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