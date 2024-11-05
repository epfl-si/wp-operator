SHELL := /bin/bash

NAMESPACE = wordpress-test
WP_OPERATOR_IMAGE_NAME = epflsi/wp-operator
WP_OPERATOR_IMAGE_TAG ?= latest
REGISTRY = quay-its.epfl.ch/svc0041/wp-operator

.PHONY: help
## Print this help
help:
	@echo "$$(tput setaf 2)Available rules:$$(tput sgr0)";sed -ne"/^## /{h;s/.*//;:d" -e"H;n;s/^## /---/;td" -e"s/:.*//;G;s/\\n## /===/;s/\\n//g;p;}" ${MAKEFILE_LIST}|awk -F === -v n=$$(tput cols) -v i=4 -v a="$$(tput setaf 6)" -v z="$$(tput sgr0)" '{printf"- %s%s%s\n",a,$$1,z;m=split($$2,w,"---");l=n-i;for(j=1;j<=m;j++){l-=length(w[j])+1;if(l<= 0){l=n-i-length(w[j])-1;}printf"%*s%s\n",-i," ",w[j];}}'

operator:
	python3 wpn-kopf.py run -n $(NAMESPACE) -- --db-host mariadb-min.$(NAMESPACE).svc

.PHONY: image
image: build tag push

.PHONY: build
build:
	docker build -t $(WP_OPERATOR_IMAGE_NAME) .

.PHONY: tag
tag:
	@echo Tagging image \"$(WP_OPERATOR_IMAGE_NAME)\" to \"$(REGISTRY):$(WP_OPERATOR_IMAGE_TAG)\".
	@if [ $(WP_OPERATOR_IMAGE_TAG) = 'latest' ]; then \
		echo Use \'WP_OPERATOR_IMAGE_TAG=2024-001 make tag\' to change the tag to something else.; \
	fi
	docker tag $(WP_OPERATOR_IMAGE_NAME) $(REGISTRY):$(WP_OPERATOR_IMAGE_TAG)

.PHONY: push
push:
	docker push $(REGISTRY):$(WP_OPERATOR_IMAGE_TAG)

