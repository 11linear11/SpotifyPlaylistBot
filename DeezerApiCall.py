import subprocess
import os
import requests
import time
import sys
import glob
import json


class DeemixDownloader:
    def __init__(self, deemix_path='deemix', arl_token=None):
        """Initialize with the path to the deemix executable and optional ARL token."""
        self.deemix_path = deemix_path
        self.config_file = os.path.expanduser('~/.config/deemix/.arl')
        self.settings_file = os.path.expanduser('~/.config/deemix/config.json')
        
        if arl_token:
            self.set_arl(arl_token)
        
        self._load_arl()
        self._configure_quality()

    def _load_arl(self):
        """بارگذاری خودکار ARL از فایل."""
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r') as f:
                self.arl_token = f.read().strip()
            return True
        return False

    def _configure_quality(self):
        """تنظیم کیفیت پایین‌تر برای حساب‌های رایگان."""
        config_dir = os.path.dirname(self.settings_file)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        
        # تنظیمات پیش‌فرض برای حساب رایگان
        default_config = {
            "downloadLocation": os.path.expanduser("~/Music"),
            "maxBitrate": "128",  # کیفیت پایین‌تر برای حساب رایگان
            "fallbackBitrate": True,
            "fallbackSearch": True,
            "logErrors": True,
            "logSearched": True,
            "saveArtwork": True,
            "coverImageTemplate": "cover",
            "saveArtworkArtist": False,
            "jpegImageQuality": 90,
            "embeddedArtworkSize": 800,
            "embeddedArtworkPNG": False,
            "localArtworkSize": 1400,
            "localArtworkFormat": "jpg",
            "savePlaylistAsCompilation": False,
            "playlistFilenameTemplate": "%playlist_title%",
            "createPlaylistFolder": True,
            "artistConcatString": ", ",
            "albumVariousArtists": True,
            "removeAlbumVersion": False,
            "syncedLyrics": False,
            "playlistTracknumberTemplate": 0,
            "tags": {
                "title": True,
                "artist": True,
                "album": True,
                "cover": True,
                "trackNumber": True,
                "trackTotal": True,
                "discNumber": True,
                "discTotal": True,
                "albumArtist": True,
                "genre": True,
                "year": True,
                "date": True,
                "explicit": False,
                "isrc": True,
                "length": True,
                "barcode": True,
                "bpm": True,
                "replayGain": False,
                "label": True,
                "lyrics": False,
                "copyright": False,
                "composer": False,
                "involvedPeople": False,
                "source": False,
                "savePlaylistAsCompilation": False,
                "useNullSeparator": False,
                "saveID3v1": True,
                "multiArtistSeparator": "default",
                "singleAlbumArtist": False,
                "coverDescriptionUTF8": False
            }
        }
        
        # اگر فایل وجود نداره یا خالیه، تنظیمات پیش‌فرض رو بنویس
        if not os.path.exists(self.settings_file):
            with open(self.settings_file, 'w') as f:
                json.dump(default_config, f, indent=2)
            print(f"⚙️  Created config file with default settings for free accounts")
        else:
            # بررسی و به‌روزرسانی تنظیمات موجود
            try:
                with open(self.settings_file, 'r') as f:
                    config = json.load(f)
                
                # اطمینان از تنظیمات مناسب برای حساب رایگان
                config['maxBitrate'] = '128'
                config['fallbackBitrate'] = True
                
                with open(self.settings_file, 'w') as f:
                    json.dump(config, f, indent=2)
                print(f"⚙️  Updated config for free account (128kbps)")
            except:
                pass

    def set_arl(self, arl_token):
        """Set the ARL token for deemix - فقط یک بار نیاز دارید."""
        self.arl_token = arl_token
        
        config_dir = os.path.dirname(self.config_file)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        
        with open(self.config_file, 'w') as f:
            f.write(arl_token)
        
        print(f"✅ ARL token saved permanently to {self.config_file}")

    def is_configured(self):
        """بررسی اینکه آیا ARL تنظیم شده یا نه."""
        return hasattr(self, 'arl_token') and self.arl_token

    def download_track(self, track_name, artist_name, output_dir='./downloads', bitrate='128'):
        """Download a single track with specified bitrate."""
        try:
            if not self.is_configured():
                raise Exception("❌ ARL token not configured! Use: downloader.set_arl()")

            # جستجوی ترک
            track_url = self.search_track(track_name, artist_name)
            print(f"📥 Downloading from: {track_url}")

            # ایجاد پوشه خروجی با مسیر کامل
            output_dir = os.path.abspath(output_dir)
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)

            # ذخیره لیست فایل‌های قبل از دانلود
            before_files = self._get_files_in_dir(output_dir)

            # اجرای دستور deemix با کیفیت مشخص
            command = [
                self.deemix_path, 
                track_url, 
                '-p', output_dir,
                '-b', bitrate  # تنظیم bitrate
            ]
            
            print(f"🎵 Quality: {bitrate}kbps (suitable for free accounts)")
            
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            # نمایش خروجی
            for line in process.stdout:
                print(line, end='')
                sys.stdout.flush()

            return_code = process.wait(timeout=300)

            # پیدا کردن فایل جدید دانلود شده
            time.sleep(2)
            after_files = self._get_files_in_dir(output_dir)
            new_files = after_files - before_files
            
            if new_files:
                downloaded_file = list(new_files)[0]
                file_size = os.path.getsize(downloaded_file)
                print(f"✅ Downloaded: {track_name} by {artist_name}")
                print(f"📁 File: {downloaded_file}")
                print(f"📦 Size: {file_size / (1024*1024):.2f} MB\n")
                return downloaded_file
            elif return_code == 0:
                # فایل ممکنه قبلاً دانلود شده باشه
                print(f"⚠️  No new file created. Searching for existing file...")
                existing = self._find_track_file(output_dir, track_name, artist_name)
                if existing:
                    print(f"📁 Found existing file: {existing}\n")
                    return existing
                else:
                    # چک کردن پوشه Music
                    music_dir = os.path.expanduser("~/Music")
                    if os.path.exists(music_dir):
                        existing = self._find_track_file(music_dir, track_name, artist_name)
                        if existing:
                            print(f"📁 Found in Music folder: {existing}\n")
                            return existing
                    
                    raise Exception(
                        "Download completed but file not found!\n"
                        f"Check: {output_dir}\n"
                        f"Or: {music_dir}"
                    )
            else:
                raise Exception(f"Download failed with return code: {return_code}")

        except subprocess.TimeoutExpired:
            process.kill()
            raise Exception("Download timeout (>5 minutes)")
        except Exception as e:
            raise Exception(f"Error: {str(e)}")

    def _get_files_in_dir(self, directory):
        """دریافت لیست فایل‌های صوتی در پوشه."""
        files = set()
        if os.path.exists(directory):
            for root, dirs, filenames in os.walk(directory):
                for f in filenames:
                    if f.endswith(('.mp3', '.flac', '.m4a', '.opus')):
                        files.add(os.path.join(root, f))
        return files

    def _find_track_file(self, directory, track_name, artist_name, max_age_hours=1):
        """پیدا کردن فایل ترک در پوشه."""
        if not os.path.exists(directory):
            return None
        
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        # جستجوی فایل‌های اخیر
        for root, dirs, files in os.walk(directory):
            for f in files:
                if f.endswith(('.mp3', '.flac', '.m4a', '.opus')):
                    full_path = os.path.join(root, f)
                    file_age = current_time - os.path.getctime(full_path)
                    
                    # بررسی سن فایل و نام
                    if file_age < max_age_seconds:
                        filename_lower = f.lower()
                        track_words = track_name.lower().split()[:2]
                        if any(word in filename_lower for word in track_words):
                            return full_path
        
        return None

    def download_tracks(self, tracks, output_dir='./downloads', bitrate='128'):
        """Download multiple tracks."""
        if not self.is_configured():
            raise Exception("ARL not configured! Run: downloader.set_arl()")

        downloaded_files = []
        failed_tracks = []
        
        print(f"📦 Starting batch download of {len(tracks)} tracks...")
        print(f"🎵 Quality: {bitrate}kbps\n")
        
        for i, (track_name, artist_name) in enumerate(tracks, 1):
            try:
                print(f"{'='*60}")
                print(f"[{i}/{len(tracks)}] {track_name} - {artist_name}")
                print('='*60)
                
                file_path = self.download_track(track_name, artist_name, output_dir, bitrate)
                downloaded_files.append((track_name, artist_name, file_path))
                
                if i < len(tracks):
                    time.sleep(2)
                    
            except Exception as e:
                print(f"❌ Failed: {e}\n")
                failed_tracks.append((track_name, artist_name, str(e)))
        
        # گزارش نهایی
        print(f"\n{'='*60}")
        print(f"📊 DOWNLOAD SUMMARY:")
        print(f"{'='*60}")
        print(f"✅ Successful: {len(downloaded_files)}/{len(tracks)}")
        print(f"❌ Failed: {len(failed_tracks)}/{len(tracks)}")
        
        if downloaded_files:
            print(f"\n📁 Downloaded files:")
            for track, artist, path in downloaded_files:
                if os.path.isfile(path):
                    size = os.path.getsize(path) / (1024*1024)
                    print(f"   ✓ {track} → {os.path.basename(path)} ({size:.2f} MB)")
        
        if failed_tracks:
            print(f"\n⚠️  Failed tracks:")
            for track, artist, _ in failed_tracks:
                print(f"   - {track} by {artist}")
        
        return downloaded_files

    def search_track(self, track_name, artist_name):
        """Search for a track on Deezer."""
        try:
            query = f"{track_name} {artist_name}"
            url = f"https://api.deezer.com/search?q={requests.utils.quote(query)}"
            
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('total', 0) == 0 or not data.get('data'):
                raise Exception(f"No tracks found for: {query}")

            track_info = data['data'][0]
            print(f"🔍 Found: {track_info['title']} by {track_info['artist']['name']}")
            
            return track_info['link']
            
        except Exception as e:
            raise Exception(f"Search failed: {str(e)}")

    def setup_arl(self):
        """راه‌اندازی تعاملی ARL - فقط یک بار اجرا کنید."""
        print("\n" + "="*60)
        print("🔑 ARL TOKEN SETUP (One-time only)")
        print("="*60)
        print("\n📌 How to get your Deezer ARL token:\n")
        print("1. Go to https://www.deezer.com and login")
        print("2. Press F12 to open Developer Tools")
        print("3. Go to 'Application' tab (Chrome) or 'Storage' (Firefox)")
        print("4. Expand 'Cookies' → 'https://www.deezer.com'")
        print("5. Find 'arl' cookie and copy its value")
        print("\n⚠️  Note: Free accounts can only download at 128kbps")
        print("="*60 + "\n")
        
        arl_input = input("Paste your ARL token here: ").strip()
        
        if arl_input:
            self.set_arl(arl_input)
            return True
        else:
            print("❌ No token provided!")
            return False


