##########################
# Charm related commands #
##########################
.PHONY: build-machine-charm deploy-machine-bundle

# Builds the machine operator charm
build-machine-charm:
	rm -f *.charm
	charmcraft pack --project-dir ./ --verbosity=debug

# Deploys the machine bundle using a locally build charm
deploy-machine-bundle: build-machine-charm
	juju deploy ./bundle/bundle.yaml --overlay ./bundle/machine_overlay.yaml

#####################
# INTEGRATION TESTS #
#####################
.PHONY: test-operator-machine-charm

# Runs tox integration tests against the desired target
integration-test:
	source venv/bin/activate && tox -e integration

# Runs tox integration tests against the desired target
unit-test:
	source venv/bin/activate && tox -e unit 

test: unit-test integration-test
