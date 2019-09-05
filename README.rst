spotify-ripper
========================
A fork of (https://github.com/Mavyre/spotify-ripper), making its Dockerfile more generic.
Read there for how to set up the web api part.

This docker image expects the following parameters.

- volume /config with spotify-ripper settings and your api key file 'https://github.com/Mavyre/spotify-ripper'
- volume /music where spotify-ripper will store the downloaded files
- environment variables 'user', 'pass', and 'playlist'
- environment variables 'SPOTIPY_CLIENT_ID' and 'SPOTIPY_CLIENT_SECRET' for web api access

Then, the image will periodically download your 'playlist' and empty it. For that, you need to configure web api access.
