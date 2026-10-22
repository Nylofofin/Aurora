from __future__ import annotations

from urllib.parse import urlparse, urlencode, parse_qs, urljoin
import asyncio, base64, concurrent.futures, configparser, html, json, os, platform, queue, re, shlex, shutil, signal, subprocess, sys, threading, time, urllib.error, urllib.request, unicodedata

from ..config import settings_save

WMO_WEATHER={0:'céu limpo',1:'predominantemente limpo',2:'parcialmente nublado',3:'nublado',45:'neblina',48:'neblina com gelo',51:'garoa fraca',53:'garoa',55:'garoa forte',61:'chuva fraca',63:'chuva',65:'chuva forte',71:'neve fraca',73:'neve',75:'neve forte',80:'pancadas fracas',81:'pancadas de chuva',82:'pancadas fortes',95:'trovoadas',96:'trovoadas com granizo',99:'trovoadas com granizo forte'}

def _get_json(url,timeout=4):
    req=urllib.request.Request(url,headers={'User-Agent':'Aurora-Local/0.4','Accept':'application/json','Cache-Control':'no-cache, no-store, max-age=0','Pragma':'no-cache'})
    with urllib.request.urlopen(req,timeout=timeout) as r: return json.loads(r.read(300_000))

def weather_now(cfg,prompt):
    """Fast, direct weather path: cached city/IP geolocation then Open-Meteo; no LLM round trip."""
    place_match=re.search(r'\b(?:em|para|na cidade de)\s+([\wÀ-ÿ][\wÀ-ÿ .-]{1,48})',prompt,re.I)
    place=place_match.group(1).strip(' .?!') if place_match else ''
    cached=cfg.get('weather_location')
    now=time.time()
    if place:
        geo=_get_json('https://geocoding-api.open-meteo.com/v1/search?'+urlencode({'name':place,'count':1,'language':'pt','format':'json'}))
        rows=geo.get('results') or []
        if not rows: return f'Não achei a cidade {place}.'
        place=rows[0]; loc={'city':place['name'],'region':place.get('admin1',''),'country':place.get('country',''),'latitude':place['latitude'],'longitude':place['longitude'],'updated':now}; cached=loc
    elif isinstance(cached,dict) and now-float(cached.get('updated',0))<86400:
        loc=cached
    else:
        # IP lookup is city-level only; it is requested only when weather is asked, and cached for a day.
        geo=_get_json('https://ipwho.is/',3)
        if not geo.get('success') or not geo.get('city') or geo.get('latitude') is None: raise RuntimeError('Não consegui localizar sua cidade pela conexão. Diga “tempo em [cidade]”.')
        loc={'city':geo['city'],'region':geo.get('region',''),'country':geo.get('country',''),'latitude':geo['latitude'],'longitude':geo['longitude'],'updated':now}
    cfg['weather_location']=loc
    settings_save(cfg)
    query={'latitude':loc['latitude'],'longitude':loc['longitude'],'current':'temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,wind_speed_10m','daily':'temperature_2m_max,temperature_2m_min,precipitation_probability_max','timezone':'auto','forecast_days':1}
    data=_get_json('https://api.open-meteo.com/v1/forecast?'+urlencode(query),4); weather=data.get('current',{}); daily=data.get('daily',{})
    place_name=', '.join(x for x in (loc.get('city'),loc.get('region')) if x)
    condition=WMO_WEATHER.get(int(weather.get('weather_code',-1)),'condição variável')
    temp=round(float(weather['temperature_2m']))
    feels=round(float(weather.get('apparent_temperature',temp)))
    rain=float(weather.get('precipitation',0))
    forecast=''
    if daily.get('temperature_2m_min') and daily.get('temperature_2m_max'):
        forecast=f' Hoje, mínima de {round(float(daily["temperature_2m_min"][0]))} e máxima de {round(float(daily["temperature_2m_max"][0]))} graus'
        chance=(daily.get('precipitation_probability_max') or [None])[0]
        if chance is not None: forecast+=f', chance de chuva até {int(chance)} por cento'
        forecast+='.'
    return f'Agora em {place_name}: {temp} graus, {condition}, sensação de {feels}. Umidade {int(weather.get("relative_humidity_2m",0))} por cento, vento {round(float(weather.get("wind_speed_10m",0)))} quilômetros por hora.{forecast}'
