import unittest
from unittest.mock import Mock, patch

from simulation.cli import parse_args
from simulation.publishers import DryPublisher, MqttPublisher
from simulation.simulator import Simulator


class Clock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, delay):
        self.now += delay


class SimulationTests(unittest.TestCase):
    def test_todos_covers_every_scenario_with_exact_budget(self):
        args = parse_args(['--dry-run', '--ataque', 'todos', '--paquetes', '302',
                           '--burst-size', '100', '--force-attack', '--seed', '42'])
        simulator = Simulator(args)
        with patch('builtins.print'):
            simulator.run()
        self.assertEqual(simulator.emitted, 302)
        self.assertEqual(simulator.counts,
                         {'normal': 2, 'dos': 100, 'mitm': 100, 'intrusion': 100})

    def test_real_burst_obeys_wall_clock_rate(self):
        args = parse_args(['--ataque', 'dos', '--paquetes', '5',
                           '--burst-size', '5', '--dos-rate', '4', '--force-attack'])
        simulator = Simulator(args)
        clock = Clock()
        with patch('simulation.simulator.time.monotonic', clock.monotonic), \
                patch('simulation.simulator.time.sleep', clock.sleep), \
                patch.object(simulator, 'publisher', return_value=DryPublisher('test')), \
                patch('builtins.print'):
            simulator.run()
        self.assertAlmostEqual(clock.now, 1.0)
        self.assertEqual(simulator.counts['dos'], 5)

    def test_normal_traffic_does_not_exceed_budget(self):
        simulator = Simulator(parse_args(['--dry-run', '--paquetes', '1']))
        for device in simulator.devices:
            device.next_time = 0
        with patch('builtins.print'):
            simulator.run()
        self.assertEqual(simulator.emitted, 1)

    def test_failed_publish_is_not_counted_and_stops_publishers(self):
        simulator = Simulator(parse_args(['--dry-run', '--ataque', 'dos',
                                          '--force-attack']))
        with patch.object(DryPublisher, 'publish', return_value=4), \
                patch.object(DryPublisher, 'stop') as stop, patch('builtins.print'):
            with self.assertRaisesRegex(RuntimeError, 'Publicación fallida'):
                simulator.run()
        self.assertEqual(simulator.emitted, 0)
        self.assertEqual(stop.call_count, simulator.args.dos_clients)

    def test_invalid_rates_and_insufficient_todos_budget_are_rejected(self):
        for argv in (['--dos-rate', '0'], ['--attack-gap', '-1'],
                     ['--attack-rate', 'nan'], ['--dos-rate', 'inf'],
                     ['--ataque', 'todos', '--paquetes', '10']):
            with self.subTest(argv=argv), patch('sys.stderr'):
                with self.assertRaises(SystemExit):
                    parse_args(argv)

    def test_publisher_rejected_connection_cleans_up(self):
        client = Mock()
        client.loop_start.side_effect = lambda: client.on_connect(client, None, {}, 5)
        with patch('mqtt_utils.make_client', return_value=client):
            with self.assertRaisesRegex(RuntimeError, 'conexión rechazada'):
                MqttPublisher('test', 'broker', 1883)
        client.disconnect.assert_called_once()
        client.loop_stop.assert_called_once()

    def test_publisher_drains_before_disconnect(self):
        client = Mock()
        client.loop_start.side_effect = lambda: client.on_connect(client, None, {}, 0)
        info = Mock(rc=0)
        info.is_published.return_value = False
        client.publish.return_value = info
        order = []

        def complete(timeout):
            order.append('publish')
            info.is_published.return_value = True

        info.wait_for_publish.side_effect = complete
        client.disconnect.side_effect = lambda: order.append('disconnect')
        with patch('mqtt_utils.make_client', return_value=client):
            publisher = MqttPublisher('test', 'broker', 1883)
            self.assertEqual(publisher.publish('home/test', 'payload'), 0)
            publisher.stop()
        self.assertEqual(order, ['publish', 'disconnect'])

    def test_publisher_pending_timeout_is_reported_and_cleans_up(self):
        client = Mock()
        client.loop_start.side_effect = lambda: client.on_connect(client, None, {}, 0)
        info = Mock(rc=0)
        info.is_published.return_value = False
        client.publish.return_value = info
        with patch('mqtt_utils.make_client', return_value=client):
            publisher = MqttPublisher('test', 'broker', 1883)
            publisher.publish('home/test', 'payload')
            with self.assertRaisesRegex(RuntimeError, 'pendientes'):
                publisher.stop()
        client.disconnect.assert_called_once()
        client.loop_stop.assert_called_once()
