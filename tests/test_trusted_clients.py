"""Regression checks for trusted-client Traefik routes (run with PyYAML)."""
import pathlib
import re
import unittest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFESTS = ROOT / 'argocd/configs/infrastructure/ingressroute/manifests'


class TrustedClientRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resources = [r for r in yaml.safe_load_all((MANIFESTS / 'trusted-clients.yaml').read_text()) if r]
        cls.routes = [route for resource in cls.resources for route in resource['spec']['routes']]

    def test_priorities_beat_all_media_routes(self):
        media = [r for r in yaml.safe_load_all((MANIFESTS / 'truenas-media.yaml').read_text()) if r and r['kind'] == 'IngressRoute']
        priorities = [route.get('priority', 0) for resource in media for route in resource['spec']['routes']]
        self.assertTrue(priorities)
        for route in self.routes:
            self.assertEqual(route['priority'], 110)
            self.assertTrue(all(route['priority'] > priority for priority in priorities))

    def test_exact_clients_hosts_and_no_forwardauth(self):
        matches = [route['match'] for route in self.routes]
        clients = set(re.findall(r'ClientIP\(`([^`]+)`\)', (MANIFESTS / 'trusted-clients.yaml').read_text()))
        hosts = set(re.findall(r'Host\(`([^.]+)\.646499453\.xyz`\)', ' '.join(matches)))
        self.assertEqual(clients, {'192.168.50.79/32', '100.102.152.24/32'})
        self.assertEqual(hosts, {'traefik', 'sonarr', 'radarr', 'whisparr', 'prowlarr', 'n8n', 'longhorn'})
        self.assertTrue(hosts.isdisjoint({'homeassistant', 'hermes', 'homepage'}))
        for route in self.routes:
            self.assertFalse(any('authentik-forwardauth' in middleware['name'] for middleware in route.get('middlewares', [])))

    def test_route_configuration(self):
        services = {
            'traefik': {'name': 'api@internal', 'kind': 'TraefikService'},
            'n8n': {'name': 'n8n', 'namespace': 'n8n', 'port': 80},
            'longhorn': {'name': 'longhorn-frontend', 'namespace': 'longhorn-system', 'port': 80},
        }
        for host in ['sonarr', 'radarr', 'whisparr', 'prowlarr']:
            services[host] = {'name': 'truenas-media', 'port': host}
        self.assertEqual(len(self.resources), len(services))
        for resource in self.resources:
            self.assertEqual(resource['kind'], 'IngressRoute')
            self.assertEqual(resource['metadata']['namespace'], 'traefik')
            self.assertFalse(any(key.startswith('gethomepage.dev/') for key in resource['metadata'].get('annotations', {})))
            spec = resource['spec']
            self.assertEqual(spec['entryPoints'], ['websecure'])
            self.assertEqual(spec['tls']['secretName'], 'wildcards-646499453-xyz-tls')
            self.assertEqual(len(spec['routes']), 1)
            route = spec['routes'][0]
            host = re.search(r'Host\(`([^.]+)\.646499453\.xyz`\)', route['match']).group(1)
            self.assertEqual(resource['metadata']['name'], 'trusted-' + ('traefik-dashboard' if host == 'traefik' else host))
            self.assertEqual(route['match'], f'Host(`{host}.646499453.xyz`) && (ClientIP(`192.168.50.79/32`) || ClientIP(`100.102.152.24/32`))')
            self.assertEqual(route['kind'], 'Rule')
            self.assertEqual(route['services'], [services[host]])
            expected_middlewares = [{'name': 'truenas-media-proto'}] if host in {'sonarr', 'radarr', 'whisparr', 'prowlarr'} else []
            self.assertEqual(route.get('middlewares', []), expected_middlewares)


if __name__ == '__main__':
    unittest.main()
