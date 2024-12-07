# Dockerfile for the image of the OLM controller (“operator's operator”)
#
# ⚠ This Dockerfile needs to be built from the directory above this one!
#
#   cd ..
#   docker build . -f olm/Dockerfile.controller
#
FROM python:3.12-slim

COPY requirements.txt .
RUN pip3 install -r requirements.txt

COPY olm/wpn-olm-controller.py olm/operator.yaml .
RUN set -e -x; \
    ( echo "#!/usr/local/bin/python3"; cat wpn-olm-controller.py ) > /usr/local/bin/wpn-olm-controller ; \
    chmod 755 /usr/local/bin/wpn-olm-controller

CMD ["/usr/local/bin/wpn-olm-controller", "run", "-A"]
