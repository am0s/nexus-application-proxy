# Nexus Application Proxy

Nexus Application Proxy (NAP) is a set of services to aid in exposing
web services trough a single load-balancer/proxy. The proxy is flexible
and supports regular http and https setup as well as ssl termination.

Consist of:
- A load-balancer/proxy using haproxy
- A configuration stored in etcd
- CLI tool for setting up the configuration manually, inspecting it.
- Certbot for generating certificates from letsencrypt and storing
  them in the configuration.
- Docker-gen manager for automatically registering docker containers,
  setting up listeners and targets according to environment variables.

The services are designed to be run in docker containers for easy
management and separation of concern. It also makes it easier to develop
locally.

## etcd

This is the configuration store which every service communicates with
by storing key/value entries. Any etcd setup can be used, the other
containers just needs to be setup with the correct IP/port by passing
the `ETCD_HOST` environment variable.

## Load-balancer / Proxy

The ALB (Application Load Balancer) is a docker container running
haproxy which takes care of reading the configuration from etcd and then
generating a haproxy.cfg file and reloading haproxy.

There can be as many ALB as wanted, each with its own name, but there
is generally only required that one is started.

Start the ALB with

...

## Auto-discover

This service takes care of discovering docker containers and then
register/unregister them when they are started/stopped. It will only
include containers which contain the `VIRTUAL_HOST` environment
variable.

...

## Cerbot

This service periodically checks for domains that needs a certificate
from letsencrypt and starts the certbot to retrieve a new certificate.
It also renews existing letsencrypt certificates which are nearing its
expiry date.

...

## Usage

To use this system there needs to be one etcd service running, then
one or more load balancers. Optionally one service for the certbot
if you intend to use letsencrypt certificates, if you have existing
certificates it is not necessary.

If you intend to expose docker containers the `autodiscover` service
can be used to automatically manage containers.

In addition there is a CLI which can be run manually for displaying
the configuration, registering/unregistering targets and manage
certificates.

The whole system is meant to be run in docker containers on one or more
machines.

### etcd

A simple etcd setup is starting a docker container with:

    docker volume create etcd_data
    docker run --restart=always -v etcd_data:/etcd-data -p 2379:2379 quay.io/coreos/etcd etcd -name etcd0 -advertise-client-urls http://:2379,http://:4001 -listen-client-urls http://0.0.0.0:2379,http://0.0.0.0:4001 -listen-peer-urls http://0.0.0.0:2380 --data-dir=/etcd-data

The IP and port of the must then be passed as `ETCD_HOST` in the other
containers, e.g. if `10.0.1.10` is the IP then pass
`-e ETCD_HOST=10.0.1.10:4001`.

For production it is recommended to use ssl with certificates.

### Load-balancer / Proxy

To run it:

    ...

### Auto-discover

To run it:

    $ docker run -d --name ap-discover -e ETCD_HOST=1.2.3.4:4001 -p 127.0.0.1:1936:1936 -p 80:80 -t am0s/haproxy-discover

Then for each host run the appropriate software for registering docker
services or custom services.

### Certbot

To run it:

    ...

### CLI

To run it:

    ...

### Stats Interface

The haproxy stats interface can be exposed on port 1936. For local
development this is enabled by default.

Open your browser to `http://localhost:1936/_hastats` to view it.

## Development

The easiest way to develop and test this is to run it locally with the
supplied docker-compose.yml file. It will start all required services,
even the etcd service. Run it with:

    docker-compose up

For the docker auto-discover service to work the docker socket must
be mounted into the container by editing the `.env` file and setting:

    DOCKER_SOCKET=/var/run/docker.sock

This currently does not work on Windows, instead set it to:

    DOCKER_SOCKET=./docker0


## Acknowledgements

This code is based on [jwilder/docker-discover](https://github.com/jwilder/docker-discover) but heavily modified.

## License

MIT
