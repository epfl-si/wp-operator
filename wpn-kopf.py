# Simple installation of Kopf, source : https://kopf.readthedocs.io/en/latest/walkthrough/starting/
# WARNING : In the case of this project, it is normal that this code does not do what we want.
import kopf
import logging

@kopf.on.create('ephemeralvolumeclaims')
def create_fn(body, **kwargs):
    logging.info(f"A handler is called with body: {body}")