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

# base abstract SpotifyBot class
class SpotifyBot(ABC):
    @abstractmethod
    def authenticate(self) -> bool:
        pass
    
    @abstractmethod
    def search_track(self, track: Track) -> Optional[Track]:
        pass
    
    @abstractmethod
    def create_playlist(self, name: str, description: str = "") -> Optional[str]:
        pass
    
    @abstractmethod
    def add_tracks(self, playlist_id: str, track_ids: list[str]) -> bool:
        pass
    
    @abstractmethod
    def get_playlist(self, playlist_id: str) -> Optional[Playlist]:
        pass

class SpotifyAuthenticator(SpotifyBot):
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.sp = None
    
    def authenticate(self) -> spotipy.Spotify:
        # set up the authentication for Spotify API
        try:
            self.sp = spotipy.Spotify(auth_manager = SpotifyOAuth(
                client_id = self.client_id,
                client_secret = self.client_secret,
                redirect_uri = self.redirect_uri,
                scope = "playlist-modify-public playlist-read-private"
            ))
            logging.info("Successfully authenticated with Spotify Web API")
            return True
        except Exception as e:
            logging.error(f"Authentication failed: {str(e)}")
            return False

    # implement other abstract methods with pass
    def search_track(self, track: Track) -> Optional[Track]:
        pass

    def create_playlist(self, name: str, description: str = "") -> Optional[str]:
        pass

    def add_tracks(self, playlist_id: str, track_ids: list[str]) -> bool:
        pass

    def get_playlist(self, playlist_id: str) -> Optional[Playlist]:
        pass

class SpotifyTrackSearcher(SpotifyBot):
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
        
    def authenticate(self) -> bool:
        pass

    def create_playlist(self, name: str, description: str = "") -> Optional[str]:
        pass

    def add_tracks(self, playlist_id: str, track_ids: list[str]) -> bool:
        pass

    def get_playlist(self, playlist_id: str) -> Optional[Playlist]:
        pass

class SpotifyPlaylistManager(SpotifyBot):
    def __init__(self, spotify_client: spotipy.Spotify):
        self.sp = spotify_client

    def get_playlist(self, playlist_id: str) -> Optional[Playlist]:
        try:
            # get playlist data from Spotify API
            playlist_data = self.sp.playlist(playlist_id)

            # create new Playlist object
            playlist = Playlist(
                id=playlist_data['id'],
                name=playlist_data['name']
            )
            
            # get all tracks (handling pagination)
            tracks = []
            results = playlist_data['tracks']
            tracks.extend(results['items'])
            
            while results['next']:
                results = self.sp.next(results)
                tracks.extend(results['items'])
            
            # add tracks to playlist object
            playlist.add_track_from_items(tracks)
            
            return playlist
            
        except Exception as e:
            logging.error(f"Error getting playlist: {str(e)}")
            return None

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
    
    def authenticate(self) -> bool:
        pass

    def search_track(self, track: Track) -> Optional[Track]:
        pass

class SpotifyBotDecorator(SpotifyBot, ABC):
    def __init__(self, spotify_bot):
        self._bot = spotify_bot

    @property
    def sp(self):
        return self._bot.sp

# concrete decorator classes
class AuthenticatorLoggingDecorator(SpotifyBotDecorator):
    def authenticate(self) -> bool:
        print("\n--- Authentication Process ---")
        start_time = time.time()
        
        result = self._bot.authenticate()
        
        processing_time = time.time() - start_time
        print(f"Authentication {'Successful' if result else 'Failed'}")
        print(f"Processing Time: {processing_time:.2f} seconds")
        
        return result

    # delegate other methods to the wrapped bot
    def search_track(self, track: Track) -> Optional[Track]:
        return self._bot.search_track(track)

    def create_playlist(self, name: str, description: str = "") -> Optional[str]:
        return self._bot.create_playlist(name, description)

    def add_tracks(self, playlist_id: str, track_ids: list[str]) -> bool:
        return self._bot.add_tracks(playlist_id, track_ids)

    def get_playlist(self, playlist_id: str) -> Optional[Playlist]:
        return self._bot.get_playlist(playlist_id)

class TrackSearcherLoggingDecorator(SpotifyBotDecorator):
    def search_track(self, track: Track) -> Optional[Track]:
        print(f"\n--- Searching for Clean Version ---")
        print(f"Track: {track}")
        start_time = time.time()
        
        result = self._bot.search_track(track)
        
        processing_time = time.time() - start_time
        if result:
            print(f"Found clean version: {result}")
        else:
            print("No clean version found")
        print(f"Search Time: {processing_time:.2f} seconds")
        
        return result

    # delegate other methods
    def authenticate(self) -> bool:
        return self._bot.authenticate()

    def create_playlist(self, name: str, description: str = "") -> Optional[str]:
        return self._bot.create_playlist(name, description)

    def add_tracks(self, playlist_id: str, track_ids: list[str]) -> bool:
        return self._bot.add_tracks(playlist_id, track_ids)

    def get_playlist(self, playlist_id: str) -> Optional[Playlist]:
        return self._bot.get_playlist(playlist_id)

class PlaylistManagerLoggingDecorator(SpotifyBotDecorator):
    def create_playlist(self, name: str, description: str = "") -> Optional[str]:
        print(f"\n--- Creating Playlist ---")
        print(f"Name: {name}")
        start_time = time.time()
        
        playlist_id = self._bot.create_playlist(name, description)
        
        processing_time = time.time() - start_time
        print(f"{'Successfully created' if playlist_id else 'Failed to create'} playlist")
        print(f"Processing Time: {processing_time:.2f} seconds")
        
        return playlist_id

    def add_tracks(self, playlist_id: str, track_ids: list[str]) -> bool:
        print(f"\n--- Adding Tracks to Playlist ---")
        print(f"Number of tracks to add: {len(track_ids)}")
        start_time = time.time()
        
        success = self._bot.add_tracks(playlist_id, track_ids)
        
        processing_time = time.time() - start_time
        print(f"{'Successfully added' if success else 'Failed to add'} tracks")
        print(f"Processing Time: {processing_time:.2f} seconds")
        
        return success

    def get_playlist(self, playlist_id: str) -> Optional[Playlist]:
        print(f"\n--- Fetching Playlist ---")
        print(f"Playlist ID: {playlist_id}")
        start_time = time.time()
        
        playlist = self._bot.get_playlist(playlist_id)
        
        processing_time = time.time() - start_time
        if playlist:
            print(f"Successfully fetched playlist: {playlist}")
            print(f"Total tracks: {playlist.get_track_count()}")
        else:
            print("Failed to fetch playlist")
        print(f"Processing Time: {processing_time:.2f} seconds")
        
        return playlist

    # delegate other methods
    def authenticate(self) -> bool:
        return self._bot.authenticate()

    def search_track(self, track: Track) -> Optional[Track]:
        return self._bot.search_track(track)


def main():
    load_dotenv()
    CLIENT_ID = os.getenv("CLIENT_ID")
    CLIENT_SECRET = os.getenv("CLIENT_SECRET")
    REDIRECT_URI = "http://localhost:8888/callback"
    
    # create and decorate the authentication bot
    auth_bot = SpotifyAuthenticator(CLIENT_ID, CLIENT_SECRET, REDIRECT_URI)
    auth_bot = AuthenticatorLoggingDecorator(auth_bot)
    
    # authenticate
    if not auth_bot.authenticate():
        print("Authentication failed!")
        return
    
    # create and decorate the playlist manager bot
    playlist_bot = SpotifyPlaylistManager(auth_bot.sp)
    playlist_bot = PlaylistManagerLoggingDecorator(playlist_bot)
    
    # create and decorate the track searcher bot
    track_bot = SpotifyTrackSearcher(auth_bot.sp)
    track_bot = TrackSearcherLoggingDecorator(track_bot)
    
    # get playlist ID from user
    playlist_id = input("Enter playlist ID: ")
    
    # Get playlist
    original_playlist = playlist_bot.get_playlist(playlist_id)
    if not original_playlist:
        print("Failed to get playlist!")
        return
    
    # create new playlist
    clean_playlist_id = playlist_bot.create_playlist(
        f"{original_playlist.name} (Clean)",
        "Clean version generated by SpotifyBot"
    )
    if not clean_playlist_id:
        print("Failed to create clean playlist!")
        return
    
    # process tracks
    clean_track_ids = []
    for track in original_playlist.tracks:
        if track.is_clean:
            clean_track_ids.append(track.id)
        else:
            clean_track = track_bot.search_track(track)
            if clean_track:
                clean_track_ids.append(clean_track.id)
    
    # add tracks to new playlist
    if clean_track_ids:
        playlist_bot.add_tracks(clean_playlist_id, clean_track_ids)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()