# OLM packaging for the WordPress Operator

This is what the `olm/` subdirectory is about.

## OLM 20-line explainer

OLM stands for Operator Lifecycle Manager, which is to OpenShift as RPM is to RedHat. Meaning, an over-engineered, verging on obsolete, walled-garden style method and apparatus to install things.

OLM is an [operator's operator's operator](https://factoryfactoryfactory.net/) running inside your [OpenShift](https://en.wikipedia.org/wiki/OpenShift) or [OKD](https://okd.io/) cluster out-of-the-box; that is, it will run your **controller** for you, which will in turn launch one or more instances of your operator (typically one per namespace).

When you present OLM with a so-called **catalog** (a [gRPC](https://en.wikipedia.org/wiki/GRPC) server in a pod that responds to `api.Registry/ListBundles`), it will
1. follow the catalog's pointers to download and inspect **bundles**, which are a series metadata-only Docker images (with no binaries inside — Not suitable for running pods);
2. work out your operator's **channels** from the catalog and bundles. There is generally one bundle per operator version, and channels (which can have names like *production* or *testing*) are in a N:N relationship with them (meaning that a given version may be in more than one channel);
3. display the above in the marketplace GUI thingy, complete with icon, blurb, gamified quality ladder (complete with [scorecard](https://sdk.operatorframework.io/docs/testing-operators/scorecard/) tests embedded in the bundles) etc;
4. once you click on Install, set up one or more [CRDs](https://en.wikipedia.org/wiki/Kubernetes#Custom_resources,_controllers_and_operators), some [RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/) and a **controller** pod — All of the above either embedded or pointed to by a `ClusterServiceVersion` Kubernetes object, whose [/v1alpha1](https://olm.operatorframework.io/docs/concepts/crds/clusterserviceversion/) version suffix (since... 2018) should tell you everything you need to know about the OLM ecosystem;
5. technically your controller then does whatever you want. In particular, and despite what [the official documentation](https://sdk.operatorframework.io/docs/building-operators/) would have you believe, you can write it in any language. You could decide that the controller *is* your operator; however, it is wise to at least read the OLM [best practices](https://sdk.operatorframework.io/docs/best-practices/) once; and evaluate the “standard” design in which your controller launches one instance of the operator per namespace, for fault isolation purposes. **See also:** § “Design Choices for the WordPress OLM controller” below.

The main struggles of packaging your operator for OLM are therefore
- decide on the controller ↔ operator scheme as per the discussion in point 5 above;
- create the `ClusterServiceVersion` object and shoehorn it into a bundle image; which involves something called `operator-sdk`, and its own set of quirks and design mistakes (not the least of which being its tendency to fail silently,  as is fashionable with software written in Golang).

## Developer Instructions

### Requirements


- **An OpenShift or OKD cluster you have kubeadmin permissions to**

  > 💡 As a matter of personal opinion, I think there is very little point in trying to go the “OLM as a service on vanilla Kubernetes” route, as the [official instructions](https://olm.operatorframework.io/docs/getting-started/); that just sounds like a recipe to wrangle bugs and corner cases that don't matter in reality.

  The [instructions over there](https://docs.okd.io/latest/installing/installing_sno/install-sno-installing-sno.html) will help you get a single-node OKD going. ⚠n You should be aware that even a single-node OpenShift deployment (= with only one instance of each pod) clocks in at roughly 100 pods out-of-the-box, so beef up your VM accordingly — We are talking 8 CPUs, 64 Gb RAM, 200 Gb disk.

- **A place to build Docker images from**

  This means an x86_64 machine with Docker installed and 10+ Gb of disk space.
  There most certainly is a way to do it better (`docker buildx`, or `podman something something`); pull requests welcome.

- **An OLM catalog that points to the WordPress operator bundles**

  As per above, the only way for OLM to pick up this here WordPress operator, is to enumerate the bundles out of a gRPC server pod. [The `epfl-si/isas-fsd-catalog` project on GitHub](https://github.com/epfl-si/isas-fsd-catalog/) does exactly that, with all the bells and whistles such as multiple operators with multiple channels, which can overlap in version — All built out of one, fully hermetic, multi-stage `Dockerfile`.

### First deployment

1. `kubectl apply` (or `oc apply`) the `CatalogSource` YAML that comes with your catalog image

   →  As soon as you do that, a pod named something like `isas-fsd-catalog-xxxxx` should pop into the `openshift-marketplace` of your OKD cluster. Make sure it stays up.
2. Install the WordPress operator through the OLM GUI (Operators → OperatorHub)

  → If all goes to plan, a `wordpress-olm-controller-xxxxx-yyyyy` pod should start in namespace `openshift-operators` and likewise transition promptly to `Running` state.

### [Enbugging](https://media.pragprog.com/articles/jan_03_enbug.pdf) / manual testing workflow

1. Make some changes
2. Bump `BUNDLE_VERSION=` line in `Dockerfile.bundle`
3. Build and push the two images (bundle and controller):

   ```shell
   make -C olm bundle-build bundle-push controller-build controller-push
   ```
4. As soon as the `bundle-push` part is complete, you can start rebuilding the catalog image in another window.
5. As soon as said catalog image is pushed into the registry, kill the `isas-fsd-xxxxx` pod in the `openshift-marketplace` of your OKD cluster, to force OLM to reload the catalog
5. Wait for all the magical OLM things to happen, and make the new `ClusterServiceVersion` available for install.

  💡 Assuming you installed the operator successfully before; and you selected “Automatic” upgrades; the controller upgrade should start without any further intervention on your part.
6. Test out your changes

#### Shorter version

The following shortcut may help you achieve more test cycles per unit of time:

1. Make sure the `imagePullPolicy: Always` line in `controller-deployment-and-rbac.yaml` is active (not commented out)
2. Do a “long” cycle as per above, to make sure that the controller's `Deployment` object contains that line
3. Overwrite just the controller image without bumping its `BUNDLE_VERSION=`:

   ```shell
   make -C olm controller-build controller-push
   ```
4. Kick the controller pod, so that the next one reloads from the new build (same version number) of the image.

⚠ The short version is *not* appropriate whenever you

- need to update objects that are part of the bundle (and that the WordPress OLM controller therefore doesn't control); such as the CRD and the controller's own `Deployment` and RBAC objects
- need to effect changes on OpenShifts that you don't control (such as that production cluster that you *don't* have cluster-admin access to, which got you looking into OLM in the first place). Obviously, OLM will only pick up your changes automatically if you produce a new revision of both bundle and controller images, and reference the former in the proper channel of the catalog.

### Tips and Tricks

- If you want a `kubectl` CLI in your controller image for debugging purposes (e.g. to test out your RBAC), comment out the relevant line in `Dockerfile.bundle` and run a short enbugging cycle as per above

# Design Choices for the WordPress OLM controller

## “Standard” three-stage design

We decided to go with three distinct images for the bundle, controller and operator; despite the latter two being written in the same language and ([almost](https://github.com/tomplus/kubernetes_asyncio)) the same framework.

Pros of having three distinct images:

- Putting the bundle into its own image, minimizes the amount of useless megabytes the OLM operator (“operator's operator's operator”) has to wade through to do its job — To the tune of several orders of magnitude optimizations in memory and network resource consumption on behalf of OLM.
- Using two distinct images for the controller and the operator, allows them to have independent release schedules. In particular, using a `:latest` tag for the operator image will Just Work.


Cons of having three distinct images:

- Opting for the same image for both the controller and the operator, would have let us alias the Python layers between them; which would have helped the whole thing scale down. (However dubious an endeavor “scaling down” might be on OpenShift, all things considered.)

Pros of having two distinct pods for the operator and the controller:

- **Fault isolation.** The only thing the controller knows or cares about `WordPressSite`s, is whether they exist or not in a given namespace; meaning that its “attack surface,” so to speak, is quite narrow. Any and all bugs in the operator that would cause it to malfunction or crash on certain `WordPressSite` objects, only impact the one namespace in which said `WordPressSite`s exist.
- **Operator enbuggability.** Since the operator needs not operate on the “big” (non-namespaced) objects (anymore), it can make do with a fairly restricted set of RBAC permissions; in fact, it will typically require *less* privileges than those wielded by a typical human having access to the cluster. As a consequence, it is quite possible, in an emergency situation, to scale the operator `Deployment` to 0 and run the operator from one's workstation; more on that below. This would be quite a bit more of a pain to do if the operator, being also the controller, lived in one of the `openshift-foo` namespaces.

Cons of having two distinct pods for the operator and the controller:

- Resource frugality, see above
- Complexity for the developer (hence, most likely, why you are reading this).
    - For each of the Kuberenetes objects that need created (including some of them that exist *only* to support the controller itself), we need to carefully pick which of the three moving parts (to wit: OLM, our controller, or our operator) will be in charge of creating and/or maintaining it
    - And we need proper RBAC for the controller and operator to fulfill their jobs; Kubernetes RBAC being its own headache in and of itself (and bringing along [its own set of design flaws](http://www.erights.org/elib/capability/duals/myths.html)).

## No `WordPressOperator` CRD / per-namespace operator on first `WordPressSite`

Whereas some operators packaged for OLM, such as [MariaDB](https://github.com/mariadb-operator/mariadb-operator-helm), follow RedHat's “best” practices and define a CRD specifically for OLM (i.e. [`MariaDBOperator`](https://github.com/mariadb-operator/mariadb-operator-helm/blob/3a432b604763601fcbb468af241a1d21426ca1d2/config/crd/bases/helm.mariadb.mmontes.io_mariadboperators.yaml)); we decided not to, and use `WordPressSite` itself as the “owned” CRD in the OLM sense.

The WordPress OLM controller watches all `WordPressSite` objects cluster-wide. Whenever the first of its kind gets created in a given namespace, the controller launches the operator in that namespace. Conversely, said operator will be destroyed after the last `WordPressSite` is deleted — and we do mean “after”, i.e. [Kubernetes' destruction ordering features](https://kubernetes.io/docs/concepts/overview/working-with-objects/finalizers/) are leveraged to ensure that the operator has enough time to perform orderly cleanup (i.e. ancillary MariaDB `Database`s, `User`s etc), before being destroyed itself.

Pros:

- makes the system simpler to reason about from the perspective of `WordPressSite` producers; they are in a position to forget about OLM altogether

Cons:

- Deviates from best practices, and therefore from least astonishment

## The controller creates and destroys; it doesn't reconcile

Even when wielding cluster-admin, most objects in your OpenShift cluster only *appear* to be editable. After you are done with e.g. `kubectl edit` though, some kind of operator-this or controller-manager-that, lurking behind the scenes, will most likely rush to revert your changes within a few seconds.

Not so with the WordPress OLM controller. It will *not* revert your changes on the objects it manages, and deliberately so. This lets you do “enbuggy” things such as

- stop the operator pod in order to run it from your workstation instead (with debugger, `strace(1)` and whatnot);
- tweak the operator RBAC with `kubectl apply` until it stops complaining (and only then, rebuild and repush); etc.

(💡 This “pattern” in OpenShift of reconciling any and all “deviant” objects is the reason, as seen above, why you have to go through the proper channels so to speak, to set `imagePullPolicy: Always` on the controller pod. Feel free to try a straight `kubectl edit deployment` instead!)

## Kopf

Notwithstanding the author's own [claim](https://github.com/nolar/kopf?tab=readme-ov-file#kubernetes-operator-pythonic-framework-kopf), Kopf is *not* a Pythonic framework: rather, it sort of stands above and to the side of the usual Pythonic stuff. Its admittedly admirable (and effective!) design traits — such as dependency injection, behind-the-scenes (too-much-)magic, and carefully researched names for every internal nook and cranny — align it more with the Ruby-on-Rails mindset than with Python. However, Kopf is by far the most flexible option to write controllers and operators in Python.

Pros:

- stipulations such as “the controller creates and destroys; it doesn't reconcile”, as seen in the previous §, really are as simple to implement as they sound.

Cons:

- debugging can prove challenging — to put it politely. [This one](https://github.com/epfl-si/wp-operator/commit/baed082f97fb3bc67ec9fd41b668bfb68c818303), for instance, required pulling out [`export SSLKEYLOGFILE` and Wireshark](https://wiki.wireshark.org/TLS) just *as an opener* so as to figure out *where* to put the `debugpy` breakpoint in Kopf's source code — And even then, we were lucky enough to have full stack traces available thanks to `kubernetes_asyncio` (See next §.)

## `kubernetes_asyncio` vs. `kubernetes`

As noted in the previous §, using Python's new async/await style is required for [full stack trace debuggability](https://kopf.readthedocs.io/en/stable/async/#async-await). Although this is more of a point for `../README.md`, we have yet to convert much of the operator code to async, due to

- The operator's [leader election](https://kubernetes.io/docs/concepts/cluster-administration/coordinated-leader-election/) feature, which we better have if we want people to start it from their workstation willy-nilly (as per § above), [being unavailable in `kubernetes_asyncio`](https://github.com/tomplus/kubernetes_asyncio/issues/297);
- Lack of time and practice with Python AsyncIO for the rest of the operator logic — Pull requests welcome.
