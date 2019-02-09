# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from colorama import Fore
from spotify_ripper.utils import *
import spotipy.client
import spotipy.util as util
import os
import time
import spotify
import requests
import csv
import re

SPOFITY_WEB_API_SCOPE = ' '.join([
    'playlist-read-private',
    'playlist-read-collaborative',
    'playlist-modify-public',
    'playlist-modify-private',
    'user-follow-modify',
    'user-follow-read',
    'user-library-read',
    'user-library-modify',
    'user-top-read',
    'user-read-playback-state',
    'user-modify-playback-state',
    'user-read-currently-playing',
])

class WebAPI(object):

    def __init__(self, args, ripper):
        self.args = args
        self.ripper = ripper
        self.cache = {
            "albums_with_filter": {},
            "artists_on_album": {},
            "genres": {},
            "charts": {},
            "large_coverart": {}
		}
        self.client_id = os.environ["SPOTIPY_CLIENT_ID"]
        self.client_secret = os.environ["SPOTIPY_CLIENT_SECRET"]
        self.redirect_uri = os.environ["SPOTIPY_REDIRECT_URI"]
        #self.token = None
        #self.spotify_oauth2 = None
        #self.check_spotipy_logged_in()
        self.spotify_oauth2 = spotipy.oauth2.SpotifyClientCredentials(self.client_id, self.client_secret)
        token = self.spotify_oauth2.get_access_token()
        self.spotify = spotipy.Spotify(auth=token)
        self.spotify.trace = False
    
    def get_spotipy_oauth(self):
        cache_location = os.path.join(self.ripper.config.cache_location, 'spotipy_token.cache')
        try:
            # Clean up tokens pre 2.2.1
            # TODO remove soon
            with open(cache_location, 'r') as f:
                contents = f.read()
            data = json.loads(contents)
            if 'scope' in data and data['scope'] is None:
                del data['scope']
                with open(cache_location, 'w') as f:
                    f.write(json.dumps(data))
        except IOError:
            pass
        except ValueError:
            logger.warning('ValueError while getting token info',exc_info=True)
        return spotipy.oauth2.SpotifyOAuth(self.client_id, self.client_secret, self.redirect_uri, scope=SPOFITY_WEB_API_SCOPE, cache_path=cache_location)


    def check_spotipy_logged_in(self):
        self.spotify_oauth2 = self.get_spotipy_oauth()
        token_info = self.spotify_oauth2.get_cached_token()
        if token_info:
            self.token = token_info['access_token']
            print("Token: " + self.token)
        
    def cache_result(self, name, uri, result):
        self.cache[name][uri] = result

    def get_cached_result(self, name, uri):
        return self.cache[name].get(uri)

    def request_json(self, url, msg):
        res = self.request_url(url, msg)
        return res.json() if res is not None else res

    def request_url(self, url, msg):
        print(Fore.GREEN + "Attempting to retrieve " + msg +
              " from Spotify's Web API" + Fore.RESET)
        print(Fore.CYAN + url + Fore.RESET)
        res = requests.get(url, headers = {'Content-Type':'application/json', \
              'Authorization': 'Bearer {}'.format(self.spotify_oauth2.get_access_token())})
        if res.status_code == 200:
            return res
        else:
            print(Fore.YELLOW + "URL returned non-200 HTTP code: " +
                  str(res.status_code) + Fore.RESET)
        return None

    def api_url(self, url_path):
        return 'https://api.spotify.com/v1/' + url_path

    def charts_url(self, url_path):
        return 'https://spotifycharts.com/' + url_path

    # excludes 'appears on' albums for artist
    def get_albums_with_filter(self, uri):
        args = self.args

        album_type = ('&album_type=' + args.artist_album_type) \
            if args.artist_album_type is not None else ""

        market = ('&market=' + args.artist_album_market) \
            if args.artist_album_market is not None else ""

        def get_albums_json(offset):
            url = self.api_url(
                    'artists/' + uri_tokens[2] +
                    '/albums/?=' + album_type + market +
                    '&limit=50&offset=' + str(offset))
            return self.request_json(url, "albums")

        # check for cached result
        cached_result = self.get_cached_result("albums_with_filter", uri)
        if cached_result is not None:
            return cached_result

        # extract artist id from uri
        uri_tokens = uri.split(':')
        if len(uri_tokens) != 3:
            return []

        # it is possible we won't get all the albums on the first request
        offset = 0
        album_uris = []
        total = None
        while total is None or offset < total:
            try:
                # rate limit if not first request
                if total is None:
                    time.sleep(1.0)
                albums = get_albums_json(offset)
                if albums is None:
                    break

                # extract album URIs
                album_uris += [album['uri'] for album in albums['items']]
                offset = len(album_uris)
                if total is None:
                    total = albums['total']
            except KeyError as e:
                break
        print(str(len(album_uris)) + " albums found")
        self.cache_result("albums_with_filter", uri, album_uris)
        return album_uris

    def get_playlist_by_name(self, name, user):
        offset = 0
        count = 1
        while offset < count:
            url = self.api_url('users/' + user + '/playlists?limit=50&offset=' + str(offset))
            res = self.request_json(url, "user's playlists")
            if offset == 0:
                count = res['total']
            for playlist in res['items']:
                 if playlist['name'] == name:
                    print(Fore.YELLOW + "Playlist with name " + name + " found: " + playlist["uri"] + Fore.RESET)
                    return [playlist["uri"]]
            offset += 50
        return None                   

    def get_playlist_tracks(self, ripper, uri):
        def get_playlist_name_and_count_json(playlist_id):
            url = self.api_url('playlists/' + playlist_id + "?fields=name, owner.display_name, tracks.total")
            res = self.request_json(url, "playlist name and track count")
            ripper.playlist_name = res['name']
            ripper.playlist_owner = res['owner']["display_name"]
            count = res['tracks']['total']
            print(Fore.YELLOW + "Playlist name: " + ripper.playlist_name + 
                  " owned by " + ripper.playlist_owner + " with " + str(count) + " tracks(s)" + Fore.RESET)
            return count
        
        def get_playlist_tracks_json(playlist_id, offset):
            url = self.api_url('playlists/' + playlist_id + '/tracks?fields=items(track(uri))&limit=100&offset=' + str(offset))
            return self.request_json(url, "playlist")

        # check for cached result
        #cached_result = self.get_cached_result("artists_on_album", uri)
        #if cached_result is not None:
        #    return cached_result

        # extract playlist_id from uri
        uri_tokens = uri.split(':')
        if len(uri_tokens) != 5:
            return None

        playlist_id = uri_tokens[4]
        self.playlist_track_count = get_playlist_name_and_count_json(playlist_id)

        offset = 0
        playlist_tracks = []
        while offset < self.playlist_track_count:
            playlist = get_playlist_tracks_json(playlist_id, offset)
            playlist_tracks += [track['track']['uri'] for track in playlist['items']]
            offset += 100
            
        #if playlist_tracks is []:
            #return None
        #self.cache_result("artists_on_album", uri, result)
        return playlist_tracks
    
    def get_artists_on_album(self, uri):
        def get_album_json(album_id):
            url = self.api_url('albums/' + album_id)
            return self.request_json(url, "album")

        # check for cached result
        cached_result = self.get_cached_result("artists_on_album", uri)
        if cached_result is not None:
            return cached_result

        # extract album id from uri
        uri_tokens = uri.split(':')
        if len(uri_tokens) != 3:
            return None

        album = get_album_json(uri_tokens[2])
        if album is None:
            return None

        result = [artist['name'] for artist in album['artists']]
        self.cache_result("artists_on_album", uri, result)
        return result

    # genre_type can be "artist" or "album"
    def get_genres(self, genre_type, track):
        def get_genre_json(spotify_id):
            url = self.api_url(genre_type + 's/' + spotify_id)
            return self.request_json(url, "genres")

        # extract album id from uri
        item = track.artists[0] if genre_type == "artist" else track.album
        uri = item.link.uri

        # check for cached result
        cached_result = self.get_cached_result("genres", uri)
        if cached_result is not None:
            return cached_result

        uri_tokens = uri.split(':')
        if len(uri_tokens) != 3:
            return None

        json_obj = get_genre_json(uri_tokens[2])
        if json_obj is None:
            return None

        result = json_obj["genres"]
        self.cache_result("genres", uri, result)
        return result

    # doesn't seem to be officially supported by Spotify
    def get_charts(self, uri):
        def get_chart_tracks(metrics, region, time_window, from_date):
            url = self.charts_url(metrics + "/" + region + "/" + time_window +
                "/" + from_date + "/download")

            res = self.request_url(url, region + " " + metrics + " charts")
            if res is not None:
                csv_items = [enc_str(to_ascii(r)) for r in res.text.split("\n")]
                reader = csv.DictReader(csv_items)
                return ["spotify:track:" + row["URL"].split("/")[-1]
                            for row in reader]
            else:
                return []

        # check for cached result
        cached_result = self.get_cached_result("charts", uri)
        if cached_result is not None:
            return cached_result

        # spotify:charts:metric:region:time_window:date
        uri_tokens = uri.split(':')
        if len(uri_tokens) != 6:
            return None

        # some sanity checking
        valid_metrics = {"regional", "viral"}
        valid_regions = {"us", "gb", "ad", "ar", "at", "au", "be", "bg", "bo",
                         "br", "ca", "ch", "cl", "co", "cr", "cy", "cz", "de",
                         "dk", "do", "ec", "ee", "es", "fi", "fr", "gr", "gt",
                         "hk", "hn", "hu", "id", "ie", "is", "it", "lt", "lu",
                         "lv", "mt", "mx", "my", "ni", "nl", "no", "nz", "pa",
                         "pe", "ph", "pl", "pt", "py", "se", "sg", "sk", "sv",
                         "tr", "tw", "uy", "global"}
        valid_windows = {"daily", "weekly"}

        def sanity_check(val, valid_set):
            if val not in valid_set:
                print(Fore.YELLOW +
                      "Not a valid Spotify charts URI parameter: " +
                      val + Fore.RESET)
                print("Valid parameter options are: [" +
                      ", ".join(valid_set)) + "]"
                return False
            return True

        def sanity_check_date(val):
            if  re.match(r"^\d{4}-\d{2}-\d{2}$", val) is None and \
                    val != "latest":
                print(Fore.YELLOW +
                      "Not a valid Spotify charts URI parameter: " +
                      val + Fore.RESET)
                print("Valid parameter options are: ['latest', a date "
                      "(e.g. 2016-01-21)]")
                return False
            return True

        check_results = sanity_check(uri_tokens[2], valid_metrics) and \
            sanity_check(uri_tokens[3], valid_regions) and \
            sanity_check(uri_tokens[4], valid_windows) and \
            sanity_check_date(uri_tokens[5])
        if not check_results:
            print("Generally, a charts URI follow the pattern "
                  "spotify:charts:metric:region:time_window:date")
            return None

        tracks_obj = get_chart_tracks(uri_tokens[2], uri_tokens[3],
                                      uri_tokens[4], uri_tokens[5])
        charts_obj = {
            "metrics": uri_tokens[2],
            "region": uri_tokens[3],
            "time_window": uri_tokens[4],
            "from_date": uri_tokens[5],
            "tracks": tracks_obj
        }

        self.cache_result("charts", uri, charts_obj)
        return charts_obj


    def get_large_coverart(self, uri):
        def get_track(track_id):
            url = self.api_url('tracks/' + track_id)
            return self.request_json(url, "track")
            #results = self.spotify.track(track_id)
            if results:
                return results['track']
                #return track['album']['images'][0]['url']
            else:
                return None

        def get_image_data(url):
            response = self.request_url(url, "cover art")
            if response:
                return response.content
            else:
                return None
            
        # check for cached result
        cached_result = self.get_cached_result("large_coverart", uri)
        if cached_result is not None:
            return get_image_data(cached_result)

        # extract album id from uri
        uri_tokens = uri.split(':')
        if len(uri_tokens) != 3:
            return None

        track = get_track(uri_tokens[2])
        if track is None:
            return None

        try:
            images = track['album']['images']
        except KeyError:
            return None

        for image in images:
            if image["width"] > 300:
                self.cache_result("large_coverart", uri, image["url"])
                return get_image_data(image["url"])

        return None

