.PHONY: help
## Print this help
help:
	@echo "$$(tput setaf 2)Available rules:$$(tput sgr0)";sed -ne"/^## /{h;s/.*//;:d" -e"H;n;s/^## /---/;td" -e"s/:.*//;G;s/\\n## /===/;s/\\n//g;p;}" ${MAKEFILE_LIST}|awk -F === -v n=$$(tput cols) -v i=4 -v a="$$(tput setaf 6)" -v z="$$(tput sgr0)" '{printf"- %s%s%s\n",a,$$1,z;m=split($$2,w,"---");l=n-i;for(j=1;j<=m;j++){l-=length(w[j])+1;if(l<= 0){l=n-i-length(w[j])-1;}printf"%*s%s\n",-i," ",w[j];}}'

WEBHOOK_IMAGE_NAME = quay-its.epfl.ch/svc0041/wordpresssite-conversion-webhook
WEBHOOK_IMAGE_TAG ?= latest


.PHONY: build
## Build the conversion webhook image
build:
	docker build -t $(WEBHOOK_IMAGE_NAME):$(WEBHOOK_IMAGE_TAG) .

.PHONY: push
## Push the image using `REGISTRY` and `WEBHOOK_IMAGE_TAG`
push:
	docker push $(WEBHOOK_IMAGE_NAME):$(WEBHOOK_IMAGE_TAG)
