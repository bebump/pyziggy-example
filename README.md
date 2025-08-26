A fully-fledged and continously tested home automation project using <https://pyziggy.github.io>.

## Bootstrapping the project directly from the home automation server

You need the following prerequisites

* rsync 3.2.0+
* pyenv

You can install both using `brew`.

This approach will not initialize a git repository in your project directory.

1. Create a directory where you want to have the home automation project.
2. Download `remote.json` and `pyziggy-setup` into that directory. Make sure the latter is executable.
3. Run `./pyziggy-setup sync-remote stop`. This downloads all project files from the server and stops the pyziggy service running there. This is to ensure that the remote service does not interfere with running the project locally.
4. Run `./pyziggy-setup setup`. This will set up a Python virtual environment and install the required dependencies.

Once you're done with the modifications, you can run `./pyziggy-setup sync-remote start main.py` to upload all modified files to the server and start the service again.
