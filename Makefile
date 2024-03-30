cache:
	# generate json files, resulting from SPARQL queries, to be used as cached date loaded when the API is launched
	SPARQL_ENDPOINT='http://127.0.0.1:3030' PYTHONPATH=`pwd`"/src" python src/generate_caches.py

images:
	# generate small images generate from the cacheing script and copies them to the react-app public assets
	mkdir -p assets/images/personalities_small/
	cp -v assets/images/personalities/* assets/images/personalities_small
	mogrify -resize 250x250^ -gravity center -extent 250x250 assets/images/personalities_small/*
	cp -R assets/images/parties ../politiquices-app/public/assets/images/parties
	cp -R assets/images/personalities_small ../politiquices-app/public/assets/images/

build:
	# build a Docker image
	docker build --tag politiquices-api .

production:
	# run the docker image
	echo "Running the API inside the politiquices network and connecting to the jena_sparql container see start_docker.sh"

develop:
	# runs a local
	PYTHONPATH=`pwd`"/src" SPARQL_ENDPOINT='http://127.0.0.1:3030' uvicorn src.main:app --reload

lint:
	black -t py39 -l 120 src
	PYTHONPATH=src pylint src --rcfile=pylint.cfg --ignore=qa_neural_search.py
	flake8 src --config=setup.cfg

typecheck:
	mypy --config mypy.ini src

test:
	PYTHONPATH=src coverage run --rcfile=setup.cfg --source=src -m pytest
	coverage report --rcfile=setup.cfg
