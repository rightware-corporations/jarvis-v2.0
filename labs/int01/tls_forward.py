"""INT01 E2E (LAB): local TLS front for the loopback JARVIS, standing in for the Dev Tunnel relay with
``--host-header unchanged --origin-header unchanged``: raw bytes are forwarded, Host/Origin are NOT rewritten.
Usage: python -m labs.int01.tls_forward CERT KEY [listen_port=443] [target_port=8000]"""
import asyncio
import ssl
import sys


async def pipe(r, w):
    try:
        while data := await r.read(65536):
            w.write(data)
            await w.drain()
    except (ConnectionError, asyncio.IncompleteReadError):
        pass
    finally:
        w.close()


async def main(cert, key, port=443, target=8000):
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.load_cert_chain(cert, key)

    async def handle(cr, cw):
        try:
            tr, tw = await asyncio.open_connection("127.0.0.1", target)
        except OSError:
            cw.close()
            return
        await asyncio.gather(pipe(cr, tw), pipe(tr, cw))
    srv = await asyncio.start_server(handle, "127.0.0.1", port, ssl=ctx)
    async with srv:
        await srv.serve_forever()


if __name__ == "__main__":
    a = sys.argv[1:]
    asyncio.run(main(a[0], a[1], int(a[2]) if len(a) > 2 else 443, int(a[3]) if len(a) > 3 else 8000))
