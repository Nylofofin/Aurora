"""Bounded decoding for HTTP response bodies used by web search."""
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import zlib


def decode_http_body(raw: bytes, content_encoding: str | None, limit: int) -> bytes:
    """Decode identity/gzip/deflate content without allowing unbounded expansion."""
    encoding=(content_encoding or '').strip().casefold()
    if encoding in ('','identity'):
        return raw[:limit]
    if encoding == 'gzip':
        decoders=(zlib.decompressobj(16+zlib.MAX_WBITS),)
    elif encoding == 'deflate':
        decoders=(zlib.decompressobj(),zlib.decompressobj(-zlib.MAX_WBITS))
    else:
        raise ValueError('A página usa um tipo de compressão HTTP não suportado.')
    for decoder in decoders:
        try:
            decoded=decoder.decompress(raw,limit+1)
            if len(decoded)>limit or decoder.unconsumed_tail:
                raise ValueError('A página expandida excede o limite de leitura.')
            decoded+=decoder.flush(max(1,limit+1-len(decoded)))
            if len(decoded)>limit:
                raise ValueError('A página expandida excede o limite de leitura.')
            if not decoder.eof:
                raise ValueError('A resposta HTTP comprimida está incompleta.')
            return decoded
        except zlib.error:
            continue
    raise ValueError('Não foi possível descomprimir a resposta HTTP.')
