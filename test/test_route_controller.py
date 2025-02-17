import unittest
from wp_operator import RouteController


class TestRouteController(unittest.TestCase):
    def setUp(self):
        self.controller = RouteController()
        self.controller._routes_by_namespace = {
            'namespace-test': {
                'route_root': {
                    'spec': {
                        'host': 'www.example.com',
                        'to': {'name': 'service1'}
                    }
                },
                'route_foo': {
                    'spec': {
                        'host': 'www.example.com',
                        'path': '/foo',
                        'to': {'name': 'service2'}
                    }
                },
                'route_foo_bar': {
                    'spec': {
                        'host': 'www.example.com',
                        'path': '/foo/bar',
                        'to': {'name': 'service3'}
                    }
                },
                'route_foo_bar_sanka': {
                    'spec': {
                        'host': 'www.example.com',
                        'path': '/foo/bar/sanka/',
                        'to': {'name': 'service4'}
                    }
                }
            }
        }

    def test_get_closest_parent_route_match_route_root(self):
        result = self.controller._get_closest_parent_route('namespace-test', 'www.example.com', '/fooooo')
        expected = {
            'name': 'route_root',
            'spec': {
                'host': 'www.example.com',
                'to': {'name': 'service1'}
            }
        }
        self.assertEqual(result, expected)

    def test_get_closest_parent_route_exact_match_route_foo(self):
        result = self.controller._get_closest_parent_route('namespace-test', 'www.example.com', '/foo')
        expected = {
            'name': 'route_foo',
            'spec': {
                'host': 'www.example.com',
                'path': '/foo',
                'to': {'name': 'service2'}
            }
        }
        self.assertEqual(result, expected)

    def test_get_closest_parent_route_match_route_foo_bar(self):
        result = self.controller._get_closest_parent_route('namespace-test', 'www.example.com', '/foo/bar/suomi')
        expected = {
            'name': 'route_foo_bar',
            'spec': {
                'host': 'www.example.com',
                'path': '/foo/bar',
                'to': {'name': 'service3'}
            }
        }
        self.assertEqual(result, expected)

    def test_get_closest_parent_route_match_route_foo_bar_sanka(self):
        result = self.controller._get_closest_parent_route('namespace-test', 'www.example.com', '/foo/bar/sanka/cof')
        expected = {
            'name': 'route_foo_bar_sanka',
            'spec': {
                'host': 'www.example.com',
                'path': '/foo/bar/sanka/',
                'to': {'name': 'service4'}
            }
        }
        self.assertEqual(result, expected)

    def test_get_closest_parent_route_match_route_foo_bar_sanka_siteurl_with_final_slash(self):
        result = self.controller._get_closest_parent_route('namespace-test', 'www.example.com', '/foo/bar/sanka/cof/')
        expected = {
            'name': 'route_foo_bar_sanka',
            'spec': {
                'host': 'www.example.com',
                'path': '/foo/bar/sanka/',
                'to': {'name': 'service4'}
            }
        }
        self.assertEqual(result, expected)

    def test_get_closest_parent_route_no_host_match(self):
        result = self.controller._get_closest_parent_route('namespace-test', 'www.example.fi', '/foo/drebin')
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
