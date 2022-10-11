# canonical-livepatch-server

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

## Testing

The Python operator framework includes a very nice harness for testing
operator behaviour without full deployment. Just `run_tests`:

    ./run_tests
