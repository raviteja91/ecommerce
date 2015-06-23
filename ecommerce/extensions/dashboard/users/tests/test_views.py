import json

from django.conf import settings
from django.contrib.messages import constants as MSG
from django.core.urlresolvers import reverse
from django.test import TestCase
import httpretty
import mock
from requests import Timeout
from testfixtures import LogCapture
from waffle import Switch

from ecommerce.extensions.dashboard.tests import DashboardViewTestMixin
from ecommerce.extensions.dashboard.users.views import UserDetailView
from ecommerce.tests.mixins import UserMixin

LOGGER_NAME = 'ecommerce.extensions.dashboard.users.views'


class UserDetailViewTests(DashboardViewTestMixin, UserMixin, TestCase):
    def setUp(self):
        super(UserDetailViewTests, self).setUp()
        self.switch, __ = Switch.objects.get_or_create(name='user_enrollments_on_dashboard', active=True)
        self.user = self.create_user(is_staff=True)
        self.client.login(username=self.user.username, password=self.password)
        self.data = [{'course_id': 'a/b/c'}]

    def mock_enrollment_api(self, status=200):
        self.assertTrue(httpretty.is_enabled)
        httpretty.register_uri(httpretty.GET, settings.ENROLLMENT_API_URL, status=status,
                               body=json.dumps(self.data),
                               content_type='application/json')

    def load_view(self):
        return self.client.get(reverse('dashboard:user-detail', args=[self.user.id]))

    @httpretty.activate
    def test_enrollments(self):
        """ Verify the view retrieves data from the Enrollment API. """
        self.mock_enrollment_api()
        response = self.load_view()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['enrollments'], self.data)

    def test_enrollments_switch_inactive(self):
        """ Verify enrollment data is NOT returned if the user_enrollments_on_dashboard switch is NOT active. """
        self.switch.active = False
        self.switch.save()

        mock_get_enrollments = mock.Mock()
        with mock.patch.object(UserDetailView, '_get_enrollments', mock_get_enrollments):
            response = self.load_view()
            self.assertFalse(mock_get_enrollments.called)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('enrollments', response.context)

    @httpretty.activate
    def test_enrollments_bad_response(self):
        """Verify a message is logged, and a separate message displayed to the user,
        if the API does not return HTTTP 200."""
        api_status = 500
        self.mock_enrollment_api(status=api_status)

        with LogCapture(LOGGER_NAME) as l:
            response = self.load_view()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context['enrollments'], [])
            self.assert_message_equals(response, 'Failed to retrieve enrollment data.', MSG.ERROR)
            l.check((LOGGER_NAME, 'WARNING',
                     'Failed to retrieve enrollments for [{}]. Enrollment API returned status code [{}].'.format(
                         self.user.username, api_status)))

    @mock.patch('requests.get', mock.Mock(side_effect=Timeout))
    def test_enrollments_exception(self):
        """Verify a message is logged, and a separate message displayed to the user,
        if an exception is raised while retrieving enrollments."""

        with LogCapture(LOGGER_NAME) as l:
            response = self.load_view()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context['enrollments'], [])
            self.assert_message_equals(response, 'Failed to retrieve enrollment data.', MSG.ERROR)
            l.check((LOGGER_NAME, 'ERROR',
                     'An unexpected error occurred while retrieving enrollments for [{}].'.format(self.user.username)))