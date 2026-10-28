# Dev container

This dev container is operator infrastructure for the trusted launcher. It uses the Docker-in-Docker feature so the launcher can build and run episode containers. That daemon stays inside the dev container.

Do not mount the Docker socket into the target or the bridge. `docker-compose.yml` publishes no ports and has no socket mount. The target container must not receive the daemon socket, a published port, or a provider credential.

Python in the image is 3.12, which satisfies `requires-python >= 3.11.4`. `post-create.sh` installs uv and syncs `uv.lock`.
