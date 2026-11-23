import unittest

from tools import mcp_test_device


class RoomDeviceSimulationTest(unittest.TestCase):
    def test_actuator_commands_report_state_and_reject_invalid_arguments(self):
        for profile, method, key in [('LivingRoom', 'setLight', 'lightOn'),
                                     ('BedRoom', 'setFan', 'fanOn')]:
            with self.subTest(profile=profile):
                state = mcp_test_device.ROOM_STATES[profile].copy()
                self.assertEqual(mcp_test_device.room_reply(profile, method, {'state': 'true'}, state),
                                 {'ok': False, 'error': 'INVALID_PARAMS'})
                self.assertIs(state[key], False)
                self.assertEqual(mcp_test_device.room_reply(profile, method, {'state': True}, state),
                                 {'ok': True, 'state': state.copy()})
                self.assertIs(state[key], True)
                self.assertEqual(mcp_test_device.room_reply(profile, 'getState', {}, state),
                                 {'ok': True, 'state': state.copy()})

    def test_kitchen_reports_synthetic_alarms_and_has_no_actuators(self):
        state = mcp_test_device.ROOM_STATES['Kitchen'].copy()
        mcp_test_device.update_room_sample('Kitchen', state, 35)
        self.assertIs(state['gasDetected'], True)
        self.assertIs(state['smokeDetected'], False)
        mcp_test_device.update_room_sample('Kitchen', state, 65)
        self.assertIs(state['gasDetected'], False)
        self.assertIs(state['smokeDetected'], True)
        self.assertEqual(mcp_test_device.room_reply('Kitchen', 'setFan', {'state': True}, state),
                         {'ok': False, 'error': 'UNKNOWN_METHOD'})
