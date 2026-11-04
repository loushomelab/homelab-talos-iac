"""Native Homepage layout contract; run with PyYAML and unittest."""
import pathlib
import re
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'argocd/configs/workloads/homepage/manifests/config'
ROUTES = ROOT / 'argocd/configs/infrastructure/ingressroute/manifests/truenas-media.yaml'


class HomepageMediaLayoutTests(unittest.TestCase):
    def test_media_is_a_dedicated_tab_with_two_entrypoints_and_three_tool_columns(self):
        settings = yaml.safe_load((CONFIG / 'settings.yaml').read_text())
        layout = settings['layout']
        entrypoints = layout.get('Watch & Request', {})
        tools = layout.get('Media Management', {})
        for section, columns, groups in [
            (entrypoints, 2, ['Watch', 'Request']),
            (tools, 3, ['Library', 'Downloads', 'Subtitles']),
        ]:
            self.assertEqual(section.get('tab'), 'Media')
            self.assertEqual(section.get('style'), 'row')
            self.assertEqual(section.get('columns'), columns)
            children = {key: value for key, value in section.items() if isinstance(value, dict)}
            self.assertEqual(list(children), groups)
        self.assertFalse(tools['Subtitles']['useEqualHeights'])
        # Keep the existing PVE layout and global visual system intact.
        self.assertEqual(layout['Hosts']['columns'], 2)
        self.assertEqual(layout['PVE-Nodes']['columns'], 4)
        self.assertTrue(settings['useEqualHeights'])
        self.assertNotIn('Media', layout, 'Do not keep the old unstructured discovery bucket')

    def test_all_eight_apps_are_discovered_once_in_task_order_without_route_changes(self):
        expected = {
            'plex': ('Watch', 10),
            'seerr': ('Request', 10),
            'sonarr': ('Library', 10),
            'radarr': ('Library', 20),
            'qbittorrent': ('Downloads', 10),
            'prowlarr': ('Downloads', 20),
            'bazarr': ('Subtitles', 10),
            'lingarr': ('Subtitles', 20),
        }
        resources = [resource for resource in yaml.safe_load_all(ROUTES.read_text()) if resource]
        routes = [resource for resource in resources if resource['kind'] == 'IngressRoute']
        self.assertEqual({route['metadata']['name'] for route in routes}, set(expected))
        for route in routes:
            name = route['metadata']['name']
            group, weight = expected[name]
            annotations = route['metadata']['annotations']
            self.assertEqual(annotations['gethomepage.dev/enabled'], 'true')
            self.assertEqual(annotations['gethomepage.dev/group'], group)
            self.assertEqual(int(annotations.get('gethomepage.dev/weight', 0)), weight)
            self.assertEqual(annotations['gethomepage.dev/external'], 'true')
            self.assertEqual(annotations['gethomepage.dev/href'], f'https://{name}.646499453.xyz:8443')
            self.assertEqual(annotations['gethomepage.dev/siteMonitor'], annotations['gethomepage.dev/href'])
            self.assertEqual(route['spec']['tls']['secretName'], 'wildcards-646499453-xyz-tls')
            for rule in route['spec']['routes']:
                self.assertIn(
                    {'name': 'lan-only-allowlist', 'namespace': 'monitoring'},
                    rule['middlewares'],
                )
        # Discovery remains the only source of media cards; no duplicate bookmarks/services.
        for filename in ['services.yaml', 'bookmarks.yaml']:
            configured = re.sub(r'\{\{[^}]+\}\}', 'PLACEHOLDER', (CONFIG / filename).read_text())
            for app in expected:
                self.assertNotRegex(configured.lower(), rf'\b{app}\b')

    def test_arr_ui_uses_forward_auth_while_api_and_other_apps_do_not(self):
        resources = [resource for resource in yaml.safe_load_all(ROUTES.read_text()) if resource]
        routes = {
            route['metadata']['name']: route
            for route in resources
            if route['kind'] == 'IngressRoute'
        }
        proto = {'name': 'truenas-media-proto'}
        allow = {'name': 'lan-only-allowlist', 'namespace': 'monitoring'}
        forward = {'name': 'authentik-forwardauth', 'namespace': 'traefik'}
        for name in ('sonarr', 'radarr', 'prowlarr'):
            rules = routes[name]['spec']['routes']
            self.assertEqual(len(rules), 2)
            api, ui = rules
            self.assertEqual(api['match'], f'Host(`{name}.646499453.xyz`) && PathPrefix(`/api`)')
            self.assertEqual(ui['match'], f'Host(`{name}.646499453.xyz`)')
            self.assertGreater(api['priority'], ui['priority'])
            self.assertEqual(api['middlewares'], [proto, allow])
            self.assertEqual(ui['middlewares'], [allow, forward, proto])
            self.assertEqual(api['services'], ui['services'])
            self.assertEqual(
                routes[name]['metadata']['annotations']['gethomepage.dev/widget.url'],
                f'https://{name}.646499453.xyz:8443',
            )
        direct_urls = {
            'bazarr': 'http://192.168.50.102:6767',
            'seerr': 'http://192.168.50.102:5055',
            'qbittorrent': 'http://192.168.50.102:8080',
            'plex': 'http://192.168.50.102:32400',
        }
        for name, widget_url in direct_urls.items():
            rules = routes[name]['spec']['routes']
            self.assertEqual(len(rules), 1)
            self.assertNotIn('PathPrefix', rules[0]['match'])
            self.assertNotIn(
                'authentik-forwardauth',
                [middleware['name'] for middleware in rules[0]['middlewares']],
            )
            self.assertEqual(
                routes[name]['metadata']['annotations']['gethomepage.dev/widget.url'],
                widget_url,
            )
        lingarr = routes['lingarr']['spec']['routes']
        self.assertEqual(len(lingarr), 1)
        self.assertNotIn(
            'authentik-forwardauth',
            [middleware['name'] for middleware in lingarr[0]['middlewares']],
        )


if __name__ == '__main__':
    unittest.main()
