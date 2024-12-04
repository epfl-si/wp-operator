# IMAGE_TAG_BASE defines the docker.io namespace and part of the image name for remote images.
IMAGE_TAG_BASE ?= quay-its.epfl.ch/svc0041/wordpress-olm-controller

# VERSION defines the project version for the bundle.
# Update this value when you upgrade the version of your project.
# To re-generate a bundle for another specific version without changing the standard setup, you can:
# - use the VERSION as arg of the bundle target (e.g make bundle VERSION=0.0.2)
# - use environment variables to overwrite this value (e.g export VERSION=0.0.2)
VERSION ?= 0.0.1

.PHONY: all
all: controller-build

#############################################################################
##@ General

# The help target prints out all targets with their descriptions organized
# beneath their categories. The categories are represented by '##@' and the
# target descriptions by '##'. The awk commands is responsible for reading the
# entire set of makefiles included in this invocation, looking for lines of the
# file as xyz: ## something, and then pretty-format the target and help. Then,
# if there's a line with ##@ something, that gets pretty-printed as a category.
# More info on the usage of ANSI control characters for terminal formatting:
# https://en.wikipedia.org/wiki/ANSI_escape_code#SGR_parameters
# More info on the awk command:
# http://linuxcommand.org/lc3_adv_awk.php

.PHONY: help
help: ## Display this help.
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z_0-9-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

#############################################################################
##@ Building the main image

# Image URL to use all building/pushing image targets
IMG ?= $(IMAGE_TAG_BASE):v$(VERSION)

_dependencies_from_dotdot = requirements.txt \
	operator.yaml
_docker_build_reqs = $(patsubst %,controller-build-tmp/%,$(_dependencies_from_dotdot))
$(_docker_build_reqs): controller-build-tmp/%: ../%
	@mkdir $(dir $@) 2>/dev/null || true
	cp $< $@

.PHONY: controller-build
controller-build: $(_docker_build_reqs) ## Build the OLM controller docker image.
	docker build -t ${IMG} .

.PHONY: controller-push
controller-push: ## Push the OLM controller docker image.
	docker push ${IMG}


#############################################################################
##@ Building the bundle image (which holds the OLM catalog info)

CONTROLLER_IMG ?= $(shell echo $(IMG) \
  | sed 's|quay-its.epfl.ch|anonymous.apps.t-ocp-its-01.xaas.epfl.ch|')
_subst_controller_image := sed -e 's|^\#\( *image: \)controller:latest| \1 $(CONTROLLER_IMG)|'

BUNDLE_GEN_FLAGS ?=  --version $(VERSION) $(BUNDLE_ADDITIONAL_FLAGS)

bundle-tmp/manifests/clusterserviceversion.yaml: \
  clusterserviceversion-tmpl.yaml \
  controller-deployment-and-rbac.yaml
	install -d $(dir $@)
	rm -rf bundle-tmp/csv-tmp; mkdir -p bundle-tmp/csv-tmp

	set -e -x; for file in $^ ; do cat $$file ; echo "---"; done | \
	    $(_subst_controller_image) | \
	    ( yq . || cat ) | \
	(cd bundle-tmp/csv-tmp; operator-sdk generate bundle \
	        --package wordpress-operator \
	        --verbose --output-dir . $(BUNDLE_GEN_FLAGS))

	cp $$(find bundle-tmp/csv-tmp/manifests/ -name *.clusterserviceversion.yaml) $@

# Some sanity checks against the produced ClusterServiceVersion - If
# your build fails here, check for syntax errors in your source YAML,
# or name mismatches with respect to what `operator-sdk generate
# bundle` expects:
	if ! grep ISAS-FSD $@ >/dev/null; then exit 200; fi
	if grep 'deployments: \[\]' $@  >/dev/null; then exit 201; fi

	@rm -rf bundle-tmp/csv-tmp

#############################################################################
##@ Cleanup

.PHONY: clean
clean: ## Remove intermediate files and built Docker images
	rm -rf controller-build-tmp bundle-tmp
	docker rmi $(IMG) || true
