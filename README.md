A fully-fledged and continuously running home automation project using <https://pyziggy.github.io>.

## Prerequisites

* pyenv
* rsync 3.2.0+

You can install both using `brew`.

## Bootstrapping an empty project directory for development

**This only works on our local network, where we can connect to the server.**

Make sure, you are in the project directory that you want to set up. Copy and execute the following commands in the terminal.

```
curl -fsSL https://raw.githubusercontent.com/bebump/pyziggy-example/refs/heads/main/remote.json -o remote.json
curl -fsSL https://raw.githubusercontent.com/bebump/pyziggy-example/refs/heads/main/pyziggy-setup -o pyziggy-setup
chmod u+x pyziggy-setup
./pyziggy-setup sync-remote stop
```

This blob will
1. Download the `remote.json` and `pyziggy-setup` files from this repository, into your current working directory.
2. Run the `./pyziggy-setup sync-remote stop` command, which
   1. connects to your service machine specified in the `remote.json` file, and downloads all project files using rsync,
   2. creates a `.venv` directory with a Python 3.12 virtual environment, and installs all dependencies into it using the downloaded `requirements.txt`.

## Working with the project

### Before a development session

```
./download-all-files-from-remote-and-stop-remote-service
```

This command is idempotent.

### During the development session

```
./run-project-locally
```

### After the development session

```
./upload-all-files-to-remote-and-start-remote-service
```

This command is idempotent.
