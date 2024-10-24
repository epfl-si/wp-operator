# Kubernetes WordPress Operator - EPFL

Hello there, if you are reading this it means that you want to know more
about this repository, so let's get started!


## Where am I?

This repository is for the `Kubernetes WordPress Operator` for the `WordPress
Next` project from [ISAS-FSD].
It was initiated in sept-oct 2024 during the "TPI blanc" of [Azecko].


## What's a Kubernetes Operator?

In simple terms, generally what a Kubernetes Operator does ist that he watches
the Kubernetes cluster and wait for changes, creation, deletion, etc...
When he detects something, he can for exemple creates a Kubernetes pod,
delete one, create some configuration, etc...


## And what about this specific one?

The objective of this Kubernetes operator is simple.
A kind `WordpressSite` has been defined in `WordPressSite-crd.yaml`. It
represents, as it says, a WordPress site.
When a new `kind: WordPressSite` is detected by the operator, it should create
everything that the website needs to work correctly.

At the moment where I'm writing this (October 3rd, 2024), this means:
  - a Database
  - a User
  - a Secret (for the created User)
  - a Grant (to give access to the Database to the User)
  - setting up the database (creating all the tables, setting the theme, ...
    using a PHP script)


## Setup

To make it work on your device, follow these steps:
1. Make sure you have Python installed
2. Install all the dependencies using `pip install -r requirements.txt`
3. Be sure that you have applied the CRD (Custom Resource Definition) (`kubectl
   apply -f WordPressSite-crd.yaml`)
4. Install [KubeVPN]
5. Connect the VPN to your cluster using `kubevpn connect`
6. If you are on Linux → make sure to run these commands:
    ```bash
    resolvectl dns utun0 $(kubectl get -n kube-system \
    service/rke2-coredns-rke2-coredns \
    -o jsonpath='{$.spec.clusterIP}')

    NAMESPACE=wordpress-test       # par exemple
    resolvectl domain utun0 $NAMESPACE.svc.cluster.local \
    svc.cluster.local cluster.local
    ```
7. Quickly check that your VPN is _connected_ using `kubevpn status`
8. Run the operator using `kopf run wpn-kopf.py`
   - If you want more logs, you can run it with the `--verbose` parameter


## What's next?

This operator has still a(lot) of work to do, here's some known issues,
features, backlog, ...

- [ ] Quotes in site name / tagline, e.g. `Nicolas's site`, are not escaped properly.
- [ ] We need to have a way to make the operator manage Ingresses / Deployment to balance the loads / the numbers of site per pods
- [ ] As for the Ingresses and Deployments, same have to happen with MariaDB (the database server)
- [ ] We have to manage the languages (which could be changed by the users, so this imply some knowledges of the modification made at user level, see next point)
- [ ] We need to have some sort of cron task that read the actual configuration, i.e. language, that are active on a site and write thoses in the kubernetes object (status / annotation)
- [ ] The operator has to create the Databases backup/restore
- [ ] The life cycle of a WordPressSite has to be fully managed by the operator: introduce a thombstone/archive status that can be revived, duplicate a site
- [ ] The CRD should have more filter field (the one that are shown on the `kubectl get wp` output), such as `path`, etc
- [ ] wp-veritas (a clickable interface to manage WordPress sites)


## Contributing

If you want to contribute to this repository, please read the [CONTRIBUTING.md](CONTRIBUTING.md) file.

[ISAS-FSD]: https://search.epfl.ch/?filter=unit&q=ISAS-FSD
[Azecko]: https://github.com/Azecko/
[KubeVPN]: https://www.kubevpn.cn/
