FROM python:3.12-slim

COPY controller-build-tmp/requirements.txt .
RUN pip3 install -r requirements.txt

COPY wpn-olm-controller.py controller-build-tmp/operator.yaml .
RUN set -e -x; \
    ( echo "#!/usr/local/bin/python3"; cat wpn-olm-controller.py ) > /usr/local/bin/wpn-olm-controller ; \
    chmod 755 /usr/local/bin/wpn-olm-controller

CMD ["/usr/local/bin/wpn-olm-controller", "run", "-A"]
