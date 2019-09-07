#!/bin/bash

spotify-ripper -S /config/ -k /config/spotify_appkey.key -d /music -u ${user} -p ${pass} ${playlist} && python /ripper/source-code/spotify_ripper/emptyPlaylist.py
