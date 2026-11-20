"""WORK-05 R1-B: pinned-connection SSRF hardening (finding F1, DNS rebinding).

Deterministic: socket.create_connection is replaced by a recorder that never
opens a real connection; resolvers are scripted. No external or internal host
is contacted.
"""
import os
import socket
import ssl
import unittest
from unittest import mock

from rightware.agent import web as W

try:
    import httpcore
    import httpx
except ImportError:
    httpx = None

NO_SSRF = lambda url: None   # noqa: E731


class Recorder:
    def __init__(self):
        self.addresses = []

    def __call__(self, address, *args, **kwargs):
        self.addresses.append(address)
        raise ConnectionRefusedError("simulated: no real connection")


def scripted(*answers):
    """Resolver returning successive answers (check_url first, then connect time)."""
    calls = []
    seq = list(answers)

    def resolve(host):
        calls.append(host)
        return seq.pop(0) if len(seq) > 1 else seq[0]
    resolve.calls = calls
    return resolve


@unittest.skipIf(httpx is None, "needs httpx/httpcore (pinned venv, product CI)")
class PinnedConnection(unittest.TestCase):
    def fetch(self, url, resolver):
        rec = Recorder()
        f = W.HttpxFetcher(resolver=resolver, ssrf=NO_SSRF)
        with mock.patch("socket.create_connection", rec):
            with self.assertRaises(Exception) as ctx:
                f.fetch(url)
        return rec, f, ctx.exception

    def test_socket_connects_to_the_validated_ip_not_to_a_fresh_resolution(self):
        resolver = scripted(["93.184.216.34"])
        rec, f, _ = self.fetch("https://rebind.example/page", resolver)
        self.assertEqual(rec.addresses, [("93.184.216.34", 443)])
        self.assertEqual(resolver.calls, ["rebind.example", "rebind.example"])   # check_url, then pinned connect

    def test_dns_rebinding_to_private_at_connect_time_never_opens_a_socket(self):
        for private in (["127.0.0.1"], ["10.0.0.7"], ["169.254.169.254"], ["100.64.1.1"],
                        ["::ffff:127.0.0.1"], ["::1"], ["93.184.216.34", "192.168.1.1"]):
            with self.subTest(private=private):
                rec, _, exc = self.fetch("https://rebind.example/", scripted(["93.184.216.34"], private))
                self.assertIsInstance(exc, W.WebRefused)
                self.assertEqual(rec.addresses, [])

    def test_redirect_host_is_validated_again_and_pinned(self):
        resolver = scripted(["93.184.216.34"])
        transport, backend = W.pinned_transport(resolver)
        rec = Recorder()
        with mock.patch("socket.create_connection", rec):
            with self.assertRaises(Exception):
                backend.connect_tcp("other.example", 443)
        self.assertEqual(rec.addresses, [("93.184.216.34", 443)])
        with self.assertRaises(W.WebRefused):
            W.pinned_transport(scripted(["10.0.0.1"]))[1].connect_tcp("internal.example", 443)

    def test_ports_and_unix_sockets_refused_at_the_socket_layer(self):
        _, backend = W.pinned_transport(scripted(["93.184.216.34"]))
        rec = Recorder()
        with mock.patch("socket.create_connection", rec):
            with self.assertRaises(W.WebRefused):
                backend.connect_tcp("example.org", 8080)
            with self.assertRaises(W.WebRefused):
                backend.connect_unix_socket("/var/run/docker.sock")
        self.assertEqual(rec.addresses, [])

    def test_environment_proxies_are_ignored(self):
        env = {"HTTPS_PROXY": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9",
               "ALL_PROXY": "socks5://127.0.0.1:9", "SSL_CERT_FILE": "/nonexistent/evil.pem"}
        with mock.patch.dict(os.environ, env):
            transport, backend = W.pinned_transport(scripted(["93.184.216.34"]))
            rec, _, _ = self.fetch("https://example.org/", scripted(["93.184.216.34"]))
        self.assertIsInstance(transport._pool, httpcore.ConnectionPool)
        self.assertNotIsInstance(transport._pool, httpcore.HTTPProxy)
        self.assertIs(transport._pool._network_backend, backend)
        self.assertEqual(rec.addresses, [("93.184.216.34", 443)])     # never the proxy

    def test_tls_verification_and_conservative_connection_limits(self):
        transport, _ = W.pinned_transport(scripted(["93.184.216.34"]))
        pool = transport._pool
        self.assertEqual(pool._ssl_context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(pool._ssl_context.check_hostname)
        self.assertEqual((pool._max_connections, pool._max_keepalive_connections, pool._retries),
                         (W.MAX_CONNECTIONS, 0, 0))
        self.assertFalse(pool._http2)

    def test_default_fetcher_uses_the_pinned_transport(self):
        rec, f, _ = self.fetch("https://example.org/", scripted(["93.184.216.34"]))
        self.assertIsNotNone(f.backend)
        self.assertEqual(rec.addresses, [("93.184.216.34", 443)])


class MalformedUrls(unittest.TestCase):
    def test_malformed_urls_are_refused_without_resolution(self):
        def boom(host):
            raise AssertionError("must not resolve")
        for url in ("http://[::1", "https://exa\x00mple.org/", "http:///path", "https://example.org:99999/",
                    "https://example.org:-1/", "//example.org/", "https:example.org", "HTTPS://", "https://.",
                    "https://example.org\\@evil.org/"):
            with self.subTest(url=url):
                with self.assertRaises(W.WebRefused):
                    W.check_url(url, boom, NO_SSRF)


if __name__ == "__main__":
    unittest.main()
