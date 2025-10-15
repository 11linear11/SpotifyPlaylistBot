# 🛡️ راهنمای مدیریت خطاها و Timeout

این سند توضیح می‌دهد که ربات چگونه خطاها و timeout‌ها را مدیریت می‌کند.

## 🎯 انواع خطاها

### 1. Timeout Errors ⏱️

**علت:**
- فایل بزرگ
- اتصال اینترنت ضعیف
- سرور Telegram پاسخ نمی‌دهد

**راه حل ربات:**
- ✅ 3 بار تلاش مجدد
- ✅ Exponential backoff (5s, 10s, 15s)
- ✅ Timeout قابل تنظیم (پیش‌فرض: 120 ثانیه)
- ✅ گزارش به ادمین در صورت شکست نهایی

**لاگ نمونه:**
```
⏱️ Timeout on attempt 1/3 for Coffee
⏳ Waiting 5s before retry...
📤 Attempt 2/3: Sending Coffee
✅ Successfully sent: Coffee
```

### 2. Rate Limiting (Flood Control) 🚫

**علت:**
- ارسال خیلی سریع به Telegram
- محدودیت تعداد پیام در واحد زمان

**راه حل ربات:**
- ✅ تشخیص خطای "flood" یا "too many requests"
- ✅ صبر 60 ثانیه برای اولین بار
- ✅ صبر 120 ثانیه برای بار دوم
- ✅ صبر 180 ثانیه برای بار سوم
- ✅ فاصله 3 ثانیه بین ارسال موفق
- ✅ فاصله 5 ثانیه بعد از شکست

**لاگ نمونه:**
```
🚫 Rate limited. Waiting 60s...
📤 Retry after cooldown...
```

### 3. Channel Errors 📺

**علت:**
- ربات در چنل Admin نیست
- چنل پیدا نشد
- ID چنل اشتباه است

**راه حل ربات:**
- ✅ تشخیص خطای "chat not found"
- ✅ عدم تلاش مجدد (خطای دائمی)
- ✅ اطلاع فوری به ادمین
- ✅ توقف ارسال برای جلوگیری از هدر رفت منابع

**لاگ نمونه:**
```
❌ Channel not found or bot not admin: @wrongchannel
❌ خطا: چنلی برای این پلی‌لیست تنظیم نشده است!
```

### 4. File Size Errors 📦

**علت:**
- فایل بیش از 50 مگابایت
- محدودیت Telegram Bot API

**راه حل ربات:**
- ✅ نمایش سایز فایل قبل از ارسال
- ✅ تشخیص خطای "file is too big"
- ✅ عدم تلاش مجدد
- ✅ گزارش فایل‌های بزرگ به ادمین

**لاگ نمونه:**
```
📦 File size: 52.3 MB
❌ File too large: Long Song (52.3 MB)
```

### 5. Network Errors 🌐

**علت:**
- قطعی اینترنت
- مشکل DNS
- Firewall

**راه حل ربات:**
- ✅ 3 بار تلاش مجدد
- ✅ صبر بین تلاش‌ها
- ✅ ادامه با آهنگ بعدی در صورت شکست
- ✅ اطلاع به ادمین برای خطاهای حیاتی

## 🔧 تنظیمات

### تغییر Timeout

در `bot.py` خط مربوط به `send_audio_to_channel`:

```python
async def send_audio_to_channel(
    self, file_path: str, track_name: str, 
    artist_name: str, channel_id: str, 
    max_retries: int = 3,      # تعداد تلاش
    timeout: int = 120         # ثانیه (تغییر دهید)
) -> bool:
```

**مقادیر پیشنهادی:**
- اتصال سریع: `timeout = 60`
- اتصال معمولی: `timeout = 120` (پیش‌فرض)
- اتصال کند: `timeout = 180`
- فایل‌های بزرگ: `timeout = 300`

### تغییر تعداد Retry

```python
max_retries: int = 3  # تغییر به 5 برای ثبات بیشتر
```

### تغییر Rate Limiting

در بخش `process_new_tracks`:

```python
# بعد از ارسال موفق
await asyncio.sleep(3)  # تغییر به 5 برای امنیت بیشتر

# بعد از شکست
await asyncio.sleep(5)  # تغییر به 10 برای cooldown بیشتر
```

## 📊 گزارش‌ها

### گزارش موفقیت ✅

```
📊 Summary: 8 succeeded, 2 failed out of 10 tracks
✅ Successfully sent 8 tracks to @channel
```

### گزارش شکست به ادمین ❌

```
⚠️ گزارش ارسال آهنگ‌ها:

✅ موفق: 8
❌ ناموفق: 2

آهنگ‌های ناموفق:
• Coffee - beabadoobee
• Long Track Name - Artist
```

### لاگ دقیق 🔍

```
📤 Attempt 1/3: Sending Coffee
📦 File size: 3.45 MB
📤 Sending: Coffee - beabadoobee
📁 File path: /app/downloads/Coffee.mp3
✅ Successfully sent: Coffee - beabadoobee to @channel
✅ Marked as sent: Coffee
🗑️ Cleaned up: /app/downloads/Coffee.mp3
```

## 🚨 خطاهای حیاتی

ربات برای خطاهای زیر فوراً به ادمین اطلاع می‌دهد:

1. **NetworkError**: مشکل شبکه
2. **TimedOut**: تمام تلاش‌ها timeout شدند
3. **RetryAfter**: Telegram درخواست کاهش سرعت داده
4. **Conflict**: bot instance دیگری در حال اجرا است
5. **Unauthorized**: توکن نامعتبر یا منقضی شده

**پیام نمونه:**
```
🚨 خطای حیاتی:

نوع: NetworkError
پیام: httpx.RemoteProtocolError: Server disconnected
```

## 🔍 عیب‌یابی

### مشکل: همه آهنگ‌ها timeout می‌شوند

**راه حل‌ها:**
1. Timeout را افزایش دهید (180 یا 300)
2. اتصال اینترنت را بررسی کنید
3. از VPN استفاده کنید اگر Telegram فیلتر است
4. فایل‌های بزرگ را کوچک‌تر کنید (تنظیم bitrate)

### مشکل: Rate limiting مداوم

**راه حل‌ها:**
1. فاصله بین ارسال‌ها را افزایش دهید (5-10 ثانیه)
2. تعداد پلی‌لیست‌ها را کاهش دهید
3. بازه چک را افزایش دهید (12 ساعت به جای 6)

### مشکل: Channel not found

**راه حل‌ها:**
1. مطمئن شوید ربات در چنل Admin است
2. ID چنل را دوباره بررسی کنید
3. از `/linkplaylist` استفاده کنید
4. دسترسی‌های ربات را بررسی کنید

### مشکل: فایل‌ها خیلی بزرگ هستند

**راه حل‌ها:**
1. در `config.json` bitrate را کاهش دهید:
```json
"settings": {
  "bitrate": "96"  // به جای 128
}
```

2. یا در کد تغییر دهید:
```python
bitrate=self.config_manager.config['settings']['bitrate']
```

## 📈 بهترین شیوه‌ها

### 1. تنظیمات متعادل ⚖️

```python
max_retries = 3          # کافی برای اکثر موارد
timeout = 120            # 2 دقیقه
sleep_after_success = 3  # جلوگیری از rate limit
sleep_after_fail = 5     # cooldown بیشتر
```

### 2. مانیتورینگ 📊

لاگ‌ها را بررسی کنید:
```bash
docker-compose logs -f | grep -E "❌|⚠️|🚨"
```

فقط خطاها:
```bash
docker-compose logs | grep ERROR
```

آمار موفقیت:
```bash
docker-compose logs | grep "📊 Summary"
```

### 3. Backup و Recovery 💾

در صورت خطاهای مکرر:

```bash
# Backup database
cp tracks_database.json tracks_database.json.backup

# Restart
docker-compose restart

# اگر نیاز به rebuild است
docker-compose down
docker-compose up -d --build
```

### 4. Notification Settings 🔔

تنظیم اطلاع‌رسانی‌ها:

**خطاهای مهم:**
- ✅ Channel errors
- ✅ ARL problems
- ✅ Network failures

**خطاهای عادی:**
- ❌ Single timeout (retry می‌شود)
- ❌ Rate limiting (خودکار مدیریت می‌شود)

## 🎯 خلاصه

| خطا | Retry | Backoff | اطلاع به ادمین |
|-----|-------|---------|----------------|
| Timeout | ✅ 3x | 5s, 10s, 15s | در صورت شکست نهایی |
| Rate Limit | ✅ 3x | 60s, 120s, 180s | خیر |
| Channel Error | ❌ | - | ✅ فوری |
| File Too Big | ❌ | - | ✅ فوری |
| Network Error | ✅ 3x | 5s, 10s, 15s | برای خطاهای حیاتی |

---

**آخرین بروزرسانی**: اکتبر 2025  
**نسخه**: 2.1  
**قابلیت**: Advanced Error Handling & Timeout Management
