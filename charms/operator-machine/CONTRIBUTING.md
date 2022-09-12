# operator-machine

## Developing

Create and activate a virtualenv with the development requirements:

    virtualenv .venv
    source venv/bin/activate
    pip install -r requirements-dev.txt -r requirements-test.txt -r requirements.txt

Next, in VSCode press `ctrl + shift + p` and type `python interpreter`.

Select `select interpreter`.

Select `enter interpreter path`.

Provide the path from your local .venv to the absolute path of:
`<.venv location>/bin/python3`

Activate this environment.

## Code overview

TEMPLATE-TODO:
One of the most important things a consumer of your charm (or library)
needs to know is what set of functionality it provides. Which categories
does it fit into? Which events do you listen to? Which libraries do you
consume? Which ones do you export and how are they used?

## Intended use case

TEMPLATE-TODO:
Why were these decisions made? What's the scope of your charm?

## Roadmap

If this Charm doesn't fulfill all of the initial functionality you were
hoping for or planning on, please add a Roadmap or TODO here

## Testing

The Python operator framework includes a very nice harness for testing
operator behaviour without full deployment. Just `run_tests`:

    ./run_tests
