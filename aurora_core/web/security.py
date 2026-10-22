from __future__ import annotations

from urllib.parse import urlparse, urljoin
import urllib.error, urllib.request
import socket, ipaddress

def public_http_url(url):
    parsed=urlparse(url)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Use apenas endereços públicos HTTP/HTTPS.')
    if parsed.port not in (None,80,443): raise ValueError('Porta bloqueada.')
    host=parsed.hostname.lower()
    if host in ('localhost','localhost.localdomain'): raise ValueError('Endereços locais não podem ser acessados pelo agente web.')
    try:
        addr=ipaddress.ip_address(host)
    except ValueError:
        try: infos=socket.getaddrinfo(host,None,type=socket.SOCK_STREAM)
        except socket.gaierror: infos=[]
        for info in infos:
            addr=ipaddress.ip_address(info[4][0])
            if not addr.is_global: raise ValueError('Domínio resolve para uma rede local ou reservada.')
        if not infos: raise ValueError('Não foi possível resolver o domínio.')
    else:
        if not addr.is_global: raise ValueError('Endereço local ou reservado bloqueado.')
    return url

class PublicRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        newurl=urljoin(req.full_url,newurl)
        public_http_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)

PUBLIC_OPENER=urllib.request.build_opener(PublicRedirectHandler)
