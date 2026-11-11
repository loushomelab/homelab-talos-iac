"""Regression checks for Authentik's login blueprint and proxy trust."""
import ipaddress
import pathlib
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]


class BlueprintLoader(yaml.SafeLoader):
    pass


BlueprintLoader.add_constructor('!Find', lambda loader, node: loader.construct_sequence(node, deep=True))
BlueprintLoader.add_constructor('!KeyOf', lambda loader, node: loader.construct_scalar(node))


class AuthentikLoginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = yaml.safe_load((ROOT / 'argocd/apps/security/20-services/authentik.yaml').read_text())
        cls.values = app['spec']['sources'][0]['helm']['valuesObject']
        configmap = yaml.safe_load((ROOT / 'argocd/configs/security/authentik/manifests/blueprint-login.yaml').read_text())
        cls.entries = yaml.load(configmap['data']['login.yaml'], Loader=BlueprintLoader)['entries']

    def test_session_and_blueprint_mount(self):
        self.assertIn('authentik-blueprint-login', self.values['blueprints']['configMaps'])
        stage = next(e for e in self.entries if e['model'] == 'authentik_stages_user_login.userloginstage')
        self.assertEqual(stage['identifiers']['name'], 'default-authentication-login')
        self.assertEqual(stage['attrs'], {'session_duration': 'days=30', 'remember_me_offset': 'days=1'})

    def test_proxy_trust(self):
        cidrs = self.values['authentik']['listen']['trusted_proxy_cidrs'].split(',')
        self.assertEqual(set(cidrs), {'127.0.0.0/8', '::1/128', '10.244.0.0/16',
                                     '192.168.50.111/32', '192.168.50.113/32', '192.168.50.115/32'})
        for cidr in cidrs:
            ipaddress.ip_network(cidr, strict=True)

    def test_only_default_login_mfa_binding_is_conditioned(self):
        bindings = [e for e in self.entries if e['model'] == 'authentik_flows.flowstagebinding']
        self.assertEqual(len(bindings), 1)
        binding = bindings[0]
        self.assertEqual(binding['identifiers'], {
            'order': 30,
            'stage': ['authentik_stages_authenticator_validate.authenticatorvalidatestage', ['name', 'default-authentication-mfa-validation']],
            'target': ['authentik_flows.flow', ['slug', 'default-authentication-flow']],
        })
        self.assertEqual(binding['attrs'], {'policy_engine_mode': 'all', 'evaluate_on_plan': False, 're_evaluate_policies': True})
        policy = next(e for e in self.entries if e['model'] == 'authentik_policies_expression.expressionpolicy')
        expression = policy['attrs']['expression']
        self.assertNotIn('header', expression.lower())
        namespace = {}
        exec('def evaluate(ak_client_ip):\n' + ''.join('    ' + line + '\n' for line in expression.splitlines()), namespace)
        evaluate = namespace['evaluate']
        for address, expected in [('192.168.50.1', False), ('192.168.50.254', False),
                                  ('192.168.51.1', True), ('203.0.113.1', True), ('2001:db8::1', True)]:
            self.assertEqual(evaluate(ipaddress.ip_address(address)), expected)
        policy_binding = next(e for e in self.entries if e['model'] == 'authentik_policies.policybinding')
        self.assertEqual(policy_binding['identifiers'], {'order': 20, 'policy': policy['id'], 'target': binding['id']})
        self.assertTrue(policy_binding['attrs']['failure_result'])


if __name__ == '__main__':
    unittest.main()
