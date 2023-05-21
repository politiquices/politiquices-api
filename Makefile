cache:
	# generate json files, resulting from SPARQL queries, to be used as cached date loaded when the API is launched
	python generate_caches.py

images:
	# generate small images generate from the cacheing script and copies them to the react-app public assets
	mkdir -p assets/images/personalities_small/
	cp -v assets/images/personalities/* assets/images/personalities_small
	mogrify -resize 250x250^ -gravity center -extent 250x250 assets/images/personalities_small/*
	cp -R assets/images/parties ../politiquices-app/public/assets/images/parties
	cp -R assets/images/personalities_small ../politiquices-app/public/assets/images/personalities_small

build:
	# build a Docker image
	docker build --tag politiquices-api .

production:
	# run the docker image
	docker run -d --env es_haystack='http://es_haystack:9202' --env sparql_endpoint='http://jena_sparql:3030' --name politiquices-api --net politiquices -p 127.0.0.1:8000:8000 politiquices-api

	
development:
	# runs a local
	sparql_endpoint='http://127.0.0.1:3030' es_haystack='http://127.0.0.1:9202' python main.py


lint:
	black -t py39 -l 120 src
	PYTHONPATH=src pylint src --rcfile=pylint.cfg
	flake8 src --config=setup.cfg
	mypy --config mypy.ini .

test:
	coverage run --rcfile=setup.cfg --source=src -m pytest
	coverage report --rcfile=setup.cfg