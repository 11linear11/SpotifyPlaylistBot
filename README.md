# 🎵 Spotify to Telegram Music Bot

A powerful Telegram bot that monitors Spotify playlists and automatically downloads and shares new tracks to your Telegram channel.

## ✨ Features

- 🎼 **Multiple Playlist Support**: Monitor multiple Spotify playlists simultaneously
- 📺 **Channel Mapping**: Link each playlist to a specific Telegram channel
- 🔗 **Flexible Channel Management**: Easily change which channel receives tracks from which playlist
- 🤖 **Bot Management**: Add/remove playlists directly through Telegram commands
- ⏰ **Automatic Monitoring**: Checks for new tracks every 6 hours
- 📤 **Auto-Upload**: Automatically downloads and sends new tracks to designated channels
- 🔐 **Admin Control**: Secure admin-only access to bot commands
- 🐳 **Fully Dockerized**: Easy deployment with Docker Compose
- 📊 **Statistics**: Track playlist stats and bot performance
- 💾 **Persistent Storage**: All data saved and maintained across restarts

## 🏗️ Architecture

```
┌─────────────┐      ┌──────────────┐      ┌─────────────────┐
│   Spotify   │─────▶│  Docker Bot  │─────▶│  Telegram       │
│  Playlists  │      │   + Deemix   │      │  Channels       │
│  Playlist A │      │              │      │  → Channel 1    │
│  Playlist B │      │              │      │  → Channel 2    │
│  Playlist C │      │              │      │  → Channel 3    │
└─────────────┘      └──────────────┘      └─────────────────┘
```

## 📋 Prerequisites

- Docker and Docker Compose installed
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- Telegram Channel(s) (make bot admin in each)
- Spotify API credentials (from [Spotify Developer Dashboard](https://developer.spotify.com/dashboard))
- Deezer account (free account works, but limited to 128kbps)

## 🚀 Quick Start

### 1. Clone the Repository

```bash
git clone <your-repo-url>
cd spotify-telegram-bot
```

### 2. Configure Environment Variables

```bash
cp .env.example .env
nano .env  # Edit with your credentials
```

Required environment variables:

```bash
# Get from @BotFather
TELEGRAM_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz

# Your channel ID (use @userinfobot, forward a message from channel)
CHANNEL_ID=-1001234567890

# Get from https://developer.spotify.com/dashboard
SPOTIFY_CLIENT_ID=your_client_id_here
SPOTIFY_CLIENT_SECRET=your_client_secret_here

# Your Telegram user ID (from @userinfobot)
ADMIN_IDS=123456789,987654321

# Optional: Deezer ARL (can configure later via bot)
DEEZER_ARL=
```

### 3. Get Your Deezer ARL Token

The bot needs a Deezer ARL token to download music. You can:

**Option A: Add to .env before starting**
1. Go to https://www.deezer.com and login
2. Press F12 → Application/Storage → Cookies → deezer.com
3. Find `arl` cookie and copy its value
4. Add to `.env`: `DEEZER_ARL=your_arl_token_here`

**Option B: Configure after starting (easier)**
1. Start the bot without ARL
2. Message the bot and follow setup instructions

### 4. Build and Run

```bash
# Build and start the bot
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the bot
docker-compose down
```

### 5. Setup Deezer ARL (if not in .env)

If you didn't add ARL to .env:

1. The bot will detect missing ARL on first download attempt
2. Follow the instructions in bot logs
3. Or manually create `/root/.config/deemix/.arl` file in container

## 🎮 Bot Commands

### User Commands

- `/start` - Welcome message and bot info
- `/help` - Display help and usage instructions
- `/listplaylists` - Show all monitored playlists
- `/showlinks` - Display playlist-to-channel mappings
- `/stats` - View bot statistics

### Admin Commands

- `/addplaylist` - Add a new Spotify playlist to monitor
- `/linkplaylist` - Link a playlist to a specific channel
- `/setchannel` - Set channel for a playlist (legacy method)
- `/removeplaylist` - Remove a playlist from monitoring
- `/checkplaylists` - Manually trigger playlist check (bypass 6-hour timer)
- `/setuparl` - Show instructions for getting Deezer ARL
- `/setarl` - Set Deezer ARL token

## 📖 Usage Guide

### Adding a Playlist

1. Send `/addplaylist` to the bot
2. Send the Spotify playlist URL:
   ```
   https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M
   ```
3. Send a friendly name for the playlist:
   ```
   My Favorite Mix
   ```
4. Send the channel ID where tracks should be posted:
   ```
   @mymusicchannel
   ```
   or
   ```
   -1001234567890
   ```
5. Bot will confirm and start monitoring!

### Linking Playlist to Channel

You can link different playlists to different channels:

1. Send `/linkplaylist` to the bot
2. Select the playlist from the interactive menu
3. Send the new channel ID:
   ```
   @mynewchannel
   ```
4. Bot will update the mapping and confirm!

### Viewing Playlist-Channel Mappings

Send `/showlinks` to see which playlist sends to which channel:

```
🔗 ارتباط پلی‌لیست‌ها با چنل‌ها:

1. 🎵 My Favorite Mix
   📺 چنل: @mymusicchannel
   📊 تعداد آهنگ: 50
   🕐 آخرین چک: 2025-01-15 14:30
   🔗 [لینک پلی‌لیست](https://open.spotify.com/playlist/...)

2. 🎵 Chill Vibes
   📺 چنل: @chillchannel
   📊 تعداد آهنگ: 32
   🕐 آخرین چک: 2025-01-15 14:32
   🔗 [لینک پلی‌لیست](https://open.spotify.com/playlist/...)
```

### Viewing Playlists

Send `/listplaylists` to see all monitored playlists:

```
📋 پلی‌لیست‌های ثبت شده:

1. 🎵 My Favorite Mix
   📊 تعداد آهنگ: 50
   🕐 آخرین چک: 2025-01-15 14:30
   🔗 https://open.spotify.com/playlist/...

2. 🎵 Chill Vibes
   📊 تعداد آهنگ: 32
   🕐 آخرین چک: 2025-01-15 14:32
   🔗 https://open.spotify.com/playlist/...
```

### Removing a Playlist

1. Send `/removeplaylist`
2. Bot shows numbered list of playlists
3. Reply with the number of playlist to remove

## 🐳 Docker Management

### View Logs
```bash
docker-compose logs -f
```

### Restart Bot
```bash
docker-compose restart
```

### Update Bot
```bash
git pull
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Backup Data
```bash
# Backup all persistent data
tar -czf backup-$(date +%Y%m%d).tar.gz data/ downloads/ deemix-config/
```

### Clean Everything
```bash
docker-compose down -v
rm -rf data/ downloads/ deemix-config/
```

## 📁 Directory Structure

```
.
├── bot.py                    # Main bot application
├── SpotifyApiCall.py         # Spotify API wrapper
├── DeezerApiCall.py          # Deezer/Deemix wrapper
├── requirements.txt          # Python dependencies
├── Dockerfile                # Docker image definition
├── docker-compose.yml        # Docker Compose configuration
├── .env                      # Environment variables (create from .env.example)
├── .env.example              # Environment variables template
├── data/                     # Persistent bot data
│   ├── config.json          # Playlists configuration
│   └── tracks_database.json # Tracks database
├── downloads/                # Downloaded music files
└── deemix-config/           # Deemix configuration
    └── .arl                 # Deezer authentication token
```

## ⚙️ Configuration

### Change Check Interval

Edit `data/config.json`:

```json
{
  "settings": {
    "check_interval": 21600,  // 6 hours in seconds (change as needed)
    "bitrate": "128",         // Audio quality (128, 320)
    "download_dir": "./downloads"
  }
}
```

### Audio Quality

Free Deezer accounts support up to 128kbps. Premium accounts can use:
- `128` - Standard quality (free accounts)
- `320` - High quality (premium accounts)

Change in `config.json` or set default in bot code.

## 🔧 Troubleshooting

### Bot Not Responding

```bash
# Check if container is running
docker ps

# Check logs for errors
docker-compose logs -f

# Restart bot
docker-compose restart
```

### ARL Token Expired

Deezer ARL tokens can expire. To update:

```bash
# Stop bot
docker-compose down

# Remove old token
rm deemix-config/.arl

# Get new token from deezer.com (F12 → Cookies)
echo "your_new_arl_token" > deemix-config/.arl

# Start bot
docker-compose up -d
```

### Downloads Failing

```bash
# Check deemix configuration
docker-compose exec spotify-telegram-bot cat /root/.config/deemix/.arl

# Test deemix manually
docker-compose exec spotify-telegram-bot deemix https://www.deezer.com/track/123456789

# Check logs
docker-compose logs -f | grep -i error
```

### Permission Issues

```bash
# Fix permissions on data directories
sudo chown -R $USER:$USER data/ downloads/ deemix-config/
chmod -R 755 data/ downloads/ deemix-config/
```

### Channel Upload Fails

- Verify bot is admin in the channel
- Check `CHANNEL_ID` is correct (should start with `-100`)
- Ensure bot has permission to send audio files

## 📊 Performance

- **Memory Usage**: ~200-500MB
- **CPU Usage**: Low (spikes during downloads)
- **Storage**: Depends on music library size
- **Network**: Downloads audio files, minimal API calls

## 🔒 Security Best Practices

1. **Never commit `.env` file** - Contains sensitive tokens
2. **Use strong admin verification** - Only trusted user IDs in `ADMIN_IDS`
3. **Regular backups** - Backup `data/` directory regularly
4. **Update dependencies** - Keep Docker images and packages updated
5. **Monitor logs** - Check for unauthorized access attempts

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is for educational purposes. Ensure you comply with:
- Spotify Terms of Service
- Deezer Terms of Service
- Telegram Bot API Terms
- Copyright laws in your jurisdiction

## ⚠️ Disclaimer

This bot is for personal use only. Downloading copyrighted content may be illegal in your country. Use responsibly and respect artists' rights.

## 🆘 Support

- **Issues**: Open an issue on GitHub
- **Questions**: Check existing issues or create new one
- **Updates**: Star the repo to get notifications

## 🎯 Roadmap

- [ ] Add support for YouTube Music
- [ ] Playlist scheduling (different check intervals per playlist)
- [ ] Multiple channel support
- [ ] Web dashboard for management
- [ ] User analytics and listening stats
- [ ] Automatic playlist creation based on genres

---

Made with ❤️ by developers who love music automation
