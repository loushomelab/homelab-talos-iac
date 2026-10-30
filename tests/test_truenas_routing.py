"""Regression checks for the bare-metal NAS route (run with PyYAML)."""
import pathlib
import unittest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROUTE = ROOT / 'argocd/configs/infrastructure/ingressroute/manifests/truenas.yaml'

class TrueNASRoutingTests(unittest.TestCase):
    def test_public_tls_termination_keeps_verified_https_upstream(self):
        resources = list(yaml.safe_load_all(ROUTE.read_text()))
        routes = [r for r in resources if r and r.get('kind') == 'IngressRoute']
        self.assertEqual(len(routes), 1, 'TrueNAS needs an HTTP route with managed frontend TLS')
        route = routes[0]
        self.assertEqual(route['spec']['tls']['secretName'], 'wildcards-646499453-xyz-tls')
        backend = route['spec']['routes'][0]['services'][0]
        self.assertEqual(backend['scheme'], 'https')
        transports = [r for r in resources if r and r.get('kind') == 'ServersTransport']
        self.assertEqual(len(transports), 1)
        transport = transports[0]
        self.assertEqual(backend['serversTransport'], transport['metadata']['name'])
        self.assertEqual(transport['spec']['serverName'], 'localhost')
        self.assertFalse(transport['spec'].get('insecureSkipVerify', False))
        roots = transport['spec']['rootCAs']
        self.assertEqual(len(roots), 1)
        certs = [r for r in resources if r and r.get('kind') == 'ConfigMap' and r['metadata']['name'] == roots[0]['configMap']]
        self.assertEqual(len(certs), 1)
        self.assertIn('-----BEGIN CERTIFICATE-----', certs[0]['data']['ca.crt'])
        self.assertNotIn('PRIVATE KEY', certs[0]['data']['ca.crt'])
        self.assertFalse(any(r.get('kind') == 'IngressRouteTCP' for r in resources if r))

    def test_homepage_does_not_model_bare_metal_nas_as_a_vm(self):
        import re
        path = ROOT / 'argocd/configs/workloads/homepage/manifests/config/services.yaml'
        text = re.sub(r'\{\{[^}]+\}\}', 'PLACEHOLDER', path.read_text())
        services = yaml.safe_load(text)
        hosts = next(group['Hosts'] for group in services if 'Hosts' in group)
        nas = next(group['NAS'] for group in hosts if 'NAS' in group)
        truenas = next(service['TrueNAS'] for service in nas if 'TrueNAS' in service)
        self.assertEqual(truenas['href'], 'https://truenas.646499453.xyz:8443')
        self.assertEqual(truenas['siteMonitor'], 'https://truenas.646499453.xyz:8443')
        for key in ['proxmoxNode', 'proxmoxVMID', 'proxmoxType', 'showStats']:
            self.assertNotIn(key, truenas)
        nodes = next(group['PVE-Nodes'] for group in services if 'PVE-Nodes' in group)
        self.assertNotIn('n100x8', {name for node in nodes for name in node})

    def test_retired_pve_url_redirects_instead_of_dialing_nas_port_8006(self):
        path = ROOT / 'argocd/configs/infrastructure/ingressroute/manifests/pve.yaml'
        resources = [r for r in yaml.safe_load_all(path.read_text()) if r]
        self.assertFalse(any(r['kind'] in ['Service', 'EndpointSlice'] and r['metadata']['name'] == 'pve-n100x8' for r in resources))
        route = next(r for r in resources if r['kind'] == 'IngressRoute' and r['metadata']['name'] == 'pve-n100x8')
        rule = route['spec']['routes'][0]
        middleware = next(r for r in resources if r['kind'] == 'Middleware' and r['metadata']['name'] == rule['middlewares'][0]['name'])
        self.assertEqual(middleware['spec']['redirectRegex']['replacement'], 'https://truenas.646499453.xyz:8443/${1}')

if __name__ == '__main__':
    unittest.main()
