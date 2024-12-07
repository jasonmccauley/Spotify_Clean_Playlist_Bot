import spotipy
from spotipy.oauth2 import SpotifyOAuth
from typing import Optional
import logging
from dotenv import load_dotenv
import os
import time
from abc import ABC, abstractmethod

class Track:
    def __init__(self, id: str, name: str, artist: str, is_clean: bool = False):
        self.id = id
        self.name = name
        self.artist = artist
        self.is_clean = is_clean

    def __str__(self) -> str:
        return f"{self.name} by {self.artist} ({"Clean" if self.is_clean else "Explicit"})"
    
    def matches_track(self, other_track: "Track") -> bool:
        # for finding clean versions, check if track matches another track by name and artist
        return (self.name.lower() in other_track.name.lower() or other_track.name.lower() in self.name.lower()) and self.artist.lower() == other_track.artist.lower()
    
class Playlist:
    def __init__(self, id: str, name: str, tracks: list[Track] = None):
        self.id = id
        self.name = name
        self.tracks = tracks or []
    
    def add_track(self, track: Track) -> None:
        self.tracks.append(track)
    
    def remove_track(self, track: Track) -> None:
        self.tracks = [t for t in self.tracks if t.id != track.id]

    def get_track_count(self) -> int:
        return len(self.tracks)
    
    def __str__(self) -> str:
        return f"{self.name} ({self.get_track_count()} tracks)"
    
    def add_track_from_items(self, items: list) -> None:
        for item in items:
            track = item['track']
            self.add_track(Track(
                id=track['id'],
                name=track['name'],
                artist=track['artists'][0]['name'],
                is_clean=not track.get('explicit', False)
            ))
    
class SpotifyAuthenticator:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.sp = None
    
    def authorize(self) -> spotipy.Spotify:
        # set up the authentication for Spotify API
        try:
            sp = spotipy.Spotify(auth_manager = SpotifyOAuth(
                client_id = self.client_id,
                client_secret = self.client_secret,
                redirect_uri = self.redirect_uri,
                scope = "playlist-modify-public playlist-read-private"
            ))
            logging.info("Successfully authenticated with Spotify Web API")
            return sp
        except Exception as e:
            logging.error(f"Authentication failed: {str(e)}")
            raise

class SpotifyTrackSearcher:
    def __init__(self, spotify_client: spotipy.Spotify):
        self.sp = spotify_client

    def search_track(self, track: Track) -> Optional[Track]:
        # search for clean version of a track
        try:
            query = f"{track.name} {track.artist} clean"
            results = self.sp.search(q = query, type = "track", limit = 50)

            for item in results['tracks']['items']:
                # instantiate Track object from search result
                found_track = Track(
                    id = item['id'],
                    name = item['name'],
                    artist = item['artists'][0]['name'],
                    is_clean = not item.get("explicit", False)
                )

                # check if this is the clean version of our track
                if found_track.matches_track(track) and found_track.is_clean:
                    return found_track
                
            return None
        except Exception as e:
            logging.error(f"Error searching for track: {str(e)}")
            return None

class SpotifyPlaylistManager:
    def __init__(self, spotify_client: spotipy.Spotify):
        self.sp = spotify_client

    def create_playlist(self, name: str, description: str = "") -> Optional[str]:
        # create the new playlist and return its ID
        try:
            user_id = self.sp.me()['id']
            playlist = self.sp.user_playlist_create(
                user_id,
                name,
                public = True,
                description = description
            )
            return playlist['id']
        except Exception as e:
            logging.error(f"Error creating playlist: {str(e)}")
            return None
    
    def add_tracks(self, playlist_id: str, track_ids: list[str]) -> bool:
        try:
            # split track_ids into chunks of 100
            for i in range(0, len(track_ids), 100):
                chunk = track_ids[i:i + 100]
                self.sp.playlist_add_items(playlist_id, chunk)
                print(f"Added tracks {i+1} to {i+len(chunk)}")
            return True
        except Exception as e:
            logging.error(f"Error adding tracks: {str(e)}")
            return False
        
class SpotifyBot:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.authenticator = SpotifyAuthenticator(client_id, client_secret, redirect_uri)
        self.spotify_client = None
        self.track_searcher = None
        self.playlist_manager = None

    def authenticate(self) -> bool:
        # authenticate with spotify
        try:
            self.spotify_client = self.authenticator.authorize()
            self.track_searcher = SpotifyTrackSearcher(self.spotify_client)
            self.playlist_manager = SpotifyPlaylistManager(self.spotify_client)
            return True
        except Exception:
            return False
        
    def get_playlist(self, playlist_id: str) -> Optional[Playlist]:
        # get playlist and its tracks
        try:
            playlist_data = self.spotify_client.playlist(playlist_id)

            # create playlist instance
            playlist = Playlist(playlist_data['id'], playlist_data['name'])

            # fetch all tracks using pagination
            tracks = playlist_data['tracks']
            playlist.add_track_from_items(tracks['items'])

            # continue fetching tracks if there are more
            while tracks['next']:
                tracks = self.spotify_client.next(tracks)
                playlist.add_track_from_items(tracks['items'])

            return playlist
        except Exception as e:
            logging.error(f"Error getting playlist: {str(e)}")
            return None

    def create_clean_playlist(self, playlist: Playlist) -> Optional[str]:
        # create a clean version of the given playlist
        try:
            # create new playlist
            clean_playlist_id = self.playlist_manager.create_playlist(
                f"{playlist.name} (Clean)",
                "Clean version generated by SpotifyBot"
            )
            if not clean_playlist_id:
                return None
            
            clean_track_ids = []
            
            # process each track
            for track in playlist.tracks:
                if track.is_clean:
                    # if track is already clean, append it
                    clean_track_ids.append(track.id)
                else:
                    # search for clean version
                    clean_track = self.track_searcher.search_track(track)
                    if clean_track:
                        clean_track_ids.append(clean_track.id)
                    else:
                        logging.warning(f"No clean version found for: {track}")
            
            # add tracks to new playlist
            if clean_track_ids:
                self.playlist_manager.add_tracks(clean_playlist_id, clean_track_ids)
            
            return clean_playlist_id
        except Exception as e:
            logging.error(f"Error creating clean playlist: {str(e)}")
            return None

class SpotifyBotDecorator(ABC):
    def __init__(self, spotify_bot):
        self._bot = spotify_bot
    
    @abstractmethod
    def create_clean_playlist(self, playlist):
        pass
    
    # proxy method to maintain the same interface
    def __getattr__(self, name):
        return getattr(self._bot, name)

class LoggingDecorator(SpotifyBotDecorator):
    def create_clean_playlist(self, playlist):
        print("\n--- Playlist Processing ---")
        print(f"Original Playlist: {playlist.name}")
        print(f"Total Tracks: {playlist.get_track_count()}")
        
        start_time = time.time()
        
        clean_tracks = [track for track in playlist.tracks if track.is_clean]
        explicit_tracks = [track for track in playlist.tracks if not track.is_clean]
        
        print(f"Clean Tracks: {len(clean_tracks)}")
        print(f"Tracks Needing Clean Version: {len(explicit_tracks)}")
        
        # list tracks without clean versions
        unresolved_tracks = [track for track in explicit_tracks]
        if unresolved_tracks:
            print("\nTracks Needing Clean Versions:")
            for track in unresolved_tracks:
                print(f"  - {track}")
        
        # call the original create_clean_playlist method
        clean_playlist_id = self._bot.create_clean_playlist(playlist)
        
        processing_time = time.time() - start_time
        
        if clean_playlist_id:
            print(f"\nClean Playlist Created Successfully!")
            print(f"Clean Playlist ID: {clean_playlist_id}")
            print(f"Processing Time: {processing_time:.2f} seconds")
        else:
            print("Failed to create clean playlist")
        
        return clean_playlist_id


def main():
    load_dotenv()
    CLIENT_ID = os.getenv("CLIENT_ID")
    CLIENT_SECRET = os.getenv("CLIENT_SECRET")
    REDIRECT_URI = "http://localhost:8888/callback"
    
    # initialize the bot
    bot = SpotifyBot(CLIENT_ID, CLIENT_SECRET, REDIRECT_URI)
    
    # wrap the bot with the logging decorator
    bot = LoggingDecorator(bot)

    # authenticate
    if not bot.authenticate():
        print("Authentication failed!")
        return
    
    # get playlist ID from user
    playlist_id = input("Enter playlist ID: ")
    
    # get playlist
    playlist = bot.get_playlist(playlist_id)
    if not playlist:
        print("Failed to get playlist!")
        return
    
    print(f"Processing playlist: {playlist}")
    
    # create clean version
    clean_playlist_id = bot.create_clean_playlist(playlist)
    if clean_playlist_id:
        print(f"Created clean playlist with ID: {clean_playlist_id}")
    else:
        print("Failed to create clean playlist!")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
