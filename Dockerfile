FROM docker-registry.default.svc:5000/wwp-test/wp-base

RUN mkdir -p /srv/wp-operator
WORKDIR /srv/wp-operator
COPY ./requirements.txt .
RUN pip3 install --break-system-packages -r requirements.txt
COPY . .

ENTRYPOINT [ "python3" ]
CMD [ "wpn-kopf.py", "run", "--", "--db-host", "mariadb-min.wordpress-test.svc", "--wp-dir=/wp/6" ]