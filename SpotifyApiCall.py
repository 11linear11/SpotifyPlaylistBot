
import json
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from urllib.parse import urlparse

class SpotifyAPI:
    def __init__(self, client_id, client_secret):
        client_credentials_manager = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
        self.sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)

    def get_playlist_tracks(self, playlist_link):
        parsed_url = urlparse(playlist_link)
        if 'playlist' in parsed_url.path:
            playlist_id = parsed_url.path.split('/')[-1]
        else:
            raise ValueError('Invalid playlist link')

        results = self.sp.playlist_items(playlist_id)
        tracks = []
        while results:
            for item in results['items']:
                track = item['track']
                tracks.append({
                    'name': track['name'],
                    'artists': [artist['name'] for artist in track['artists']],
                    'id': track['id']
                })
            if results['next']:
                results = self.sp.next(results)
            else:
                results = None
        return tracks

    def save_tracks_to_json(self, tracks, filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                existing_tracks = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            existing_tracks = []

        existing_ids = {track['id'] for track in existing_tracks}

        # ابتدا فلگ new همه ترک‌های موجود را False می‌کنیم
        for track in existing_tracks:
            track['new'] = False

        new_tracks = []
        for track in tracks:
            if track['id'] not in existing_ids:
                track['new'] = True
                new_tracks.append(track)
            else:
                # برای ترک‌های موجود، فلگ new را حفظ می‌کنیم (که الان False است)
                for et in existing_tracks:
                    if et['id'] == track['id']:
                        track['new'] = et.get('new', False)
                        break

        all_tracks = existing_tracks + new_tracks

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(all_tracks, f, ensure_ascii=False, indent=4)

        return new_tracks


