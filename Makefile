cache:
	# generate json files, resulting from SPARQL queries, to be used as cached date loaded when the API is launched
	SPARQL_ENDPOINT='http://127.0.0.1:3030' PYTHONPATH=`pwd`"/src" python src/generate_caches.py

images:
	# Portraits are normalised to <wiki_id>.jpg: they are photographs, and a single
	# extension means the API can build the URL from the wiki_id alone instead of
	# reading whatever extension Wikidata used (.jpg/.png/.JPG/.JPEG/.tif coexisted).
	# Alpha is flattened to white first — JPEG has no alpha and would otherwise
	# composite transparent portraits onto black.
	mkdir -p assets/images/personalities_small/
	for f in assets/images/personalities/*; do \
		dest="assets/images/personalities_small/$$(basename $${f%.*}).jpg"; \
		if [ ! -f "$$dest" ]; then \
			echo "resizing $$(basename $$f)..."; \
			magick "$$f" -background white -alpha remove -alpha off \
				-resize 250x250^ -gravity center -extent 250x250 \
				-strip -quality 82 "$$dest"; \
		fi; \
	done
	# rsync --delete rather than cp -R: cp leaves behind files that no longer exist
	# here, and after the move to a single .jpg extension that meant 217 orphans
	# shipping to the web server for nobody.
	echo "mirroring to react app..."
	rsync -a --delete assets/images/parties/ ../politiquices-app/public/assets/images/parties/
	rsync -a --delete assets/images/personalities_small/ ../politiquices-app/public/assets/images/personalities_small/
	echo "done"

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
