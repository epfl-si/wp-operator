# This container won't work in a development environment: it needs to be
# deployed in the Kubernetes cluster and have to access this node's path
# `/var/run/secrets/kubernetes.io/serviceaccount/token` in order to access the
# Kubernetes's API.
# See https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/

FROM ubuntu:jammy

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get -qy update
RUN apt-get --no-install-recommends -qy install \
        awscli \
        curl \
        git \
        jq \
        patch \
        php-cli \
        php-mysql \
        python3 \
        python3-pip \
        restic \
        rsync \
        unzip \
     && rm -rf /var/lib/apt/lists/*; # from 1.12GB to 869MB

## Uncomment the following line if you want to test out your RBAC live:
# COPY --from=bitnami/kubectl:latest /opt/bitnami/kubectl/bin/kubectl /usr/local/bin/kubectl

RUN mkdir -p /srv/wp-operator
ENV HOME=/srv/wp-operator
WORKDIR /srv/wp-operator
COPY ./requirements.txt .
RUN pip3 install -r requirements.txt
COPY . .

# `wp-base` below means the image built from https://github.com/epfl-si/wp-ops/tree/WPN/docker/wp-base
COPY --from=wp-base /wp /wp

ENTRYPOINT [ "python3", "wp-operator.py", "run"]
