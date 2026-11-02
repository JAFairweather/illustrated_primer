"""Persist reply protocol in the existing pending job, never in model output.

This does not select a model, enable a transport, or authorize a notebook.
Old jobs without delivery metadata retain their legacy response contract.
"""


def delivery_options(job):
    if not isinstance(job,(list,tuple)) or len(job)>9:
        raise ValueError('invalid notebook delivery job')
    value=job[8] if len(job)>8 else None
    if value is None:
        return {}
    if not isinstance(value,dict) or value.keys()-{'response_format','revision_pending','renderer_fixture','model_transport'}:
        raise ValueError('unknown notebook delivery metadata')
    if 'response_format' in value and value['response_format']!='semantic-v1':
        raise ValueError('unsupported notebook response format')
    if 'revision_pending' in value and value['revision_pending'] is not True:
        raise ValueError('invalid notebook revision hold')
    if 'renderer_fixture' in value and (value['renderer_fixture'] is not True or
                                       value.get('response_format') != 'semantic-v1'):
        raise ValueError('renderer fixture requires semantic test delivery')
    if 'model_transport' in value and (value['model_transport'] != 'pi-socket-v1' or
            value.get('response_format') != 'semantic-v1' or value.get('renderer_fixture')):
        raise ValueError('model transport requires non-fixture semantic delivery')
    return dict(value)


def semantic_delivery(job):
    return delivery_options(job).get('response_format')=='semantic-v1'


def revision_pending(job):
    return delivery_options(job).get('revision_pending',False)


def with_delivery(job, **changes):
    options=delivery_options(job)
    for key,value in changes.items():
        if value is None:options.pop(key,None)
        else:options[key]=value
    result=list(job[:8])
    if options:
        while len(result)<8:result.append(None)
        result.append(options)
    delivery_options(result)
    return result
