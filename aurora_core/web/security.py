# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from urllib.parse import urlparse, urljoin
import errno, http.client, ipaddress, queue, socket, ssl, threading, time, urllib.error, urllib.request

DNS_VALIDATION_TIMEOUT=1.0
DNS_CACHE_TTL=10.0
_DNS_CACHE_MAX=256
_DNS_CACHE={}
_DNS_CACHE_LOCK=threading.Lock()

def _resolve_public_host(host):
    result=queue.Queue(maxsize=1)
    def resolve():
        try: result.put((socket.getaddrinfo(host,None,type=socket.SOCK_STREAM),None))
        except Exception as exc: result.put((None,exc))
    worker=threading.Thread(target=resolve,name='aurora-public-dns',daemon=True)
    worker.start(); worker.join(DNS_VALIDATION_TIMEOUT)
    if worker.is_alive(): raise TimeoutError('A validação DNS excedeu o tempo limite.')
    infos,error=result.get_nowait()
    if error: raise error
    return infos

def _public_addresses(host):
    host=host.lower()
    if host in ('localhost','localhost.localdomain'):
        raise ValueError('Endereços locais não podem ser acessados pelo agente web.')
    try:
        addr=ipaddress.ip_address(host)
    except ValueError:
        now=time.monotonic()
        with _DNS_CACHE_LOCK:
            cached=_DNS_CACHE.get(host)
            if cached and now<cached[0]: return cached[1]
            if cached: _DNS_CACHE.pop(host,None)
        try: infos=_resolve_public_host(host)
        except socket.gaierror: infos=[]
        addresses=[]
        for info in infos:
            addr=ipaddress.ip_address(info[4][0])
            if not addr.is_global: raise ValueError('Domínio resolve para uma rede local ou reservada.')
            addresses.append(str(addr))
        if not addresses: raise ValueError('Não foi possível resolver o domínio.')
        addresses=tuple(dict.fromkeys(addresses))
        with _DNS_CACHE_LOCK:
            for key,(expires,_) in list(_DNS_CACHE.items()):
                if now>=expires: _DNS_CACHE.pop(key,None)
            if len(_DNS_CACHE)>=_DNS_CACHE_MAX: _DNS_CACHE.pop(next(iter(_DNS_CACHE)))
            _DNS_CACHE[host]=(time.monotonic()+DNS_CACHE_TTL,addresses)
        return addresses
    if not addr.is_global: raise ValueError('Endereço local ou reservado bloqueado.')
    return (str(addr),)

def _validated_url_addresses(url):
    parsed=urlparse(url)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Use apenas endereços públicos HTTP/HTTPS.')
    if parsed.port not in (None,80,443): raise ValueError('Porta bloqueada.')
    return parsed,_public_addresses(parsed.hostname)

def public_http_url(url):
    _validated_url_addresses(url)
    return url

class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self,host,addresses,**kwargs):
        self._public_addresses=addresses
        super().__init__(host,**kwargs)
    def connect(self):
        last_error=None
        for address in self._public_addresses:
            try:
                self.sock=socket.create_connection((address,self.port),self.timeout,self.source_address)
                break
            except OSError as exc:
                last_error=exc
        else:
            raise last_error or OSError('Não foi possível conectar ao endereço público validado.')
        try: self.sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
        except OSError as exc:
            if exc.errno!=errno.ENOPROTOOPT: raise
        if self._tunnel_host: self._tunnel()

class _PinnedHTTPSConnection(_PinnedHTTPConnection):
    def __init__(self,host,addresses,context=None,**kwargs):
        kwargs.setdefault('port',443)
        self._tls_context=context or ssl.create_default_context()
        super().__init__(host,addresses,**kwargs)
    def connect(self):
        super().connect()
        server_hostname=self._tunnel_host or self.host
        self.sock=self._tls_context.wrap_socket(self.sock,server_hostname=server_hostname)

class PublicHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self,req):
        _,addresses=_validated_url_addresses(req.full_url)
        return self.do_open(lambda host,**kwargs:_PinnedHTTPConnection(host,addresses,**kwargs),req)

class PublicHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self,req):
        _,addresses=_validated_url_addresses(req.full_url)
        return self.do_open(lambda host,**kwargs:_PinnedHTTPSConnection(host,addresses,**kwargs),
                            req,context=self._context)

class PublicRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        newurl=urljoin(req.full_url,newurl)
        public_http_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)

PUBLIC_OPENER=urllib.request.build_opener(urllib.request.ProxyHandler({}),PublicRedirectHandler,
                                           PublicHTTPHandler,PublicHTTPSHandler)
