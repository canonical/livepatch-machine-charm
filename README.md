# Canonical Livepatch Server (Machine Charm)

[![CharmHub Badge](https://charmhub.io/canonical-livepatch-server/badge.svg)](https://charmhub.io/canonical-livepatch-server)
[![Release](https://github.com/canonical/livepatch-machine-charm/actions/workflows/publish_charm.yaml/badge.svg)](https://github.com/canonical/livepatch-machine-charm/actions/workflows/publish_charm.yaml)
[![Tests](https://github.com/canonical/livepatch-machine-charm/actions/workflows/test.yaml/badge.svg?branch=main)](https://github.com/canonical/livepatch-machine-charm/actions/workflows/test.yaml?query=branch%3Amain)

## Description

The Livepatch machine charm is the easiest and the recommended way to deploy Livepatch. This charm installs and configures the Ubuntu Linux Livepatch-ing utility and daemon. Canonical Livepatch patches high and critical linux kernel vulnerabilities, removing the immediate need to reboot to upgrade the kernel,
instead allowing the downtime to be scheduled. It is a part of the Ubuntu Pro offering.

⚠️ For users who want to deploy an entire Livepatch on-prem server (including its dependencies), it is recommended to use the [bundle](https://charmhub.io/canonical-livepatch-onprem) made for this purpose. For more detailed steps on using the bundle, please see the [tutorials](https://ubuntu.com/security/livepatch/docs/livepatch_on_prem/tutorial) on the Livepatch website.

## Usage

The Livepatch server may be deployed using the Juju command line as follows:

```sh
juju deploy canonical-livepatch-server
```

## Integrations

### Database

Livepatch server requires integration with a PostgreSQL charm via the `database` endpoint. As an example, users can deploy a [PostgreSQL](https://charmhub.io/postgresql) database and integrate it with Livepatch as follows:

```sh
juju deploy postgresql
juju integrate canonical-livepatch-server:database postgresql:database
```

There is also an endpoint, named `database-legacy`, which can be used with PostgreSQL charm's legacy endpoint, `db` . But it is strongly recommended that users integrate with the `database` endpoint mentioned earlier. 

## Reverse-proxy

Livepatch provides an endpoint, named `website`, which can integrated with reverse-proxy/load-balancer services that are meant to gate external access, like [HAProxy](https://charmhub.io/haproxy).

As an example, users can integrate this endpoint by using Juju as follows:

```sh
juju deploy haproxy
juju integrate canonical-livepatch-server:website haproxy:website
```

## Documentation

For more detailed instructions on deploying Livepatch server, please see the documentation for this service, available on the [Livepatch website](https://ubuntu.com/security/livepatch/docs).

## Contributing

Please see the [Juju SDK documentation](https://juju.is/docs/sdk) for more information about developing and improving charms and [Contributing](CONTRIBUTING.md) for developer guidance.

## License

The Livepatch machine charm is free software, distributed under the Apache Software License, version 2.0. See [License](LICENSE) for more details.
