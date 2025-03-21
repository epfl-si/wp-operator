# Get the certs

openssl  req -x509 -batch -subj "/CN=wordpresssite-conversion-webhook.wordpress-test.svc" -addext "subjectAltName = DNS:wordpresssite-conversion-webhook.wordpress-test.svc" -nodes -keyout server.key -out server.pem -newkey rsa:2048

