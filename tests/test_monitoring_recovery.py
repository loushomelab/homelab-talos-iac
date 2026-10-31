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
        self.assertEqual(v['compactor']['replicas'], 1, 'normal compaction approved; no backup gate')
        self.assertNotIn('compactor', v['mimir']['structuredConfig'], 'keep normal cleanup/retention defaults')
        self.assertNotIn('bucket_store', v['mimir']['structuredConfig']['blocks_storage'], 'do not bypass stale index guard')
        self.assertEqual(v['mimir']['structuredConfig']['ingester']['ring']['replication_factor'], 1)
        self.assertFalse(v['ingester']['persistentVolume']['enabled'])

    def test_alloy_worker_collection_shards_both_operator_scrapers(self):
        v = values('alloy')
        self.assertEqual(v['controller']['nodeSelector'], {'kubernetes.io/os': 'linux'})
        self.assertFalse(v['controller'].get('tolerations'), 'keep control-plane NoSchedule isolation')
        self.assertTrue(v['alloy']['clustering']['enabled'])
        content = v['alloy']['configMap']['content']
        for kind in ['servicemonitors', 'podmonitors']:
            self.assertRegex(content, rf'prometheus\.operator\.{kind} "default" \{{[^}}]*clustering \{{\s+enabled = true\s+\}}')

    def test_alloy_pod_records_required_worker_kernel_policy(self):
        v = values('alloy')
        self.assertEqual(v['controller'].get('podAnnotations', {}).get('homelab.louslab/profiling-kernel-policy'), 'kptr-restrict-1')

    def test_pyroscope_backend_restores_without_duplicate_collector(self):
        v = values('pyroscope')
        self.assertEqual(v['pyroscope']['replicaCount'], 1)
        self.assertEqual(v['alloy']['controller']['replicas'], 0)

if __name__ == '__main__':
    unittest.main()
