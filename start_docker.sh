#/bin/bash
docker container stop politiquices-api
docker container rm politiquices-api
PROTOCOL="HTTP://"
IP_ADDRESS=`docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' happy_cartwright`
PORT="3030"
PROTOCOL_IP="$PROTOCOL$IP_ADDRESS:$PORT"
docker run -dit --env SPARQL_ENDPOINT=$PROTOCOL_IP --name politiquices-api -p 127.0.0.1:8000:8000 politiquices-api