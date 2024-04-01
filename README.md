[![python](https://img.shields.io/badge/Python-3.9-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org)
&nbsp;
![example event parameter](https://github.com/politiquices/politiquices-api/actions/workflows/code_checks.yml/badge.svg?event=pull_request)
&nbsp;
![code coverage](https://raw.githubusercontent.com/politiquices/politiquices-api/coverage-badge/coverage.svg?raw=true)
&nbsp;
[![Checked with mypy](http://www.mypy-lang.org/static/mypy_badge.svg)](http://mypy-lang.org/)
&nbsp;
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

### Backend API for Politiquices.PT 

### 1. Cache contents

This will get info for each personality and parties, compute statistics for the Politiquices.PT and it's parties and entities and download images associated with each personality
This will save everything under a `assets` directory

    make cache


Now let's generate thumbnails for each downloaded image. This will copy all the images to `politiquces-app/public` so that it's part of the static html data of the website

    make images


Make a Docker image for the API.

    make build

Run a local instance of the API: http://127.0.0.1:8000/docs

    make develop