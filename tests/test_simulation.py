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
    def test_dos_uses_exact_budget(self):
        args = parse_args(['--dry-run', '--ataque', 'dos', '--paquetes', '100',
                           '--burst-size', '100', '--force-attack', '--seed', '42'])
        simulator = Simulator(args)
        with patch('builtins.print'):
            simulator.run()
        self.assertEqual(simulator.emitted, 100)
        self.assertEqual(simulator.counts, {'normal': 0, 'dos': 100})

    def test_real_burst_obeys_wall_clock_rate(self):
        args = parse_args(['--ataque', 'dos', '--dos-mode', 'persistent', '--paquetes', '5',
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

    def test_flood_opens_new_connection_per_client_and_burst(self):
        args = parse_args(['--dry-run', '--ataque', 'dos', '--paquetes', '60',
                           '--burst-size', '30', '--dos-clients', '4', '--attack-gap', '0',
                           '--force-attack', '--seed', '1'])
        simulator = Simulator(args)
        created = []
        original = simulator._new_publisher

        def track(client_id):
            created.append(client_id)
            return original(client_id)

        with patch.object(simulator, '_new_publisher', side_effect=track), \
                patch('builtins.print'):
            simulator.run()
        self.assertEqual(simulator.counts, {'normal': 0, 'dos': 60})
        self.assertEqual(len(created), 8)                 # 2 ráfagas x 4 clientes
        self.assertEqual(len(set(created)), 8)            # client_id único: conexión nueva
        self.assertEqual(simulator._publishers, {})       # no se reutilizan

    def test_flood_topics_follow_dataset_format(self):
        from simulation.attacks import build_flood_packets
        packets = build_flood_packets(3, 7, 2, payload_size=100)
        self.assertEqual([p.topic for p in packets],
                         ['mqtt-malaria/atacante_flood_3_7/data/0/2',
                          'mqtt-malaria/atacante_flood_3_7/data/1/2'])
        self.assertTrue(all(len(p.payload) == 100 for p in packets))

    def test_mode_defaults(self):
        flood, persistent = parse_args([]), parse_args(['--dos-mode', 'persistent'])
        self.assertEqual((flood.dos_mode, flood.burst_size, flood.dos_clients), ('flood', 10000, 50))
        self.assertEqual((persistent.burst_size, persistent.dos_clients), (100, 5))

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

    def test_invalid_rates_and_unsupported_attacks_are_rejected(self):
        for argv in (['--dos-rate', '0'], ['--attack-gap', '-1'],
                     ['--dos-rate', 'inf'], ['--ataque', 'mitm'],
                     ['--ataque', 'intrusion'], ['--ataque', 'todos']):
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
