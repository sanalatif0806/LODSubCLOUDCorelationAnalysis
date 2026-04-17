FROM ubuntu:latest
LABEL authors="sanal"

ENTRYPOINT ["top", "-b"]