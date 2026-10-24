"""Explicit field mapping utility for future documented platform adapters.

Mappings are developer-owned, never supplied by the app user. They only select
known fields; authentication, unit conversions and remote calls belong in the
specific adapter. No guessing of vendor endpoints or mandatory parameters.
"""
from dataclasses import dataclass


def read_path(value, path):
    for part in path.split('.'):
        if isinstance(value,dict):
            value=value.get(part)
        elif isinstance(value,list) and part.isdigit() and int(part)<len(value):
            value=value[int(part)]
        else:
            return None
    return value


def mapped(source, fields, required):
    if not set(required)<=set(fields):
        raise ValueError('Every required field needs an explicit mapping')
    result={}
    for target,path in fields.items():
        value=read_path(source,path)
        if value is None:
            if target in required:
                raise ValueError('Missing required mapped field: '+target)
            continue
        parts=target.split('.')
        if any(not p for p in parts):
            raise ValueError('Invalid mapping path')
        cursor=result
        for part in parts[:-1]:
            cursor=cursor.setdefault(part,{})
            if not isinstance(cursor,dict):
                raise ValueError('Conflicting mapping paths')
        if parts[-1] in cursor:
            raise ValueError('Conflicting mapping paths')
        cursor[parts[-1]]=value
    return result


@dataclass(frozen=True)
class FieldMapper:
    request_fields: dict
    response_fields: dict
    required_request: tuple = ()
    required_response: tuple = ()

    def request(self, canonical_request):
        return mapped(canonical_request,self.request_fields,self.required_request)

    def response(self, provider_response):
        return mapped(provider_response,self.response_fields,self.required_response)
