# Simple installation of Kopf, source : https://kopf.readthedocs.io/en/latest/walkthrough/starting/
import kopf
import logging

@kopf.on.create('wordpresssites')
def create_fn(body, **kwargs):
    logging.info(f"A handler is called with body: {body}")