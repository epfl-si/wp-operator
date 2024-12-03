# This container won't work in a development environnement: it need to be
# deployed in the Kubernetes cluster and have to access this node's path
# `/var/run/secrets/kubernetes.io/serviceaccount/token` in order to access the
# Kubernetes's API.
# See https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/

FROM ubuntu:jammy

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get -qy update
RUN apt-get --no-install-recommends -qy install \
        curl \
        git \
        jq \
        patch \
        php-cli \
        php-mysql \
        python3 \
        python3-pip \
        unzip \
     && rm -rf /var/lib/apt/lists/*; # from 1.12GB to 869MB

RUN mkdir -p /srv/wp-operator
WORKDIR /srv/wp-operator
COPY ./requirements.txt .
RUN pip3 install -r requirements.txt
COPY . .

# The WordPress operator needs a valid WordPress installation that we retreive
# from our "wp-base" image, which stands on quay-its.epfl.ch/svc0041/wp-base.
# TODO: please note the "wpn-base" instead of "wp-base" for temporary comfort.
COPY --from=wpn-base /wp /wp

ENTRYPOINT [ "python3", "wpn-operator.py", "run"]
