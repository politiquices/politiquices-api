cache:
	python generate_caches.py

images:
	mkdir -p assets/images/personalities_small/
	cp -v assets/images/personalities/* assets/images/personalities_small
	mogrify -resize 250x250^ -gravity center -extent 250x250 assets/images/personalities_small/*
	cp -R assets/images/parties ../politiquices-app/public/assets/images/parties
	cp -R assets/images/personalities_small ../politiquices-app/public/assets/images/personalities_small