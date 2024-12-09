.PHONY: help
help: ## Display this help.
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z_0-9-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

BUNDLE_VERSION := $(shell sed -ne 's/ARG BUNDLE_VERSION=\(.*\)/\1/p' < Dockerfile.bundle)

##@ Docker images

_image_stem := quay-its.epfl.ch/svc0041/wordpress-olm
_bundle_docker_image := $(_image_stem)-bundle:v$(BUNDLE_VERSION)
_controller_docker_image := $(_image_stem):v$(BUNDLE_VERSION)

.PHONY: bundle-build
bundle-build: ## Build the OLM bundle (metadata) image
	cd ..; docker build -t $(_bundle_docker_image) -f olm/Dockerfile.bundle .

.PHONY: controller-build
controller-build: ## Build the OLM controller image
	cd ..; docker build -t $(_controller_docker_image) -f olm/Dockerfile .

.PHONY: bundle-push
bundle-push: ## Push the OLM bundle image
	docker push $(_bundle_docker_image)

.PHONY: controller-push
controller-push: ## Push the OLM controller image
	docker push $(_controller_docker_image)
