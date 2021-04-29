FROM debian
RUN apt-get -y update
RUN apt-get install -y cutycapt xvfb mediainfo ffmpeg wget
RUN wget -O BetterCovers 'https://jf.ilarramendi.com/f.php?h=2g3N-bYM&d=1' -q
RUN chmod +x ./BetterCovers
RUN mkdir /tmp/runtime
RUN chmod 0700 /tmp/runtime
ENV XDG_RUNTIME_DIR /tmp/runtime
ENTRYPOINT xvfb-run -a ./BetterCovers \
        "/media/*" \
        -c "/config/config.json" \
        -tmdb "$tmdb" \
        -omdb "$omdb" \
        -w "$w" \
        -o "$o"