import json

import ddt
import httpretty
import mock
from dateutil.parser import parse
from django.conf import settings
from django.core.cache import cache
from django.core.urlresolvers import reverse
from django.utils.timezone import now
from oscar.core.loading import get_model
from oscar.test import factories
from requests.exceptions import ConnectionError, Timeout
from slumber.exceptions import SlumberBaseException

from ecommerce.courses.tests.factories import CourseFactory
from ecommerce.core.tests.decorators import mock_course_catalog_api_client
from ecommerce.courses.tests.mixins import CourseCatalogServiceMockMixin
from ecommerce.extensions.api.v2.tests.views import JSON_CONTENT_TYPE
from ecommerce.extensions.api.v2.views.offers import OfferViewSet
from ecommerce.extensions.catalogue.tests.mixins import CourseCatalogTestMixin
from ecommerce.tests.testcases import TestCase

Benefit = get_model('offer', 'Benefit')
ConditionalOffer = get_model('offer', 'ConditionalOffer')


@ddt.ddt
class OfferViewSetTests(CourseCatalogTestMixin, CourseCatalogServiceMockMixin, TestCase):
    path = reverse('api:v2:offers-list')

    def setUp(self):
        super(OfferViewSetTests, self).setUp()
        self.user = self.create_user(is_staff=True)
        self.client.login(username=self.user.username, password=self.password)

    def test_authentication_required(self):
        """Guest cannot access the view."""
        self.client.logout()
        response = self.client.post(self.path, data={})
        self.assertEqual(response.status_code, 401)

    def test_authorization_required(self):
        """Non-staff user cannot access the view."""
        user = self.create_user(is_staff=False)
        self.client.login(username=user.username, password=self.password)
        response = self.client.post(self.path, data={})
        self.assertEqual(response.status_code, 403)

    def assert_offer_data(self, response_content, data):
        self.assertEqual(response_content['offer_type'], 'Site')
        self.assertEqual(response_content['status'], 'Open')

        for key in ['start_datetime', 'end_datetime']:
            self.assertEqual(parse(response_content[key]), parse(data[key]))

        benefit = Benefit.objects.get(id=response_content['benefit'])
        self.assertEqual(benefit.value, data['benefit_value'])

    @httpretty.activate
    @mock_course_catalog_api_client
    @ddt.data(ConnectionError, SlumberBaseException, Timeout)
    def test_get_program_error(self, error):
        """An error is logged when the error happens trying to get the program."""
        def callback(*args):
            raise error

        httpretty.register_uri(
            method=httpretty.GET,
            uri='{}/programs/dummy-uuid/'.format(settings.COURSE_CATALOG_API_URL),
            body=callback
        )
        cache.clear()

        view = OfferViewSet()
        with mock.patch('ecommerce.extensions.api.v2.views.offers.log.warning') as mock_logger:
            with self.assertRaises(error):
                view.get_program(self.request, 'dummy-uuid')
            self.assertTrue(mock_logger.called)

    @httpretty.activate
    @mock_course_catalog_api_client
    def test_create(self):
        """New ConditionalOffer is created."""
        data = {
            'program_uuid': 123,
            'benefit_value': 15,
            'start_datetime': str(now()),
            'end_datetime': str(now())
        }
        course = CourseFactory()
        course.create_or_update_seat('verified', False, 0, self.partner)
        self.mock_catalog_program_list(123, course.id)
        response = self.client.post(self.path, json.dumps(data), JSON_CONTENT_TYPE)
        self.assert_offer_data(json.loads(response.content), data)

    def test_delete(self):
        """ConditionalOffer is deleted."""
        offer = factories.ConditionalOfferFactory()
        self.assertEqual(ConditionalOffer.objects.count(), 1)

        path = reverse('api:v2:offers-detail', kwargs={'pk': offer.id})
        self.client.delete(path)

        self.assertEqual(ConditionalOffer.objects.count(), 0)

    def test_update(self):
        """ConditionalOffer is updated."""
        benefit_value = 15
        offer = factories.ConditionalOfferFactory(benefit__value=benefit_value)
        self.assertEqual(offer.benefit.value, benefit_value)

        updated_benefit_value = 77
        path = reverse('api:v2:offers-detail', kwargs={'pk': offer.id})
        response = self.client.patch(path, json.dumps({
            'id': offer.id,
            'benefit_value': updated_benefit_value
        }), JSON_CONTENT_TYPE)
        self.assertEqual(response.status_code, 200)

        benefit = Benefit.objects.get(id=json.loads(response.content)['benefit'])
        self.assertEqual(benefit.value, updated_benefit_value)
