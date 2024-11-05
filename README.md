# EPFL Kubernetes WordPress Operator

![EKWO Logo](https://github.com/epfl-si/wp-operator/blob/main/images/WPO-no-bg.png?raw=true)

This is the code for the Kubernetes WordPress Operator used at [EPFL].

We ([ISAS-FSD]) are managing roughly 1,000 WordPress sites, all consolidated
under one domain, <https://www.epfl.ch>.

While we would be happy for you to give it a try, this is not an Operator that
you can use "off-the-shelf" within your cluster. First, it needs a fine-tuned
WordPress image that contains all the plugins your users are allowed to use.
Then, you have to understand that the secrets needed by "wp-config.php" are
managed within the Nginx configuration to be passed to PHP-FPM as FastCGI
parameters (`fastcgi_param` directive). A homemade entrypoint takes care of the
loading of the WordPress framework without a proper `wp-config.php`, so what
we can serve 1 to many WordPress sites using the very same image. Last but not
least, you will need to dive into some PHP scripts that manage the installation
/ configuration of the site, themes and plugins through options in the site's
database.

This operator is built with [Kopf (Kubernetes Operators Framework)] and rely on
the [MariaDB Operator].

A `make up` command in our development environment ([wp-dev]) should clone
everything needed to get started, including this repo and [wp-ops], which
contains Ansible configuration as code. The operator is meant to deploy the
[WordPressSite](./WordPressSite-crd.yaml) Custom Resource Definition by itself.


## Setup

### Locally

To make it work on your device, follow these steps:

1. Make sure you have Python3 installed
1. Install all the dependencies using `pip install -r requirements.txt`
1. If outside the EPFL network, check additional steps
1. Run the operator using `make operator`

#### Additional steps

Whenever outside the EPFL network, you will need to:

1. Install [KubeVPN]
1. Connect the VPN to your cluster using `kubevpn connect`
1. If you are on Linux → make sure to run these commands:
    ```bash
    resolvectl dns utun0 $(kubectl get -n kube-system \
    service/rke2-coredns-rke2-coredns \
    -o jsonpath='{$.spec.clusterIP}')
    NAMESPACE=wordpress-test
    resolvectl domain utun0 $NAMESPACE.svc.cluster.local \
    svc.cluster.local cluster.local
    ```
1. Quickly check that your VPN is _connected_ using `kubevpn status`

### In a Pod

This repository contains the [Dockerfile](./Dockerfile) and an example
([operator.yaml](./operator.yaml)) to deploy it in a cluster. Please note that
our deployment is done by Ansible, so dive into [wp-ops] to find the latest
version.


## Contributing

If you want to contribute to this repository, please read the [CONTRIBUTING.md](CONTRIBUTING.md) file.

[EPFL]: https://www.epfl.ch
[ISAS-FSD]: https://go.epfl.ch/isas-fsd
[Kopf (Kubernetes Operators Framework)]: https://kopf.readthedocs.io
[MariaDB Operator]: https://github.com/mariadb-operator/mariadb-operator
[wp-dev]: https://github.com/epfl-si/wp-dev
[wp-ops]: https://github.com/epfl-si/wp-ops
[KubeVPN]: https://www.kubevpn.cn/
