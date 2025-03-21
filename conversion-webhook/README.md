# `WordpressSite` v1 → v2 conversion webhook

This directory hosts a small program that supports the migration of the `spec.wordpress.plugins` field from being an array of string (in v1), to being a dict (in v2).

The mechanism is [Kubernetes' standard conversion webhook feature](https://kubernetes.io/docs/tasks/extend-kubernetes/custom-resources/custom-resource-definition-versioning/), with a small TypeScript server. The policy is the `convertWordpressSite` function in `server.ts` which is quite short and easy to review.
