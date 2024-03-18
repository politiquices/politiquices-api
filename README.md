c[![python](https://img.shields.io/badge/Python-3.9-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org)
&nbsp;
![example event parameter](https://github.com/politiquices/politiquices-api/actions/workflows/code_checks.yml/badge.svg?event=pull_request)
&nbsp;
![code coverage](https://raw.githubusercontent.com/politiquices/politiquices-api/coverage-badge/coverage.svg?raw=true)
&nbsp;
[![Checked with mypy](http://www.mypy-lang.org/static/mypy_badge.svg)](http://mypy-lang.org/)
&nbsp;
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

### Backend API for Politiquices.PT 

- Get info for each personality.
- Compute statistics for the Politiquices.PT website.
- Download images associated with each personality, parties.

  
    make cache

Generate thumbnails for each downloaded image.

    make image

Make a Docker image for the API.

    make docker


Run a local instance of the API: http://127.0.0.1:8000/docs

    make develop
