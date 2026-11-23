"""Device names and payloads shared by the workbench and device transport."""

FIELDS = {
    'temperature': {'label': 'Temperature', 'unit': '°C', 'min': -50, 'max': 100, 'default': 24.5},
    'humidity': {'label': 'Humidity', 'unit': '% RH', 'min': 0, 'max': 100, 'default': 56},
    'lightOn': {'label': 'Light', 'default': False, 'method': 'setLight', 'param': 'state'},
    'fanOn': {'label': 'Fan', 'default': False, 'method': 'setFan', 'param': 'state'},
    'locked': {'label': 'Lock', 'default': True, 'method': 'setLock', 'param': 'locked'},
    'autoLightEnabled': {'label': 'Automatic lighting', 'default': False,
                         'method': 'setAutoLight', 'param': 'enabled'},
    'gasDetected': {'label': 'Gas detected', 'default': False},
    'smokeDetected': {'label': 'Smoke detected', 'default': False},
    'doorOpen': {'label': 'Door open', 'default': False},
    'motionDetected': {'label': 'Motion detected', 'default': False},
}

DEVICES = {
    'Kitchen': ('Kitchen', 'Living areas', ('temperature', 'gasDetected', 'smokeDetected', 'fanOn')),
    'Living Room': ('Living Room', 'Living areas', ('temperature', 'humidity', 'lightOn')),
    'Dining Room': ('Dining Room', 'Living areas', ('temperature', 'gasDetected', 'smokeDetected', 'lightOn')),
    'Bedroom2': ('Bedroom 2', 'Bedrooms & baths', ('temperature', 'humidity', 'lightOn')),
    'Bedroom': ('Bedroom', 'Bedrooms & baths', ('temperature', 'humidity', 'fanOn')),
    'Bathroom': ('Bathroom 1', 'Bedrooms & baths', ('humidity', 'fanOn')),
    'Bathroom2': ('Bathroom 2', 'Bedrooms & baths', ('humidity', 'fanOn')),
    'Entrance': ('Entrance', 'Access & outdoor', ('doorOpen', 'locked')),
    'Garage': ('Garage', 'Access & outdoor', ('motionDetected', 'lightOn')),
    'Hallway': ('Hallway', 'Access & outdoor', ('motionDetected', 'lightOn', 'autoLightEnabled')),
    'Balcony': ('Balcony', 'Access & outdoor', ('temperature', 'lightOn')),
}


def initial_state(name):
    return {key: FIELDS[key]['default'] for key in DEVICES[name][2]}


def update_state(state, patch):
    for key, value in patch.items():
        if key not in state:
            raise ValueError(f'Unknown field: {key}')
        field = FIELDS[key]
        if 'min' in field:
            if type(value) not in (int, float) or not field['min'] <= value <= field['max']:
                raise ValueError(f"{field['label']} must be between {field['min']} and {field['max']}")
        elif type(value) is not bool:
            raise ValueError(f"{field['label']} must be true or false")
    if 'lightOn' in patch and patch.get('autoLightEnabled', state.get('autoLightEnabled')):
        raise ValueError('Turn off automatic lighting before setting the light manually')
    state.update(patch)
    if state.get('autoLightEnabled'):
        state['lightOn'] = state['motionDetected']


def rpc(state, method, params):
    if method == 'getState':
        if params != {}:
            return {'ok': False, 'error': 'INVALID_PARAMS'}
    else:
        key = next((key for key in state if FIELDS[key].get('method') == method and method), None)
        if key is None:
            return {'ok': False, 'error': 'UNKNOWN_METHOD'}
        param = FIELDS[key]['param']
        if not isinstance(params, dict) or set(params) != {param} or type(params[param]) is not bool:
            return {'ok': False, 'error': 'INVALID_PARAMS'}
        try:
            update_state(state, {key: params[param]})
        except ValueError:
            return {'ok': False, 'error': 'REJECTED'}
    return {'ok': True, 'state': state.copy()}
