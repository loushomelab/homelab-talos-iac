"""Regression check for the Connector's narrowly scoped subnet routes."""
import pathlib
import unittest

import yaml


class TailscaleConnectorTests(unittest.TestCase):
    def test_advertised_routes(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        path = root / 'argocd/configs/infrastructure/tailscale/connector/langshi-ha.yaml'
        connector = yaml.safe_load(path.read_text())
        self.assertEqual(set(connector['spec']['subnetRouter']['advertiseRoutes']), {
            '192.168.50.120/32', '192.168.50.231/32', '192.168.50.102/32', '192.168.50.79/32',
        })


if __name__ == '__main__':
    unittest.main()
