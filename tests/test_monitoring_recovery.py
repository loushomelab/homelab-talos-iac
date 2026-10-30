"""Backend recovery gate; collectors stay paused until runtime acceptance."""
import pathlib
import unittest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
def values(app):
    path = ROOT / f'argocd/apps/monitoring/{app}.yaml'
    return yaml.safe_load(path.read_text())['spec']['sources'][0]['helm']['valuesObject']

class MonitoringRecoveryTests(unittest.TestCase):
    def test_mimir_read_and_write_backends_restore_without_downscale_bypass(self):
        v = values('mimir')
        for component in ['distributor','ingester','querier','query_frontend','store_gateway','gateway']:
            self.assertEqual(v[component]['replicas'], 1, component)
        self.assertEqual(v['query_scheduler']['replicas'], 2)
        for component in ['ingester','store_gateway']:
            self.assertNotIn('zoneAwareReplication',v[component])
        self.assertEqual(v['compactor']['replicas'], 0, 'defer S3 compaction until acceptance')
        self.assertEqual(v['mimir']['structuredConfig']['ingester']['ring']['replication_factor'], 1)
        self.assertFalse(v['ingester']['persistentVolume']['enabled'])

    def test_pyroscope_backend_restores_without_duplicate_collector(self):
        v = values('pyroscope')
        self.assertEqual(v['pyroscope']['replicaCount'], 1)
        self.assertEqual(v['alloy']['controller']['replicas'], 0)

if __name__ == '__main__':
    unittest.main()
