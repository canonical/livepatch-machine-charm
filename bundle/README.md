# Livepatch server on-premises bundle

[![CharmHub Badge](https://charmhub.io/canonical-livepatch-onprem/badge.svg)](https://charmhub.io/canonical-livepatch-onprem)
[![Release](https://github.com/canonical/livepatch-machine-charm/actions/workflows/publish_bundle.yaml/badge.svg)](https://github.com/canonical/livepatch-machine-charm/actions/workflows/publish_bundle.yaml)

This bundle deploys a [Livepatch](https://ubuntu.com/security/livepatch)
on-prem server for serving patches to machines running Livepatch client.

## Bundled applications

The Livepatch server on-prem model consists of the following applications:

 - [HAProxy](https://charmhub.io/haproxy) as reverse-proxy/load-balancer.
 - [Livepatch](https://charmhub.io/canonical-livepatch-server) as the core Livepatch service.
 - [PostgreSQL](https://charmhub.io/postgresql) as database for patch data and machine reports.
 - [Ubuntu-advantage (subordinate)](https://charmhub.io/ubuntu-advantage) to enable Ubuntu Pro subscription. 

## Deployment

For more detailed steps on using this bundle, please see the [tutorials](https://ubuntu.com/security/livepatch/docs/livepatch_on_prem/tutorial) on the Livepatch website.
