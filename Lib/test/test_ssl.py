# Test the support for SSL and sockets

import sys
import unittest
from test import test_support
import asyncore
import socket
import select
import time
import gc
import os
import errno
import pprint
import urllib, urlparse
import traceback
import weakref

from BaseHTTPServer import HTTPServer
from SimpleHTTPServer import SimpleHTTPRequestHandler

# Optionally test SSL support, if we have it in the tested platform
skip_expected = False
try:
    import ssl
except ImportError:
    skip_expected = True

HOST = test_support.HOST
CERTFILE = None
SVN_PYTHON_ORG_ROOT_CERT = None

def handle_error(prefix):
    exc_format = ' '.join(traceback.format_exception(*sys.exc_info()))
    if test_support.verbose:
        sys.stdout.write(prefix + exc_format)


class BasicTests(unittest.TestCase):

    def testSimpleSSLwrap(self):
        # A crude test for the legacy API
        try:
            ssl.sslwrap_simple(socket.socket(socket.AF_INET))
        except IOError, e:
            if e.errno == 32: # broken pipe when ssl_sock.do_handshake(), this test doesn't care about that
                pass
            else:
                raise
        try:
            ssl.sslwrap_simple(socket.socket(socket.AF_INET)._sock)
        except IOError, e:
            if e.errno == 32: # broken pipe when ssl_sock.do_handshake(), this test doesn't care about that
                pass
            else:
                raise

    def testSSLconnect(self):
        if not test_support.is_resource_enabled('network'):
            return
        s = ssl.wrap_socket(socket.socket(socket.AF_INET),
                            cert_reqs=ssl.CERT_NONE)
        s.connect(("svn.python.org", 443))
        c = s.getpeercert()
        if c:
            raise test_support.TestFailed("Peer cert %s shouldn't be here!")
        s.close()

        # this should fail because we have no verification certs
        s = ssl.wrap_socket(socket.socket(socket.AF_INET),
                            cert_reqs=ssl.CERT_REQUIRED)
        try:
            s.connect(("svn.python.org", 443))
        except ssl.SSLError:
            pass
        finally:
            s.close()

    def testCrucialConstants(self):
        ssl.PROTOCOL_SSLv2
        ssl.PROTOCOL_SSLv23
        ssl.PROTOCOL_SSLv3
        ssl.PROTOCOL_TLSv1
        ssl.CERT_NONE
        ssl.CERT_OPTIONAL
        ssl.CERT_REQUIRED

    def testRAND(self):
        v = ssl.RAND_status()
        if test_support.verbose:
            sys.stdout.write("\n RAND_status is %d (%s)\n"
                             % (v, (v and "sufficient randomness") or
                                "insufficient randomness"))
        try:
            ssl.RAND_egd(1)
        except TypeError:
            pass
        else:
            print "didn't raise TypeError"
        ssl.RAND_add("this is a random string", 75.0)

    def testParseCert(self):
        # note that this uses an 'unofficial' function in _ssl.c,
        # provided solely for this test, to exercise the certificate
        # parsing code
        p = ssl._ssl._test_decode_cert(CERTFILE, False)
        if test_support.verbose:
            sys.stdout.write("\n" + pprint.pformat(p) + "\n")

    def testDERtoPEM(self):

        pem = open(SVN_PYTHON_ORG_ROOT_CERT, 'r').read()
        d1 = ssl.PEM_cert_to_DER_cert(pem)
        p2 = ssl.DER_cert_to_PEM_cert(d1)
        d2 = ssl.PEM_cert_to_DER_cert(p2)
        if (d1 != d2):
            raise test_support.TestFailed("PEM-to-DER or DER-to-PEM translation failed")

    def test_openssl_version(self):
        n = ssl.OPENSSL_VERSION_NUMBER
        t = ssl.OPENSSL_VERSION_INFO
        s = ssl.OPENSSL_VERSION
        self.assertIsInstance(n, (int, long))
        self.assertIsInstance(t, tuple)
        self.assertIsInstance(s, str)
        # Some sanity checks follow
        # >= 0.9
        self.assertGreaterEqual(n, 0x900000)
        # < 2.0
        self.assertLess(n, 0x20000000)
        major, minor, fix, patch, status = t
        self.assertGreaterEqual(major, 0)
        self.assertLess(major, 2)
        self.assertGreaterEqual(minor, 0)
        self.assertLess(minor, 256)
        self.assertGreaterEqual(fix, 0)
        self.assertLess(fix, 256)
        self.assertGreaterEqual(patch, 0)
        self.assertLessEqual(patch, 26)
        self.assertGreaterEqual(status, 0)
        self.assertLessEqual(status, 15)
        # Version string as returned by OpenSSL, the format might change
        self.assertTrue(s.startswith("OpenSSL {:d}.{:d}.{:d}".format(major, minor, fix)),
                        (s, t))

    def test_ciphers(self):
        if not test_support.is_resource_enabled('network'):
            return
        remote = ("svn.python.org", 443)
        s = ssl.wrap_socket(socket.socket(socket.AF_INET),
                            cert_reqs=ssl.CERT_NONE, ciphers="ALL")
        s.connect(remote)
        s = ssl.wrap_socket(socket.socket(socket.AF_INET),
                            cert_reqs=ssl.CERT_NONE, ciphers="DEFAULT")
        s.connect(remote)
        # Error checking occurs when connecting, because the SSL context
        # isn't created before.
        s = ssl.wrap_socket(socket.socket(socket.AF_INET),
                            cert_reqs=ssl.CERT_NONE, ciphers="^$:,;?*'dorothyx")
        with self.assertRaisesRegexp(ssl.SSLError, "No cipher can be selected"):
            s.connect(remote)

    @test_support.cpython_only
    def test_refcycle(self):
        # Issue #7943: an SSL object doesn't create reference cycles with
        # itself.
        s = socket.socket(socket.AF_INET)
        ss = ssl.wrap_socket(s)
        wr = weakref.ref(ss)
        del ss
        self.assertEqual(wr(), None)


class NetworkedTests(unittest.TestCase):

    def testConnect(self):
        s = ssl.wrap_socket(socket.socket(socket.AF_INET),
                            cert_reqs=ssl.CERT_NONE)
        s.connect(("svn.python.org", 443))
        c = s.getpeercert()
        if c:
            raise test_support.TestFailed("Peer cert %s shouldn't be here!")
        s.close()

        # this should fail because we have no verification certs
        s = ssl.wrap_socket(socket.socket(socket.AF_INET),
                            cert_reqs=ssl.CERT_REQUIRED)
        try:
            s.connect(("svn.python.org", 443))
        except ssl.SSLError:
            pass
        finally:
            s.close()

        # this should succeed because we specify the root cert
        s = ssl.wrap_socket(socket.socket(socket.AF_INET),
                            cert_reqs=ssl.CERT_REQUIRED,
                            ca_certs=SVN_PYTHON_ORG_ROOT_CERT)
        try:
            s.connect(("svn.python.org", 443))
        except ssl.SSLError, x:
            raise test_support.TestFailed("Unexpected exception %s" % x)
        finally:
            s.close()

    @unittest.skipIf(os.name == "nt", "Can't use a socket as a file under Windows")
    def test_makefile_close(self):
        # Issue #5238: creating a file-like object with makefile() shouldn't
        # delay closing the underlying "real socket" (here tested with its
        # file descriptor, hence skipping the test under Windows).
        ss = ssl.wrap_socket(socket.socket(socket.AF_INET))
        ss.connect(("svn.python.org", 443))
        fd = ss.fileno()
        f = ss.makefile()
        f.close()
        # The fd is still open
        os.read(fd, 0)
        # Closing the SSL socket should close the fd too
        ss.close()
        gc.collect()
        with self.assertRaises(OSError) as e:
            os.read(fd, 0)
        self.assertEqual(e.exception.errno, errno.EBADF)

    def testNonBlockingHandshake(self):
        s = socket.socket(socket.AF_INET)
        s.connect(("svn.python.org", 443))
        s.setblocking(False)
        s = ssl.wrap_socket(s,
                            cert_reqs=ssl.CERT_NONE,
                            do_handshake_on_connect=False)
        count = 0
        while True:
            try:
                count += 1
                s.do_handshake()
                break
            except ssl.SSLError, err:
                if err.args[0] == ssl.SSL_ERROR_WANT_READ:
                    select.select([s], [], [])
                elif err.args[0] == ssl.SSL_ERROR_WANT_WRITE:
                    select.select([], [s], [])
                else:
                    raise
        s.close()
        if test_support.verbose:
            sys.stdout.write("\nNeeded %d calls to do_handshake() to establish session.\n" % count)

    def testFetchServerCert(self):

        pem = ssl.get_server_certificate(("svn.python.org", 443))
        if not pem:
            raise test_support.TestFailed("No server certificate on svn.python.org:443!")

        try:
            pem = ssl.get_server_certificate(("svn.python.org", 443), ca_certs=CERTFILE)
        except ssl.SSLError:
            #should fail
            pass
        else:
            raise test_support.TestFailed("Got server certificate %s for svn.python.org!" % pem)

        pem = ssl.get_server_certificate(("svn.python.org", 443), ca_certs=SVN_PYTHON_ORG_ROOT_CERT)
        if not pem:
            raise test_support.TestFailed("No server certificate on svn.python.org:443!")
        if test_support.verbose:
            sys.stdout.write("\nVerified certificate for svn.python.org:443 is\n%s\n" % pem)

    def test_algorithms(self):
        # Issue #8484: all algorithms should be available when verifying a
        # certificate.
        # SHA256 was added in OpenSSL 0.9.8
        if ssl.OPENSSL_VERSION_INFO < (0, 9, 8, 0, 15):
            self.skipTest("SHA256 not available on %r" % ssl.OPENSSL_VERSION)
        # NOTE: https://sha256.tbs-internet.com is another possible test host
        remote = ("sha2.hboeck.de", 443)
        sha256_cert = os.path.join(os.path.dirname(__file__), "sha256.pem")
        s = ssl.wrap_socket(socket.socket(socket.AF_INET),
                            cert_reqs=ssl.CERT_REQUIRED,
                            ca_certs=sha256_cert,)
        with test_support.transient_internet():
            try:
                s.connect(remote)
                if test_support.verbose:
                    sys.stdout.write("\nCipher with %r is %r\n" %
                                     (remote, s.cipher()))
                    sys.stdout.write("Certificate is:\n%s\n" %
                                     pprint.pformat(s.getpeercert()))
            finally:
                s.close()


try:
    import threading
except ImportError:
    _have_threads = False
else:

    _have_threads = True

    class ThreadedEchoServer(threading.Thread):

        class ConnectionHandler(threading.Thread):

            """A mildly complicated class, because we want it to work both
            with and without the SSL wrapper around the socket connection, so
            that we can test the STARTTLS functionality."""

            def __init__(self, server, connsock):
                self.server = server
                self.running = False
                self.sock = connsock
                self.sock.setblocking(1)
                self.sslconn = None
                threading.Thread.__init__(self)
                self.daemon = True

            def show_conn_details(self):
                if self.server.certreqs == ssl.CERT_REQUIRED:
                    cert = self.sslconn.getpeercert()
                    if test_support.verbose and self.server.chatty:
                        sys.stdout.write(" client cert is " + pprint.pformat(cert) + "\n")
                    cert_binary = self.sslconn.getpeercert(True)
                    if test_support.verbose and self.server.chatty:
                        sys.stdout.write(" cert binary is " + str(len(cert_binary)) + " bytes\n")
                cipher = self.sslconn.cipher()
                if test_support.verbose and self.server.chatty:
                    sys.stdout.write(" server: connection cipher is now " + str(cipher) + "\n")

            def wrap_conn (self):
                try:
                    self.sslconn = ssl.wrap_socket(self.sock, server_side=True,
                                                   certfile=self.server.certificate,
                                                   ssl_version=self.server.protocol,
                                                   ca_certs=self.server.cacerts,
                                                   cert_reqs=self.server.certreqs,
                                                   ciphers=self.server.ciphers)
                except:
                    if self.server.chatty:
                        handle_error("\n server:  bad connection attempt from " +
                                     str(self.sock.getpeername()) + ":\n")
                    self.close()
                    if not self.server.expect_bad_connects:
                        # here, we want to stop the server, because this shouldn't
                        # happen in the context of our test case
                        self.running = False
                        # normally, we'd just stop here, but for the test
                        # harness, we want to stop the server
                        self.server.stop()
                    return False

                else:
                    return True

            def read(self):
                if self.sslconn:
                    return self.sslconn.read()
                else:
                    return self.sock.recv(1024)

            def write(self, bytes):
                if self.sslconn:
                    return self.sslconn.write(bytes)
                else:
                    return self.sock.send(bytes)

            def close(self):
                if self.sslconn:
                    self.sslconn.close()
                else:
                    self.sock._sock.close()

            def run (self):
                self.running = True
                if not self.server.starttls_server:
                    if isinstance(self.sock, ssl.SSLSocket):
                        self.sslconn = self.sock
                    elif not self.wrap_conn():
                        return
                    self.show_conn_details()
                while self.running:
                    try:
                        msg = self.read()
                        if not msg:
                            # eof, so quit this handler
                            self.running = False
                            self.close()
                        elif msg.strip() == 'over':
                            if test_support.verbose and self.server.connectionchatty:
                                sys.stdout.write(" server: client closed connection\n")
                            self.close()
                            return
                        elif self.server.starttls_server and msg.strip() == 'STARTTLS':
                            if test_support.verbose and self.server.connectionchatty:
                                sys.stdout.write(" server: read STARTTLS from client, sending OK...\n")
                            self.write("OK\n")
                            if not self.wrap_conn():
                                return
                        elif self.server.starttls_server and self.sslconn and msg.strip() == 'ENDTLS':
                            if test_support.verbose and self.server.connectionchatty:
                                sys.stdout.write(" server: read ENDTLS from client, sending OK...\n")
                            self.write("OK\n")
                            self.sslconn.unwrap()
                            self.sslconn = None
                            if test_support.verbose and self.server.connectionchatty:
                                sys.stdout.write(" server: connection is now unencrypted...\n")
                        else:
                            if (test_support.verbose and
                                self.server.connectionchatty):
                                ctype = (self.sslconn and "encrypted") or "unencrypted"
                                sys.stdout.write(" server: read %s (%s), sending back %s (%s)...\n"
                                                 % (repr(msg), ctype, repr(msg.lower()), ctype))
                            self.write(msg.lower())
                    except ssl.SSLError:
                        if self.server.chatty:
                            handle_error("Test server failure:\n")
                        self.close()
                        self.running = False
                        # normally, we'd just stop here, but for the test
                        # harness, we want to stop the server
                        self.server.stop()
                    except:
                        handle_error('')

        def __init__(self, certificate, ssl_version=None,
                     certreqs=None, cacerts=None, expect_bad_connects=False,
                     chatty=True, connectionchatty=False, starttls_server=False,
                     wrap_accepting_socket=False, ciphers=None):

            if ssl_version is None:
                ssl_version = ssl.PROTOCOL_TLSv1
            if certreqs is None:
                certreqs = ssl.CERT_NONE
            self.certificate = certificate
            self.protocol = ssl_version
            self.certreqs = certreqs
            self.cacerts = cacerts
            self.ciphers = ciphers
            self.expect_bad_connects = expect_bad_connects
            self.chatty = chatty
            self.connectionchatty = connectionchatty
            self.starttls_server = starttls_server
            self.sock = socket.socket()
            self.flag = None
            if wrap_accepting_socket:
                self.sock = ssl.wrap_socket(self.sock, server_side=True,
                                            certfile=self.certificate,
                                            cert_reqs = self.certreqs,
                                            ca_certs = self.cacerts,
                                            ssl_version = self.protocol,
                                            ciphers = self.ciphers)
                if test_support.verbose and self.chatty:
                    sys.stdout.write(' server:  wrapped server socket as %s\n' % str(self.sock))
            self.port = test_support.bind_port(self.sock)
            self.active = False
            threading.Thread.__init__(self)
            self.daemon = True

        def start (self, flag=None):
            self.flag = flag
            threading.Thread.start(self)

        def run (self):
            self.sock.settimeout(0.05)
            self.sock.listen(5)
            self.active = True
            if self.flag:
                # signal an event
                self.flag.set()
            while self.active:
                try:
                    newconn, connaddr = self.sock.accept()
                    if test_support.verbose and self.chatty:
                        sys.stdout.write(' server:  new connection from '
                                         + str(connaddr) + '\n')
                    handler = self.ConnectionHandler(self, newconn)
                    handler.start()
                except socket.timeout:
                    pass
                except KeyboardInterrupt:
                    self.stop()
                except:
                    if self.chatty:
                        handle_error("Test server failure:\n")
            self.sock.close()

        def stop (self):
            self.active = False

    class AsyncoreEchoServer(threading.Thread):

        class EchoServer (asyncore.dispatcher):

            class ConnectionHandler (asyncore.dispatcher_with_send):

                def __init__(self, conn, certfile):
                    asyncore.dispatcher_with_send.__init__(self, conn)
                    self.socket = ssl.wrap_socket(conn, server_side=True,
                                                  certfile=certfile,
                                                  do_handshake_on_connect=False)
                    self._ssl_accepting = True

                def readable(self):
                    if isinstance(self.socket, ssl.SSLSocket):
                        while self.socket.pending() > 0:
                            self.handle_read_event()
                    return True

                def _do_ssl_handshake(self):
                    try:
                        self.socket.do_handshake()
                    except ssl.SSLError, err:
                        if err.args[0] in (ssl.SSL_ERROR_WANT_READ,
                                           ssl.SSL_ERROR_WANT_WRITE):
                            return
                        elif err.args[0] == ssl.SSL_ERROR_EOF:
                            return self.handle_close()
                        raise
                    except socket.error, err:
                        if err.args[0] == errno.ECONNABORTED:
                            return self.handle_close()
                    else:
                        self._ssl_accepting = False

                def handle_read(self):
                    if self._ssl_accepting:
                        self._do_ssl_handshake()
                    else:
                        data = self.recv(1024)
                        self.send(data.lower())

                def handle_close(self):
                    self.close()
                    if test_support.verbose:
                        sys.stdout.write(" server:  closed connection %s\n" % self.socket)

                def handle_error(self):
                    raise

            def __init__(self, certfile):
                self.certfile = certfile
                asyncore.dispatcher.__init__(self)
                self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
                self.port = test_support.bind_port(self.socket)
                self.listen(5)

            def handle_accept(self):
                sock_obj, addr = self.accept()
                if test_support.verbose:
                    sys.stdout.write(" server:  new connection from %s:%s\n" %addr)
                self.ConnectionHandler(sock_obj, self.certfile)

            def handle_error(self):
                raise

        def __init__(self, certfile):
            self.flag = None
            self.active = False
            self.server = self.EchoServer(certfile)
            self.port = self.server.port
            threading.Thread.__init__(self)
            self.daemon = True

        def __str__(self):
            return "<%s %s>" % (self.__class__.__name__, self.server)

        def start (self, flag=None):
            self.flag = flag
            threading.Thread.start(self)

        def run (self):
            self.active = True
            if self.flag:
                self.flag.set()
            while self.active:
                try:
                    asyncore.loop(1)
                except:
                    pass

        def stop (self):
            self.active = False
            self.server.close()

    class SocketServerHTTPSServer(threading.Thread):

        class HTTPSServer(HTTPServer):

            def __init__(self, server_address, RequestHandlerClass, certfile):

                HTTPServer.__init__(self, server_address, RequestHandlerClass)
                # we assume the certfile contains both private key and certificate
                self.certfile = certfile
                self.active = False
                self.active_lock = threading.Lock()
                self.allow_reuse_address = True

            def __str__(self):
                return ('<%s %s:%s>' %
                        (self.__class__.__name__,
                         self.server_name,
                         self.server_port))

            def get_request (self):
                # override this to wrap socket with SSL
                sock, addr = self.socket.accept()
                sslconn = ssl.wrap_socket(sock, server_side=True,
                                          certfile=self.certfile)
                return sslconn, addr

        class RootedHTTPRequestHandler(SimpleHTTPRequestHandler):

            # need to override translate_path to get a known root,
            # instead of using os.curdir, since the test could be
            # run from anywhere

            server_version = "TestHTTPS/1.0"

            root = None

            def translate_path(self, path):
                """Translate a /-separated PATH to the local filename syntax.

                Components that mean special things to the local file system
                (e.g. drive or directory names) are ignored.  (XXX They should
                probably be diagnosed.)

                """
                # abandon query parameters
                path = urlparse.urlparse(path)[2]
                path = os.path.normpath(urllib.unquote(path))
                words = path.split('/')
                words = filter(None, words)
                path = self.root
                for word in words:
                    drive, word = os.path.splitdrive(word)
                    head, word = os.path.split(word)
                    if word in self.root: continue
                    path = os.path.join(path, word)
                return path

            def log_message(self, format, *args):

                # we override this to suppress logging unless "verbose"

                if test_support.verbose:
                    sys.stdout.write(" server (%s:%d %s):\n   [%s] %s\n" %
                                     (self.server.server_address,
                                      self.server.server_port,
                                      self.request.cipher(),
                                      self.log_date_time_string(),
                                      format%args))


        def __init__(self, certfile):
            self.flag = None
            self.active = False
            self.RootedHTTPRequestHandler.root = os.path.split(CERTFILE)[0]
            self.server = self.HTTPSServer(
                (HOST, 0), self.RootedHTTPRequestHandler, certfile)
            self.port = self.server.server_port
            threading.Thread.__init__(self)
            self.daemon = True

        def __str__(self):
            return "<%s %s>" % (self.__class__.__name__, self.server)

        def start (self, flag=None):
            self.flag = flag
            threading.Thread.start(self)

        def run (self):
            self.active = True
            if self.flag:
                self.flag.set()
            self.server.serve_forever(0.05)
            self.active = False

        def stop (self):
            self.active = False
            self.server.shutdown()


    def badCertTest (certfile):
        server = ThreadedEchoServer(CERTFILE,
                                    certreqs=ssl.CERT_REQUIRED,
                                    cacerts=CERTFILE, chatty=False)
        flag = threading.Event()
        server.start(flag)
        # wait for it to start
        flag.wait()
        # try to connect
        try:
            try:
                s = ssl.wrap_socket(socket.socket(),
                                    certfile=certfile,
                                    ssl_version=ssl.PROTOCOL_TLSv1)
                s.connect((HOST, server.port))
            except ssl.SSLError, x:
                if test_support.verbose:
                    sys.stdout.write("\nSSLError is %s\n" % x[1])
            except socket.error, x:
                if test_support.verbose:
                    sys.stdout.write("\nsocket.error is %s\n" % x[1])
            else:
                raise test_support.TestFailed(
                    "Use of invalid cert should have failed!")
        finally:
            server.stop()
            server.join()

    def serverParamsTest (certfile, protocol, certreqs, cacertsfile,
                          client_certfile, client_protocol=None, indata="FOO\n",
                          ciphers=None, chatty=True, connectionchatty=False,
                          wrap_accepting_socket=False):

        server = ThreadedEchoServer(certfile,
                                    certreqs=certreqs,
                                    ssl_version=protocol,
                                    cacerts=cacertsfile,
                                    ciphers=ciphers,
                                    chatty=chatty,
                                    connectionchatty=connectionchatty,
                                    wrap_accepting_socket=wrap_accepting_socket)
        flag = threading.Event()
        server.start(flag)
        # wait for it to start
        flag.wait()
        # try to connect
        if client_protocol is None:
            client_protocol = protocol
        try:
            try:
                s = ssl.wrap_socket(socket.socket(),
                                    certfile=client_certfile,
                                    ca_certs=cacertsfile,
                                    ciphers=ciphers,
                                    cert_reqs=certreqs,
                                    ssl_version=client_protocol)
                s.connect((HOST, server.port))
            except ssl.SSLError, x:
                raise test_support.TestFailed("Unexpected SSL error:  " + str(x))
            except Exception, x:
                raise test_support.TestFailed("Unexpected exception:  " + str(x))
            else:
                for arg in [indata, bytearray(indata), memoryview(indata)]:
                    if connectionchatty:
                        if test_support.verbose:
                            sys.stdout.write(
                                " client:  sending %s...\n" % (repr(arg)))
                    s.write(arg)
                    outdata = s.read()
                    if connectionchatty:
                        if test_support.verbose:
                            sys.stdout.write(" client:  read %s\n" % repr(outdata))
                    if outdata != indata.lower():
                        raise test_support.TestFailed(
                            "bad data <<%s>> (%d) received; expected <<%s>> (%d)\n"
                            % (outdata[:min(len(outdata),20)], len(outdata),
                               indata[:min(len(indata),20)].lower(), len(indata)))
                s.write("over\n")
                if connectionchatty:
                    if test_support.verbose:
                        sys.stdout.write(" client:  closing connection.\n")
                s.close()
        finally:
            server.stop()
            server.join()

    def tryProtocolCombo (server_protocol,
                          client_protocol,
                          expectedToWork,
                          certsreqs=None):

        if certsreqs is None:
            certsreqs = ssl.CERT_NONE

        if certsreqs == ssl.CERT_NONE:
            certtype = "CERT_NONE"
        elif certsreqs == ssl.CERT_OPTIONAL:
            certtype = "CERT_OPTIONAL"
        elif certsreqs == ssl.CERT_REQUIRED:
            certtype = "CERT_REQUIRED"
        if test_support.verbose:
            formatstr = (expectedToWork and " %s->%s %s\n") or " {%s->%s} %s\n"
            sys.stdout.write(formatstr %
                             (ssl.get_protocol_name(client_protocol),
                              ssl.get_protocol_name(server_protocol),
                              certtype))
        try:
            # NOTE: we must enable "ALL" ciphers, otherwise an SSLv23 client
            # will send an SSLv3 hello (rather than SSLv2) starting from
            # OpenSSL 1.0.0 (see issue #8322).
            serverParamsTest(CERTFILE, server_protocol, certsreqs,
                             CERTFILE, CERTFILE, client_protocol,
                             ciphers="ALL", chatty=False)
        except test_support.TestFailed:
            if expectedToWork:
                raise
        else:
            if not expectedToWork:
                raise test_support.TestFailed(
                    "Client protocol %s succeeded with server protocol %s!"
                    % (ssl.get_protocol_name(client_protocol),
                       ssl.get_protocol_name(server_protocol)))


    class ThreadedTests(unittest.TestCase):

        def testRudeShutdown(self):

            listener_ready = threading.Event()
            listener_gone = threading.Event()

            s = socket.socket()
            port = test_support.bind_port(s, HOST)

            # `listener` runs in a thread.  It sits in an accept() until
            # the main thread connects.  Then it rudely closes the socket,
            # and sets Event `listener_gone` to let the main thread know
            # the socket is gone.
            def listener():
                s.listen(5)
                listener_ready.set()
                s.accept()
                s.close()
                listener_gone.set()

            def connector():
                listener_ready.wait()
                c = socket.socket()
                c.connect((HOST, port))
                listener_gone.wait()
                try:
                    ssl_sock = ssl.wrap_socket(c)
                except IOError:
                    pass
                else:
                    raise test_support.TestFailed(
                          'connecting to closed SSL socket should have failed')

            t = threading.Thread(target=listener)
            t.start()
            try:
                connector()
            finally:
                t.join()

        def testEcho (self):

            if test_support.verbose:
                sys.stdout.write("\n")
            serverParamsTest(CERTFILE, ssl.PROTOCOL_TLSv1, ssl.CERT_NONE,
                             CERTFILE, CERTFILE, ssl.PROTOCOL_TLSv1,
                             chatty=True, connectionchatty=True)

        def testReadCert(self):

            if test_support.verbose:
                sys.stdout.write("\n")
            s2 = socket.socket()
            server = ThreadedEchoServer(CERTFILE,
                                        certreqs=ssl.CERT_NONE,
                                        ssl_version=ssl.PROTOCOL_SSLv23,
                                        cacerts=CERTFILE,
                                        chatty=False)
            flag = threading.Event()
            server.start(flag)
            # wait for it to start
            flag.wait()
            # try to connect
            try:
                try:
                    s = ssl.wrap_socket(socket.socket(),
                                        certfile=CERTFILE,
                                        ca_certs=CERTFILE,
                                        cert_reqs=ssl.CERT_REQUIRED,
                                        ssl_version=ssl.PROTOCOL_SSLv23)
                    s.connect((HOST, server.port))
                except ssl.SSLError, x:
                    raise test_support.TestFailed(
                        "Unexpected SSL error:  " + str(x))
                except Exception, x:
                    raise test_support.TestFailed(
                        "Unexpected exception:  " + str(x))
                else:
                    if not s:
                        raise test_support.TestFailed(
                            "Can't SSL-handshake with test server")
                    cert = s.getpeercert()
                    if not cert:
                        raise test_support.TestFailed(
                            "Can't get peer certificate.")
                    cipher = s.cipher()
                    if test_support.verbose:
                        sys.stdout.write(pprint.pformat(cert) + '\n')
                        sys.stdout.write("Connection cipher is " + str(cipher) + '.\n')
                    if 'subject' not in cert:
                        raise test_support.TestFailed(
                            "No subject field in certificate: %s." %
                            pprint.pformat(cert))
                    if ((('organizationName', 'Python Software Foundation'),)
                        not in cert['subject']):
                        raise test_support.TestFailed(
                            "Missing or invalid 'organizationName' field in certificate subject; "
                            "should be 'Python Software Foundation'.")
                    s.close()
            finally:
                server.stop()
                server.join()

        def testNULLcert(self):
            badCertTest(os.path.join(os.path.dirname(__file__) or os.curdir,
                                     "nullcert.pem"))
        def testMalformedCert(self):
            badCertTest(os.path.join(os.path.dirname(__file__) or os.curdir,
                                     "badcert.pem"))
        def testWrongCert(self):
            badCertTest(os.path.join(os.path.dirname(__file__) or os.curdir,
                                     "wrongcert.pem"))
        def testMalformedKey(self):
            badCertTest(os.path.join(os.path.dirname(__file__) or os.curdir,
                                     "badkey.pem"))

        def testProtocolSSL2(self):
            if test_support.verbose:
                sys.stdout.write("\n")
            tryProtocolCombo(ssl.PROTOCOL_SSLv2, ssl.PROTOCOL_SSLv2, True)
            tryProtocolCombo(ssl.PROTOCOL_SSLv2, ssl.PROTOCOL_SSLv2, True, ssl.CERT_OPTIONAL)
            tryProtocolCombo(ssl.PROTOCOL_SSLv2, ssl.PROTOCOL_SSLv2, True, ssl.CERT_REQUIRED)
            tryProtocolCombo(ssl.PROTOCOL_SSLv2, ssl.PROTOCOL_SSLv23, True)
            tryProtocolCombo(ssl.PROTOCOL_SSLv2, ssl.PROTOCOL_SSLv3, False)
            tryProtocolCombo(ssl.PROTOCOL_SSLv2, ssl.PROTOCOL_TLSv1, False)

        def testProtocolSSL23(self):
            if test_support.verbose:
                sys.stdout.write("\n")
            try:
                tryProtocolCombo(ssl.PROTOCOL_SSLv23, ssl.PROTOCOL_SSLv2, True)
            except test_support.TestFailed, x:
                # this fails on some older versions of OpenSSL (0.9.7l, for instance)
                if test_support.verbose:
                    sys.stdout.write(
                        " SSL2 client to SSL23 server test unexpectedly failed:\n %s\n"
                        % str(x))
            tryProtocolCombo(ssl.PROTOCOL_SSLv23, ssl.PROTOCOL_SSLv3, True)
            tryProtocolCombo(ssl.PROTOCOL_SSLv23, ssl.PROTOCOL_SSLv23, True)
            tryProtocolCombo(ssl.PROTOCOL_SSLv23, ssl.PROTOCOL_TLSv1, True)

            tryProtocolCombo(ssl.PROTOCOL_SSLv23, ssl.PROTOCOL_SSLv3, True, ssl.CERT_OPTIONAL)
            tryProtocolCombo(ssl.PROTOCOL_SSLv23, ssl.PROTOCOL_SSLv23, True, ssl.CERT_OPTIONAL)
            tryProtocolCombo(ssl.PROTOCOL_SSLv23, ssl.PROTOCOL_TLSv1, True, ssl.CERT_OPTIONAL)

            tryProtocolCombo(ssl.PROTOCOL_SSLv23, ssl.PROTOCOL_SSLv3, True, ssl.CERT_REQUIRED)
            tryProtocolCombo(ssl.PROTOCOL_SSLv23, ssl.PROTOCOL_SSLv23, True, ssl.CERT_REQUIRED)
            tryProtocolCombo(ssl.PROTOCOL_SSLv23, ssl.PROTOCOL_TLSv1, True, ssl.CERT_REQUIRED)

        def testProtocolSSL3(self):
            if test_support.verbose:
                sys.stdout.write("\n")
            tryProtocolCombo(ssl.PROTOCOL_SSLv3, ssl.PROTOCOL_SSLv3, True)
            tryProtocolCombo(ssl.PROTOCOL_SSLv3, ssl.PROTOCOL_SSLv3, True, ssl.CERT_OPTIONAL)
            tryProtocolCombo(ssl.PROTOCOL_SSLv3, ssl.PROTOCOL_SSLv3, True, ssl.CERT_REQUIRED)
            tryProtocolCombo(ssl.PROTOCOL_SSLv3, ssl.PROTOCOL_SSLv2, False)
            tryProtocolCombo(ssl.PROTOCOL_SSLv3, ssl.PROTOCOL_SSLv23, False)
            tryProtocolCombo(ssl.PROTOCOL_SSLv3, ssl.PROTOCOL_TLSv1, False)

        def testProtocolTLS1(self):
            if test_support.verbose:
                sys.stdout.write("\n")
            tryProtocolCombo(ssl.PROTOCOL_TLSv1, ssl.PROTOCOL_TLSv1, True)
            tryProtocolCombo(ssl.PROTOCOL_TLSv1, ssl.PROTOCOL_TLSv1, True, ssl.CERT_OPTIONAL)
            tryProtocolCombo(ssl.PROTOCOL_TLSv1, ssl.PROTOCOL_TLSv1, True, ssl.CERT_REQUIRED)
            tryProtocolCombo(ssl.PROTOCOL_TLSv1, ssl.PROTOCOL_SSLv2, False)
            tryProtocolCombo(ssl.PROTOCOL_TLSv1, ssl.PROTOCOL_SSLv3, False)
            tryProtocolCombo(ssl.PROTOCOL_TLSv1, ssl.PROTOCOL_SSLv23, False)

        def testSTARTTLS (self):

            msgs = ("msg 1", "MSG 2", "STARTTLS", "MSG 3", "msg 4", "ENDTLS", "msg 5", "msg 6")

            server = ThreadedEchoServer(CERTFILE,
                                        ssl_version=ssl.PROTOCOL_TLSv1,
                                        starttls_server=True,
                                        chatty=True,
                                        connectionchatty=True)
            flag = threading.Event()
            server.start(flag)
            # wait for it to start
            flag.wait()
            # try to connect
            wrapped = False
            try:
                try:
                    s = socket.socket()
                    s.setblocking(1)
                    s.connect((HOST, server.port))
                except Exception, x:
                    raise test_support.TestFailed("Unexpected exception:  " + str(x))
                else:
                    if test_support.verbose:
                        sys.stdout.write("\n")
                    for indata in msgs:
                        if test_support.verbose:
                            sys.stdout.write(
                                " client:  sending %s...\n" % repr(indata))
                        if wrapped:
                            conn.write(indata)
                            outdata = conn.read()
                        else:
                            s.send(indata)
                            outdata = s.recv(1024)
                        if (indata == "STARTTLS" and
                            outdata.strip().lower().startswith("ok")):
                            if test_support.verbose:
                                sys.stdout.write(
                                    " client:  read %s from server, starting TLS...\n"
                                    % repr(outdata))
                            conn = ssl.wrap_socket(s, ssl_version=ssl.PROTOCOL_TLSv1)
                            wrapped = True
                        elif (indata == "ENDTLS" and
                            outdata.strip().lower().startswith("ok")):
                            if test_support.verbose:
                                sys.stdout.write(
                                    " client:  read %s from server, ending TLS...\n"
                                    % repr(outdata))
                            s = conn.unwrap()
                            wrapped = False
                        else:
                            if test_support.verbose:
                                sys.stdout.write(
                                    " client:  read %s from server\n" % repr(outdata))
                    if test_support.verbose:
                        sys.stdout.write(" client:  closing connection.\n")
                    if wrapped:
                        conn.write("over\n")
                    else:
                        s.send("over\n")
                    s.close()
            finally:
                server.stop()
                server.join()

        def testSocketServer(self):

            server = SocketServerHTTPSServer(CERTFILE)
            flag = threading.Event()
            server.start(flag)
            # wait for it to start
            flag.wait()
            # try to connect
            try:
                if test_support.verbose:
                    sys.stdout.write('\n')
                d1 = open(CERTFILE, 'rb').read()
                d2 = ''
                # now fetch the same data from the HTTPS server
                url = 'https://127.0.0.1:%d/%s' % (
                    server.port, os.path.split(CERTFILE)[1])
                with test_support.check_py3k_warnings():
                    f = urllib.urlopen(url)
                dlen = f.info().getheader("content-length")
                if dlen and (int(dlen) > 0):
                    d2 = f.read(int(dlen))
                    if test_support.verbose:
                        sys.stdout.write(
                            " client: read %d bytes from remote server '%s'\n"
                            % (len(d2), server))
                f.close()
            except:
                msg = ''.join(traceback.format_exception(*sys.exc_info()))
                if test_support.verbose:
                    sys.stdout.write('\n' + msg)
                raise test_support.TestFailed(msg)
            else:
                if not (d1 == d2):
                    raise test_support.TestFailed(
                        "Couldn't fetch data from HTTPS server")
            finally:
                server.stop()
                server.join()

        def testWrappedAccept (self):

            if test_support.verbose:
                sys.stdout.write("\n")
            serverParamsTest(CERTFILE, ssl.PROTOCOL_SSLv23, ssl.CERT_REQUIRED,
                             CERTFILE, CERTFILE, ssl.PROTOCOL_SSLv23,
                             chatty=True, connectionchatty=True,
                             wrap_accepting_socket=True)


        def testAsyncoreServer (self):

            indata = "TEST MESSAGE of mixed case\n"

            if test_support.verbose:
                sys.stdout.write("\n")
            server = AsyncoreEchoServer(CERTFILE)
            flag = threading.Event()
            server.start(flag)
            # wait for it to start
            flag.wait()
            # try to connect
            try:
                try:
                    s = ssl.wrap_socket(socket.socket())
                    s.connect(('127.0.0.1', server.port))
                except ssl.SSLError, x:
                    raise test_support.TestFailed("Unexpected SSL error:  " + str(x))
                except Exception, x:
                    raise test_support.TestFailed("Unexpected exception:  " + str(x))
                else:
                    if test_support.verbose:
                        sys.stdout.write(
                            " client:  sending %s...\n" % (repr(indata)))
                    s.write(indata)
                    outdata = s.read()
                    if test_support.verbose:
                        sys.stdout.write(" client:  read %s\n" % repr(outdata))
                    if outdata != indata.lower():
                        raise test_support.TestFailed(
                            "bad data <<%s>> (%d) received; expected <<%s>> (%d)\n"
                            % (outdata[:min(len(outdata),20)], len(outdata),
                               indata[:min(len(indata),20)].lower(), len(indata)))
                    s.write("over\n")
                    if test_support.verbose:
                        sys.stdout.write(" client:  closing connection.\n")
                    s.close()
            finally:
                server.stop()
                # wait for server thread to end
                server.join()


        def testAllRecvAndSendMethods(self):

            if test_support.verbose:
                sys.stdout.write("\n")

            server = ThreadedEchoServer(CERTFILE,
                                        certreqs=ssl.CERT_NONE,
                                        ssl_version=ssl.PROTOCOL_TLSv1,
                                        cacerts=CERTFILE,
                                        chatty=True,
                                        connectionchatty=False)
            flag = threading.Event()
            server.start(flag)
            # wait for it to start
            flag.wait()
            # try to connect
            try:
                s = ssl.wrap_socket(socket.socket(),
                                    server_side=False,
                                    certfile=CERTFILE,
                                    ca_certs=CERTFILE,
                                    cert_reqs=ssl.CERT_NONE,
                                    ssl_version=ssl.PROTOCOL_TLSv1)
                s.connect((HOST, server.port))
            except ssl.SSLError as x:
                self.fail("Unexpected SSL error:  " + str(x))
            except Exception as x:
                self.fail("Unexpected exception:  " + str(x))
            else:
                # helper methods for standardising recv* method signatures
                def _recv_into():
                    b = bytearray("\0"*100)
                    count = s.recv_into(b)
                    return b[:count]

                def _recvfrom_into():
                    b = bytearray("\0"*100)
                    count, addr = s.recvfrom_into(b)
                    return b[:count]

                # (name, method, whether to expect success, *args)
                send_methods = [
                    ('send', s.send, True, []),
                    ('sendto', s.sendto, False, ["some.address"]),
                    ('sendall', s.sendall, True, []),
                ]
                recv_methods = [
                    ('recv', s.recv, True, []),
                    ('recvfrom', s.recvfrom, False, ["some.address"]),
                    ('recv_into', _recv_into, True, []),
                    ('recvfrom_into', _recvfrom_into, False, []),
                ]
                data_prefix = u"PREFIX_"

                for meth_name, send_meth, expect_success, args in send_methods:
                    indata = data_prefix + meth_name
                    try:
                        send_meth(indata.encode('ASCII', 'strict'), *args)
                        outdata = s.read()
                        outdata = outdata.decode('ASCII', 'strict')
                        if outdata != indata.lower():
                            self.fail(
                                "While sending with <<%s>> bad data "
                                "<<%r>> (%d) received; "
                                "expected <<%r>> (%d)\n" % (
                                    meth_name, outdata[:20], len(outdata),
                                    indata[:20], len(indata)
                                )
                            )
                    except ValueError as e:
                        if expect_success:
                            self.fail(
                                "Failed to send with method <<%s>>; "
                                "expected to succeed.\n" % (meth_name,)
                            )
                        if not str(e).startswith(meth_name):
                            self.fail(
                                "Method <<%s>> failed with unexpected "
                                "exception message: %s\n" % (
                                    meth_name, e
                                )
                            )

                for meth_name, recv_meth, expect_success, args in recv_methods:
                    indata = data_prefix + meth_name
                    try:
                        s.send(indata.encode('ASCII', 'strict'))
                        outdata = recv_meth(*args)
                        outdata = outdata.decode('ASCII', 'strict')
                        if outdata != indata.lower():
                            self.fail(
                                "While receiving with <<%s>> bad data "
                                "<<%r>> (%d) received; "
                                "expected <<%r>> (%d)\n" % (
                                    meth_name, outdata[:20], len(outdata),
                                    indata[:20], len(indata)
                                )
                            )
                    except ValueError as e:
                        if expect_success:
                            self.fail(
                                "Failed to receive with method <<%s>>; "
                                "expected to succeed.\n" % (meth_name,)
                            )
                        if not str(e).startswith(meth_name):
                            self.fail(
                                "Method <<%s>> failed with unexpected "
                                "exception message: %s\n" % (
                                    meth_name, e
                                )
                            )
                        # consume data
                        s.read()

                s.write("over\n".encode("ASCII", "strict"))
                s.close()
            finally:
                server.stop()
                server.join()

        def test_handshake_timeout(self):
            # Issue #5103: SSL handshake must respect the socket timeout
            server = socket.socket(socket.AF_INET)
            host = "127.0.0.1"
            port = test_support.bind_port(server)
            started = threading.Event()
            finish = False

            def serve():
                server.listen(5)
                started.set()
                conns = []
                while not finish:
                    r, w, e = select.select([server], [], [], 0.1)
                    if server in r:
                        # Let the socket hang around rather than having
                        # it closed by garbage collection.
                        conns.append(server.accept()[0])

            t = threading.Thread(target=serve)
            t.start()
            started.wait()

            try:
                try:
                    c = socket.socket(socket.AF_INET)
                    c.settimeout(0.2)
                    c.connect((host, port))
                    # Will attempt handshake and time out
                    self.assertRaisesRegexp(ssl.SSLError, "timed out",
                                            ssl.wrap_socket, c)
                finally:
                    c.close()
                try:
                    c = socket.socket(socket.AF_INET)
                    c.settimeout(0.2)
                    c = ssl.wrap_socket(c)
                    # Will attempt handshake and time out
                    self.assertRaisesRegexp(ssl.SSLError, "timed out",
                                            c.connect, (host, port))
                finally:
                    c.close()
            finally:
                finish = True
                t.join()
                server.close()


def test_main(verbose=False):
    if skip_expected:
        raise unittest.SkipTest("No SSL support")

    global CERTFILE, SVN_PYTHON_ORG_ROOT_CERT
    CERTFILE = os.path.join(os.path.dirname(__file__) or os.curdir,
                            "keycert.pem")
    SVN_PYTHON_ORG_ROOT_CERT = os.path.join(
        os.path.dirname(__file__) or os.curdir,
        "https_svn_python_org_root.pem")

    if (not os.path.exists(CERTFILE) or
        not os.path.exists(SVN_PYTHON_ORG_ROOT_CERT)):
        raise test_support.TestFailed("Can't read certificate files!")

    tests = [BasicTests]

    if test_support.is_resource_enabled('network'):
        tests.append(NetworkedTests)

    if _have_threads:
        thread_info = test_support.threading_setup()
        if thread_info and test_support.is_resource_enabled('network'):
            tests.append(ThreadedTests)

    test_support.run_unittest(*tests)

    if _have_threads:
        test_support.threading_cleanup(*thread_info)

if __name__ == "__main__":
    test_main()
