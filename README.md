# Canonical livepatch machine charm

The livepatch machine charm is the easiest and the recommended way to deploy livepatch. This charms installs and configures the Ubuntu Linux Livepatching Utility and Daemon. Canonical Livepatch patches high and critical linux kernel vulnerabilities removing the immediate need to reboot to upgrade the kernel, instead allowing the downtime to be scheduled. It is a part of the Ubuntu Pro offering.

## Usage

```
# deploy livepatch:
juju deploy canonical-livepatch-server
```

## Relations

TBA

## Contributing

Please see the [Juju SDK documentation](https://juju.is/docs/sdk) for more information about developing and improving charms and [Contributing](CONTRIBUTING.md) for developer guidance. Documentation for this service is available on the [livepatch website](https://github.com/ubuntu.com/security/livepatch/docs).

## License

The livepatch machine charm is free software, distributed under the Apache Software License, version 2.0. See [License](LICENSE) for more details.
