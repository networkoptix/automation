# Description
Docker image for Workflow Robocat Gitlab Bot who is designated to automate the Merge Request merging
routine and enforce some workflow rules..

More info: https://networkoptix.atlassian.net/wiki/spaces/SD/pages/1486749741/Automation+Workflow+Police+bot

# Requirements
  - `python-gitlab.cfg` should be mounted to `/etc/python-gitlab.cfg` in container.
Example maybe found at bots/robocat/python-gitlab.cfg.example.
NOTE: Field `private_token` must be set to the token of user whom issues will be assigned to.
- .ssh directory with keys for access to the repo should be mounted to
/home/workflow-robocat/.ssh.
- `config.yaml` file with configuration options should be mounted to `/workdir/config.yaml` in
container.
NOTE: Field `password` must be set to the actual password of the user from the field `login`.

The directories must have proper UID & GID, default 1000:1000,
the UID & GID can be configured at image build time.

# Parameters
Run: `./robocat.app --help`

# Building docker image locally
To build docker image locally (without CI), run the following command from the repo root directory:
`docker build -f bots/robocat/Dockerfile -t workflow-robocat --build-arg GIT_COMMIT=$(git log -1 --format=%h) .`

# Recommended example
Run in docker:

```
docker run -it \
    -v ~/.python-gitlab.cfg:/etc/python-gitlab.cfg \
    -v ~/.config/workflow-robocat/config.yaml:/workdir/config.yaml \
    -v ~/.ssh:/home/workflow-robocat/.ssh \
    -v git_data:/var/workflow_robocat \
    workflow-robocat -p 2 --log-level=DEBUG
```

# Development notices
For development it is necessary to set up environment variable `PYTHONPATH`. It must contain
`<repo_directory>/automation_tools` and `<repo_directory>/bots/robocat`. If VS Code (with Python
extension) or PyCharm is used as IDE, this variable should be set automatically by ".env" file in
the root of the repo directory.
