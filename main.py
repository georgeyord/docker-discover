#!/usr/bin/python

import etcd
from jinja2 import Environment, PackageLoader
import os
from subprocess import call
import signal
import sys
import time
from datetime import datetime

env = Environment(loader=PackageLoader('haproxy', 'templates'))
admin_user="stats"
admin_password="stats"
POLL_TIMEOUT=5

signal.signal(signal.SIGCHLD, signal.SIG_IGN)

def get_etcd_addr():
    if "ETCD_HOST" not in os.environ:
        print "ETCD_HOST not set"
        sys.exit(1)

    etcd_host = os.environ["ETCD_HOST"]
    if not etcd_host:
        print "ETCD_HOST not set"
        sys.exit(1)

    port = 4001
    host = etcd_host

    if ":" in etcd_host:
        host, port = etcd_host.split(":")

    return host, port

def get_services():

    host, port = get_etcd_addr()
    client = etcd.Client(host=host, port=int(port))
    etcd_services = client.read('/services', recursive = True)
    services = {}

    for s in etcd_services.children:

        if s.key[1:].count("/") != 3:
            continue

        ignore, name, port, container = s.key[1:].split("/")

        endpoints = services.setdefault(port, dict())
        domains = endpoints.setdefault(name, [])
        domains.append(dict(ID=container, addr=s.value))

    return services

def generate_config(services):
    template = env.get_template('haproxy.cfg.tmpl')
    with open("/etc/haproxy/haproxy.cfg", "w") as f:
        f.write(template.render(
            services=services,
            admin_user=admin_user,
            admin_password=admin_password,
            now=datetime.now().strftime("%d-%m-%y-%H-%M-%S")
            ))

if __name__ == "__main__":
    current_services = {}

    if "ADMIN_USER" in os.environ:
        admin_user = os.environ["ADMIN_USER"]

    if "ADMIN_PASSWORD" in os.environ:
        admin_password = os.environ["ADMIN_PASSWORD"]

    while True:
        try:
            services = get_services()

            if not services or services == current_services:
                print "Config did not change. Sleep for " + str(POLL_TIMEOUT) + " sec"
                time.sleep(POLL_TIMEOUT)
                continue

            print "Config changed, generating configs..."
            generate_config(services)
            print "Reloading proxy..."
            ret = call(["./reload-haproxy.sh"])
            if ret != 0:
                print "Reloading haproxy returned: ", ret
                time.sleep(POLL_TIMEOUT)
                continue
            else:
                print "Proxy reloaded"
            current_services = services

        except Exception, e:
            print "Error:", e

        time.sleep(POLL_TIMEOUT)