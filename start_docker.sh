#/bin/bash
docker container stop politiquices-api
docker container rm politiquices-api
docker build . -t politiquices-api
PROTOCOL="HTTP://"
IP_ADDRESS=`docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' jena_sparql`
PORT="3030"
PROTOCOL_IP="$PROTOCOL$IP_ADDRESS:$PORT"
docker run -dit --name politiquices-api --net politiquices --env SPARQL_ENDPOINT=$PROTOCOL_IP -p 8000:8000  -v .:/app politiquices-api

