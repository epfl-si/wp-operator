# Dockerfile for the image of the OLM controller (“operator's operator”)
#
# ⚠ This Dockerfile needs to be built from the directory above this one!
#
#   cd ..
#   docker build . -f olm/Dockerfile
#
FROM python:3.12-slim

COPY requirements.txt .
RUN pip3 install -r requirements.txt

COPY olm/wp-olm-controller.py operator-namespaced.yaml operator-non-namespaced.yaml .
RUN set -e -x; \
    ( echo "#!/usr/local/bin/python3"; cat wp-olm-controller.py ) > /usr/local/bin/wp-olm-controller ; \
    chmod 755 /usr/local/bin/wp-olm-controller

## Uncomment the following line if you want to test out your RBAC live:
# COPY --from=bitnami/kubectl:latest /opt/bitnami/kubectl/bin/kubectl /usr/local/bin/kubectl

CMD ["/usr/local/bin/wp-olm-controller", "run", "-A"]
