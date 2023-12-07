# Livepatch server on-premises bundle

This juju bundle deploys a [livepatch](https://ubuntu.com/security/livepatch)
server for serving patches to machines running livepatch client.

## Model

The livepatch server on-premises model for machines consists of 4 applications:
 - HAProxy 
 - Livepatch
 - PostgreSQL
 - Ubuntu-advantage (subordinate)


Postgresql stores patch data and machine reports. 
The HAProxy charm handles providing a reverse-proxy to the server units.

## Deployment

For usage on this bundle, please see [here](https://ubuntu.com/security/livepatch/docs/livepatch_on_prem/tutorial/Getting started with Livepatch and LXD)

