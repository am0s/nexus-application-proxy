haproxy-discover is a service discovery system for haproxy. It reads
the configuration for the backends from etcd and generates a new
haproxy.cfg from this.

### Usage

To run it:

    $ docker run -d --name haproxy-discover -e ETCD_HOST=1.2.3.4:4001 -p 127.0.0.1:1936:1936 -p 80:80 -t am0s/haproxy-discover

Then for each host run the appropriate software for registering docker
services or custom services.

### Stats Interface

The haproxy stats interface is exposed on port 1936.  Open your browser to `http://localhost:1936` to view it.

### Acknowledgements

This code is based on [jwilder/docker-discover](https://github.com/jwilder/docker-discover) but heavily modified.

### License

MIT
